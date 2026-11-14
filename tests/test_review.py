import json
import os
import tempfile
import threading
import unittest
from unittest import mock

# `discover -s tests` does not import tests/__init__.py, so isolate here too, before review/server load.
_tmp = tempfile.mkdtemp(prefix="shortcut-tests-")
os.environ["CODEX_HOME"] = os.path.join(_tmp, "codex")
os.environ["REVIEW_DATA_DIR"] = _tmp

import review

FUTURE = "2999-01-01T00:00:00+00:00"
PAST = "2000-01-01T00:00:00+00:00"
BAD = "That code isn't valid or has expired"


class AdminCodeTest(unittest.TestCase):
    def test_admin_code(self):
        with mock.patch.dict(os.environ, {"REVIEWER_CODE": "abc", "ADMIN_REVIEW_CODE": "own", "REVIEW_EXPIRES_AT": FUTURE}):
            review._reset()
            self.assertEqual(review.check("own", "Naomi", "c-admin"), (True, "Admin · Naomi"))
            self.assertEqual(review.check("abc", "Maria", "c-admin"), (True, "Maria"))
            self.assertTrue(review.is_admin_code("own"))
            self.assertFalse(review.is_admin_code("abc"))
        with mock.patch.dict(os.environ, {"ADMIN_REVIEW_CODE": ""}):
            self.assertFalse(review.is_admin_code(""))  # unset never matches an empty code


