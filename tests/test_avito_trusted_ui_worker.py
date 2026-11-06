"""Offline tests for the opt-in read-only trusted machine worker."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import avito_trusted_ui_handoff as contract
import avito_trusted_ui_worker as worker

NOW = dt.datetime(2026, 11, 6, 13, tzinfo=dt.timezone.utc)
REQUEST_ID = "b9f76dc1-68ea-4f10-89f7-6025acfb9b18"


def comment():
    request = {
        "schema": contract.REQUEST_SCHEMA, "request_id": REQUEST_ID,
        "action": "inventory", "purpose": "portfolio",
        "issued_at": (NOW - dt.timedelta(minutes=1)).isoformat(),
        "expires_at": (NOW + dt.timedelta(minutes=5)).isoformat(),
    }
    return {"user": {"login": contract.OWNER_LOGIN, "id": contract.OWNER_USER_ID},
            "body": contract.REQUEST_PREFIX + json.dumps(request)}


def sample_counts():
    return {"schema": contract.INVENTORY_SCHEMA,
            "screen": "owner-selected", "privacy": "category-counts-only",
            "categories": {"portfolio": 2, "profile": 1, "media": 1, "edit": 1},
            "control_types": {"button": 2, "textbox": 1}}


class WorkerOfflineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "session"

    def tearDown(self):
        self.tmp.cleanup()

    def test_private_json_roundtrip(self):
        root = worker.private_root(self.root)
        path = root / "targets.json"
        worker.private_json_write(path, {"portfolio": "https://www.avito.ru/profile/portfolio"})
        self.assertIn("portfolio", worker.read_private_json(path))

    def test_invalid_target_rejected(self):
        for url in ("http://www.avito.ru/profile", "https://example.org/profile",
                    "https://www.avito.ru/profile?x=1"):
            with self.assertRaises(worker.WorkerBlocked):
                worker.valid_targets({"portfolio": url})

    def test_dry_run_never_posts(self):
        with patch.object(worker, "_github_request", side_effect=AssertionError("network unexpected")):
            result = worker.run_once(self.root, comments=[comment()], now=NOW)
        self.assertEqual(result["pending"], 1)
        self.assertEqual(result["posted"], 0)
        self.assertFalse(worker.replay_path(self.root).exists())

    def test_lock_prevents_second_worker_from_processing(self):
        with worker.exclusive_worker_lock(self.root):
            with self.assertRaises(worker.WorkerBlocked):
                worker.run_once(self.root, comments=[comment()], now=NOW)

    def test_lock_prevents_bootstrap_during_processing(self):
        with worker.exclusive_worker_lock(self.root):
            with self.assertRaises(worker.WorkerBlocked):
                worker.bootstrap(self.root, "portfolio")

    def test_lock_released_after_first_run(self):
        with worker.exclusive_worker_lock(self.root):
            pass
        result = worker.run_once(self.root, comments=[comment()], now=NOW)
        self.assertEqual(result["pending"], 1)

    def test_symlink_lock_rejected(self):
        root = worker.private_root(self.root)
        target = root / "legit"
        target.write_text("not a lock", encoding="utf-8")
        try:
            (root / "worker.lock").symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        with self.assertRaises(worker.WorkerBlocked):
            worker.run_once(root, comments=[comment()], now=NOW)

    def test_no_token_no_post(self):
        with self.assertRaises(worker.WorkerBlocked):
            worker.run_once(self.root, dry_run=False, comments=[comment()], now=NOW)

    def test_report_has_only_counts(self):
        posts = []
        def fake_request(url, token=None, body=None):
            posts.append(body["body"])
            return {"id": 123}
        with patch.object(worker, "_github_request", side_effect=fake_request):
            first = worker.run_once(
                self.root, dry_run=False, token="TEST", comments=[comment()], now=NOW,
                enable_browser=True, inventory_fn=lambda _: sample_counts(),
            )
            second = worker.run_once(
                self.root, dry_run=False, token="TEST", comments=[comment()], now=NOW,
                enable_browser=True, inventory_fn=lambda _: sample_counts(),
            )
        self.assertEqual(first["posted"], 1)
        self.assertEqual(second["posted"], 0)
        self.assertEqual(len(posts), 1)
        data = json.loads(posts[0][len(contract.RESULT_PREFIX):])
        self.assertEqual(data["status"], "observed_controls")
        self.assertFalse(data["public_profile_updated"])
        self.assertEqual(data["price_list_visible"], "unverified")

    def test_browser_error_reports_blocked(self):
        posts = []
        with patch.object(worker, "_github_request", side_effect=lambda u, t=None, b=None: posts.append(b["body"]) or {}):
            worker.run_once(
                self.root, dry_run=False, token="TEST", comments=[comment()], now=NOW,
                enable_browser=True, inventory_fn=lambda _: (_ for _ in ()).throw(RuntimeError("offline error")),
            )
        self.assertIn("no_verified_session", posts[0])

    def test_other_user_ignored(self):
        foreign = comment()
        foreign["user"]["id"] = 101
        result = worker.run_once(self.root, comments=[foreign], now=NOW)
        self.assertEqual(result["pending"], 0)

    def test_invalid_github_target_rejected(self):
        with self.assertRaises(worker.WorkerBlocked):
            worker._github_request("https://example.org/")


if __name__ == "__main__":
    unittest.main()
