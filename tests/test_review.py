import json
import os
import tempfile
import threading
import unittest
from unittest import mock

import review

FUTURE = "2999-01-01T00:00:00+00:00"
PAST = "2000-01-01T00:00:00+00:00"
BAD = "That code isn't valid or has expired"


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


if __name__ == "__main__":
    unittest.main()
