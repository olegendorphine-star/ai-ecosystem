import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

WORKER_PATH = Path(__file__).resolve().parents[1] / "tools" / "avito_server_worker.py"
spec = importlib.util.spec_from_file_location("worker", WORKER_PATH)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WorkerTests(unittest.TestCase):
    def test_health_is_read_only_shape(self):
        result = worker.health()
        self.assertEqual(result["action"], "health")
        self.assertTrue(result["ok"])
        self.assertIn("disk_free_bytes", result)

    def test_browser_health_does_not_require_profile(self):
        os.environ.pop("AVITO_BROWSER_PROFILE_DIR", None)
        result = worker.browser_health()
        self.assertFalse(result["profile_configured"])

    def test_connect_status_has_no_write_action(self):
        worker.http_status = lambda url: 200
        result = worker.connect_status()
        self.assertFalse(result["write_actions"])


if __name__ == "__main__":
    unittest.main()