class GuestCodeTest(unittest.TestCase):
    def test_guest_code_tagged(self):
        env = {"REVIEWER_CODE": "abc", "ADMIN_REVIEW_CODE": "own", "GUEST_REVIEW_CODES": "Peter=pete123; Bad=;=x", "REVIEW_EXPIRES_AT": FUTURE}
        with mock.patch.dict(os.environ, env):
            review._reset()
            self.assertEqual(review.check("pete123", "Peter S", "g1"), (True, "Peter · Peter S"))
            self.assertEqual(review.check("abc", "Peter · fake", "g1")[0], False)
            self.assertEqual(review.check("", "Maria", "g2"), (False, BAD))
            self.assertEqual(review.guest_label(""), "")
            self.assertFalse(review.is_admin_code("pete123"))


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {
            "REVIEWER_CODE": "abc", "REVIEW_EXPIRES_AT": FUTURE,
            "REVIEW_DATA_DIR": self.tmp.name, "CODEX_HOME": self.tmp.name,
        })
        p.start()
        self.addCleanup(p.stop)
        review._reset()

    def lines(self):
        with open(os.path.join(self.tmp.name, "review-log.jsonl"), encoding="utf-8") as f:
            return f.read().splitlines()

    def test_inactive_without_code(self):
        del os.environ["REVIEWER_CODE"]
        self.assertIs(review.active(), False)

    def test_check_accepts_right_code_and_trims_name(self):
        self.assertEqual(review.check("abc", "  Maria ", "c1"), (True, "Maria"))

    def test_check_rejects_wrong_code_message(self):
        self.assertEqual(review.check("nope", "Maria", "c1"), (False, BAD))

    def test_name_length(self):
        self.assertFalse(review.check("abc", "A", "c1")[0])
        self.assertFalse(review.check("abc", "x" * 41, "c1")[0])
        self.assertTrue(review.check("abc", "Al", "c1")[0])

    def test_limiter_after_five_wrong(self):
        for _ in range(5):
            review.check("bad", "Maria", "c2")
        self.assertFalse(review.check("abc", "Maria", "c2")[0])
        self.assertTrue(review.check("abc", "Maria", "c3")[0])

    def test_expired_rejects(self):
        os.environ["REVIEW_EXPIRES_AT"] = PAST
        self.assertFalse(review.check("abc", "Maria", "c1")[0])
        self.assertIs(review.is_open(), False)

    def test_naive_expiry_fails_closed(self):
        os.environ["REVIEW_EXPIRES_AT"] = "2030-01-01T00:00:00"
        with mock.patch("builtins.print") as pr:
            self.assertIs(review.is_open(), False)
        pr.assert_called_once()

    def test_corrupt_log_line_skipped(self):
        review.log("A", "plan", "x", True, 1)
        with open(review._log_path(), "a", encoding="utf-8") as f:
            f.write('{"time": "trunc' + chr(10))
        review.log("B", "plan", "y", True, 1)
        self.assertEqual(len(review.read_log()), 2)
        self.assertEqual(len(review.log_csv().strip().splitlines()), 3)

    def test_daily_cap(self):
        os.environ["REVIEW_DAILY_CAP"] = "3"
        self.assertEqual([review.allow_action() for _ in range(4)],
                         [True, True, True, False])

    def test_log_line_shape(self):
        review.log("Maria", "plan", "x" * 200, True, 1.5)
        lines = self.lines()
        self.assertEqual(len(lines), 1)
        d = json.loads(lines[0])
        self.assertEqual(set(d), {"time", "name", "action", "topic", "ok", "seconds"})
        self.assertEqual(len(d["topic"]), 120)
        self.assertEqual(review.read_log()[0]["name"], "Maria")
        self.assertIn("time,name,action", review.log_csv())

    def test_log_concurrent_writes(self):
        def work():
            for i in range(25):
                review.log("T", "plan", f"t{i}", True, 0.1)
        ts = [threading.Thread(target=work) for _ in range(20)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        lines = self.lines()
        self.assertEqual(len(lines), 500)
        for l in lines:
            json.loads(l)

    def test_expire_and_seed_credentials(self):
        os.environ["CODEX_AUTH_JSON"] = '{"x":1}'
        auth = os.path.join(self.tmp.name, "auth.json")
        review.seed_credentials()
        self.assertTrue(os.path.exists(auth))
        os.environ["REVIEW_EXPIRES_AT"] = PAST
        self.assertIs(review.expire_credentials(), True)
        self.assertFalse(os.path.exists(auth))
        review.seed_credentials()
        self.assertFalse(os.path.exists(auth))

    def test_expire_noop_when_gate_inactive(self):
        del os.environ["REVIEWER_CODE"]
        auth = os.path.join(self.tmp.name, "auth.json")
        with open(auth, "w") as f:
            f.write("{}")
        self.assertIs(review.expire_credentials(), False)
        self.assertTrue(os.path.exists(auth))

    def test_read_log_skips_non_dict_and_bad_utf8(self):
        review.log("A", "plan", "x", True, 1)
        with open(review._log_path(), "ab") as f:
            f.write(b"123\n\xff\xfe{bad\n")
        review.log("B", "plan", "y", True, 1)
        self.assertEqual([e["name"] for e in review.read_log()], ["B", "A"])
        self.assertEqual(len(review.log_csv().strip().splitlines()), 3)

    def test_hosted_signal(self):
        for k in ("REVIEW_HOSTED", "RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PROJECT_ID"):
            os.environ.pop(k, None)
        os.environ["PORT"] = "9"
        self.assertIs(review.hosted(), False)
        os.environ["RAILWAY_PROJECT_ID"] = "p"
        self.assertIs(review.hosted(), True)
        del os.environ["RAILWAY_PROJECT_ID"]
        os.environ["REVIEW_HOSTED"] = "1"
        self.assertIs(review.hosted(), True)

    def test_default_codex_home_never_deleted(self):
        del os.environ["REVIEWER_CODE"]
        del os.environ["CODEX_HOME"]
        os.environ["REVIEW_HOSTED"] = "1"
        fake_home = os.path.join(self.tmp.name, "home")
        auth = os.path.join(fake_home, ".codex", "auth.json")
        os.makedirs(os.path.dirname(auth))
        with open(auth, "w") as f:
            f.write("{}")
        with mock.patch.object(review.Path, "home", return_value=review.Path(fake_home)),                 mock.patch.object(review.Path, "unlink") as unlink:
            self.assertIs(review.expire_credentials(), False)
        unlink.assert_not_called()
        self.assertTrue(os.path.exists(auth))

    def test_suite_never_points_at_real_codex(self):
        real = os.path.normcase(str(review.Path.home() / ".codex"))
        here = os.path.normcase(os.path.abspath(os.environ["CODEX_HOME"]))
        self.assertFalse(here == real or here.startswith(real + os.sep))
        self.assertFalse(os.path.normcase(_tmp).startswith(real))  # module-level isolation too


if __name__ == "__main__":
    unittest.main()
