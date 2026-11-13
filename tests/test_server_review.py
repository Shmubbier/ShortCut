import http.client
import json
import os
import tempfile
import threading
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from unittest import mock

import review
import server

ADMIN = "admin-code"


class ServerReviewTest(unittest.TestCase):
    gate = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {"REVIEW_DATA_DIR": self.tmp.name, "ADMIN_CODE": ADMIN,
               "REVIEW_EXPIRES_AT": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
        if self.gate:
            env["REVIEWER_CODE"] = "test-code"
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        if not self.gate:
            os.environ.pop("REVIEWER_CODE", None)
        review._reset()
        server.ADMIN_TOKENS.clear()
        server.ADMIN_FAILS.clear()
        stub = mock.patch.dict(server.ROUTES, {"/api/plan": lambda body: {"title": "stub", "scenes": []}})
        stub.start()
        self.addCleanup(stub.stop)
        quiet = mock.patch.object(server.Handler, "log_message", lambda *a: None)
        quiet.start()
        self.addCleanup(quiet.stop)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def req(self, method, path, body=None, headers=None, raw=None):
        c = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=10)
        h = dict(headers or {})
        data = raw
        if body is not None:
            data = json.dumps(body)
            h["Content-Type"] = "application/json"
        c.request(method, path, data, h)
        r = c.getresponse()
        text = r.read().decode()
        out = (r.status, text, r)
        c.close()
        return out

    def admin_cookie(self):
        s, _, r = self.req("POST", "/admin", raw="code=" + ADMIN,
                           headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(s, 303)
        return r.getheader("Set-Cookie").split(";")[0]

    def test_status_open(self):
        s, t, _ = self.req("GET", "/api/session/status")
        self.assertEqual(s, 200)
        self.assertIs(json.loads(t)["open"], True)

    def test_plan_locked_without_headers(self):
        s, t, _ = self.req("POST", "/api/plan", {})
        self.assertEqual(s, 401)
        self.assertEqual(json.loads(t), {"error": "locked"})

    def test_plan_with_headers_runs_and_logs(self):
        s, t, _ = self.req("POST", "/api/plan", {"topic": "cats"},
                           {"X-Reviewer-Code": "test-code", "X-Reviewer-Name": "Maria"})
        self.assertEqual(s, 200)
        self.assertIn("stub", t)
        e = review.read_log()[0]
        self.assertEqual((e["name"], e["action"], e["topic"], e["ok"]), ("Maria", "plan", "cats", True))

    def test_session_wrong_code(self):
        s, t, _ = self.req("POST", "/api/session", {"code": "nope", "name": "Maria"})
        self.assertEqual(s, 401)
        self.assertEqual(json.loads(t), {"error": review.BAD_CODE})

    def test_session_ok_logs_unlock(self):
        s, t, _ = self.req("POST", "/api/session", {"code": "test-code", "name": " Maria "})
        self.assertEqual(s, 200)
        self.assertEqual(json.loads(t)["name"], "Maria")
        self.assertEqual(review.read_log()[0]["action"], "unlock")

    def test_ungated_styles_without_headers(self):
        self.assertEqual(self.req("GET", "/api/styles")[0], 200)

    def test_assets_list_gated(self):
        self.assertEqual(self.req("GET", "/api/assets")[0], 401)

    def test_footage_gated(self):
        self.assertEqual(self.req("POST", "/api/footage/upload", {})[0], 401)

    def test_cap_returns_429(self):
        h = {"X-Reviewer-Code": "test-code", "X-Reviewer-Name": "Maria"}
        with mock.patch.dict(os.environ, {"REVIEW_DAILY_CAP": "1"}):
            self.assertEqual(self.req("POST", "/api/plan", {}, h)[0], 200)
            self.assertEqual(self.req("POST", "/api/plan", {}, h)[0], 429)

    def test_admin_requires_code_and_escapes(self):
        review.log("<script>x</script>", "plan", "t", True, 1)
        s, t, _ = self.req("GET", "/admin")
        self.assertEqual(s, 200)
        self.assertIn("<form", t)
        self.assertNotIn("script", t)
        cookie = self.admin_cookie()
        s, t, _ = self.req("GET", "/admin", headers={"Cookie": cookie})
        self.assertIn("&lt;script&gt;", t)
        self.assertNotIn("<script>x", t)

    def test_admin_cookie_attributes(self):
        _, _, r = self.req("POST", "/admin", raw="code=" + ADMIN,
                           headers={"Content-Type": "application/x-www-form-urlencoded"})
        c = r.getheader("Set-Cookie")
        for part in ("sc_admin=", "Path=/admin", "HttpOnly", "SameSite=Lax", "Max-Age=43200"):
            self.assertIn(part, c)
        self.assertEqual(r.getheader("Location"), "/admin")

    def test_shots_without_blender_not_counted(self):
        os.environ["REVIEW_DAILY_CAP"] = "1"
        h = {"X-Reviewer-Code": "test-code", "X-Reviewer-Name": "Maria"}
        with mock.patch.object(server.shots_jobs, "blender_executable", side_effect=RuntimeError("x")):
            s, t, _ = self.req("POST", "/api/shots/render", {}, h)
        self.assertEqual(s, 400)
        self.assertIn("hosted version", t)
        self.assertEqual(self.req("POST", "/api/plan", {}, h)[0], 200)  # cap of 1 still unspent

    def test_admin_wrong_code(self):
        s, _, r = self.req("POST", "/admin", raw="code=bad",
                           headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(s, 401)
        self.assertIsNone(r.getheader("Set-Cookie"))

    def test_admin_survives_corrupt_log(self):
        cookie = self.admin_cookie()
        review.log("Maria", "plan", "t", True, 1)
        with open(review._log_path(), "a") as f:
            f.write("{not json\n")
        with mock.patch("sys.stdout"):
            s, t, _ = self.req("GET", "/admin", headers={"Cookie": cookie})
        self.assertEqual(s, 200)
        self.assertIn("Maria", t)  # the corrupt line is skipped, not fatal

    def test_admin_limiter(self):
        form = {"Content-Type": "application/x-www-form-urlencoded"}
        for _ in range(5):
            self.assertEqual(self.req("POST", "/admin", raw="code=bad", headers=form)[0], 401)
        s, t, _ = self.req("POST", "/admin", raw="code=" + ADMIN, headers=form)
        self.assertEqual(s, 429)
        self.assertIn("Too many tries", t)

    def test_limiter_ignores_spoofed_first_hop(self):
        for i in range(5):
            h = {"X-Reviewer-Code": "wrong", "X-Reviewer-Name": "Maria", "X-Forwarded-For": f"9.9.9.{i}, 1.2.3.4"}
            self.assertEqual(self.req("POST", "/api/plan", {}, h)[0], 401)
        h = {"X-Reviewer-Code": "test-code", "X-Reviewer-Name": "Maria", "X-Forwarded-For": "8.8.8.8, 1.2.3.4"}
        self.assertEqual(self.req("POST", "/api/plan", {}, h)[0], 401)

    def test_assets_list_does_not_use_cap(self):
        h = {"X-Reviewer-Code": "test-code", "X-Reviewer-Name": "Maria"}
        with mock.patch.dict(os.environ, {"REVIEW_DAILY_CAP": "1"}):
            self.assertEqual(self.req("GET", "/api/assets", headers=h)[0], 200)
            self.assertEqual(self.req("GET", "/api/assets", headers=h)[0], 200)
            self.assertEqual(self.req("POST", "/api/plan", {}, h)[0], 200)

    def test_expired_window_locks(self):
        h = {"X-Reviewer-Code": "test-code", "X-Reviewer-Name": "Maria"}
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        with mock.patch.dict(os.environ, {"REVIEW_EXPIRES_AT": past}):
            s, t, _ = self.req("POST", "/api/plan", {}, h)
        self.assertEqual((s, json.loads(t)), (401, {"error": "locked"}))

    def test_csv(self):
        cookie = self.admin_cookie()
        s, t, r = self.req("GET", "/admin/log.csv", headers={"Cookie": cookie})
        self.assertEqual(s, 200)
        self.assertTrue(r.getheader("Content-Type").startswith("text/csv"))
        self.assertTrue(t.startswith("time,name,action,topic,ok,seconds"))
        self.assertEqual(self.req("GET", "/admin/log.csv")[0], 401)


class GateInactiveTest(ServerReviewTest):
    gate = False

    def test_gate_inactive_by_default(self):
        s, t, _ = self.req("POST", "/api/plan", {})
        self.assertEqual(s, 200)
        self.assertIn("stub", t)
        self.assertEqual(review.read_log(), [])

    # inherited gate-specific tests do not apply without a code
    test_status_open = test_plan_locked_without_headers = test_plan_with_headers_runs_and_logs = None
    test_session_wrong_code = test_session_ok_logs_unlock = test_assets_list_gated = None
    test_footage_gated = test_cap_returns_429 = test_admin_requires_code_and_escapes = None
    test_shots_without_blender_not_counted = test_admin_cookie_attributes = test_admin_wrong_code = test_admin_survives_corrupt_log = test_csv = None
    test_admin_limiter = test_limiter_ignores_spoofed_first_hop = test_assets_list_does_not_use_cap = test_expired_window_locks = None


class HostedNoCodeTest(ServerReviewTest):
    gate = False

    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ, {"PORT": "9"})
        p.start()
        self.addCleanup(p.stop)

    def test_hosted_without_code_fails_closed(self):
        s, t, _ = self.req("POST", "/api/plan", {})
        self.assertEqual((s, json.loads(t)), (401, {"error": "locked"}))
        s, t, _ = self.req("GET", "/api/session/status")
        self.assertIs(json.loads(t)["open"], False)

    def test_hosted_without_code_removes_credentials(self):
        auth = os.path.join(self.tmp.name, "auth.json")
        with open(auth, "w") as f:
            f.write("{}")
        with mock.patch.dict(os.environ, {"CODEX_HOME": self.tmp.name}):
            self.req("GET", "/api/session/status")
        self.assertFalse(os.path.exists(auth))

    test_status_open = test_plan_locked_without_headers = test_plan_with_headers_runs_and_logs = None
    test_session_wrong_code = test_session_ok_logs_unlock = test_assets_list_gated = None
    test_footage_gated = test_cap_returns_429 = test_admin_requires_code_and_escapes = None
    test_shots_without_blender_not_counted = test_admin_cookie_attributes = test_admin_wrong_code = test_admin_survives_corrupt_log = test_csv = None
    test_admin_limiter = test_limiter_ignores_spoofed_first_hop = test_assets_list_does_not_use_cap = test_expired_window_locks = None


class MediaTest(unittest.TestCase):
    def test_absolute_media_uses_port_and_demo(self):
        with mock.patch.dict(os.environ, {"PORT": "9123"}):
            out = server._absolute_media({"a": "/assets/x.jpg", "b": ["/demo/media/x.jpg"]})
        self.assertEqual(out, {"a": "http://127.0.0.1:9123/assets/x.jpg", "b": ["http://127.0.0.1:9123/demo/media/x.jpg"]})

    def test_demo_static_served_and_confined(self):
        env = {"REVIEW_DATA_DIR": tempfile.gettempdir()}
        with mock.patch.dict(os.environ, env), mock.patch.object(server.Handler, "log_message", lambda *a: None):
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                def get(p):
                    c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
                    c.request("GET", p)
                    r = c.getresponse(); r.read(); c.close()
                    return r.status
                self.assertEqual(get("/demo/index.json"), 200)
                self.assertEqual(get("/demo/../../server.py"), 404)
            finally:
                httpd.shutdown(); httpd.server_close()


if __name__ == "__main__":
    unittest.main()
