import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AGENT = str(Path(__file__).resolve().parents[1] / "tools" / "avito_operator_agent.py")
NOW = "2026-11-07T12:00:00Z"


def run(task):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "task.json"
        p.write_text(json.dumps(task), encoding="utf-8")
        out = subprocess.check_output([sys.executable, AGENT, "--task-file", str(p), "--now", NOW], text=True)
        return json.loads(out)


def base(**extra):
    value = {
        "task_id": "CAND-006",
        "source": "connect",
        "order_url": "https://connect.tg/orders/example",
        "title": "amoCRM automation",
        "response_text": "Пилот после проверки API.",
        "session_status": "ready",
        "approval": {"allow_send": True, "allow_paid": False, "expires_at": "2026-11-07T13:00:00Z"},
    }
    value.update(extra)
    return value


class OperatorAgentTests(unittest.TestCase):
    def test_free_ready_task_is_submit_ready(self):
        self.assertEqual(run(base())["decision"], "ready_to_submit")

    def test_paid_task_is_blocked_without_explicit_paid_approval(self):
        result = run(base(paid=True))
        self.assertEqual(result["decision"], "blocked_paid")

    def test_expired_session_requires_handoff(self):
        result = run(base(session_status="auth_required"))
        self.assertEqual(result["decision"], "auth_required")

    def test_blocked_session_requires_support_review_not_login_retry(self):
        result = run(base(session_status="blocked"))
        self.assertEqual(result["decision"], "access_restricted")
        self.assertEqual(result["next_action"], "stop_and_request_support_review")

    def test_expired_approval_is_rejected(self):
        result = run(base(approval={"allow_send": True, "allow_paid": False, "expires_at": "2026-11-07T11:00:00Z"}))
        self.assertEqual(result["decision"], "approval_expired")


if __name__ == "__main__":
    unittest.main()
