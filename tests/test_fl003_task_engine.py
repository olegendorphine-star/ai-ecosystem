"""Offline tests of FL-003 task routing, storage, evidence and no-send guarantees."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import fl003_task_engine as engine

class TaskEngineTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.store=engine.Store(Path(self.t.name)/"state.sqlite3")
    def tearDown(self):
        self.store.close()
        self.t.cleanup()
    def test_idempotent_queue(self):
        self.assertTrue(self.store.enqueue("fixture_shop_001","shop_m185"))
        self.assertFalse(self.store.enqueue("fixture_shop_001","shop_m185"))
        self.assertEqual(len(self.store.pending()),1)
    def test_invalid_kind_rejected(self):
        with self.assertRaises(ValueError):self.store.enqueue("x_xx","send_mail")
    def test_offline_shop_waits_for_human(self):
        self.store.enqueue("fixture_shop_002","shop_m185")
        result=engine.execute_tasks(self.store,offline=True)
        self.assertEqual(result,[{"kind":"shop_m185","state":"waiting_human"}])
    def test_mail_docx_produces_unsent_draft(self):
        self.store.enqueue("fixture_mail_001","mail_test")
        result=engine.execute_tasks(self.store,offline=True)
        self.assertEqual(result,[{"kind":"mail_test","state":"draft_ready"}])
        row=self.store.conn.execute("SELECT result_json FROM tasks").fetchone()
        self.assertIn("7 календарных дней",row[0])
        self.assertIn('"sent": false',row[0])
    def test_fake_unsupported_evidence_not_accepted(self):
        p=Path(self.t.name)/"evidence.json"
        p.write_text('{"schema":"fl003.marketplace.manual.evidence.v2","products":{"Ozon":{"price_rub":100}}}')
        os.chmod(p,0o600)
        self.assertIsNone(engine.read_verified_products(p))
    def test_missing_private_telegram_never_creates_tasks(self):
        saved=engine.TELEGRAM_SOCKET
        try:
            engine.TELEGRAM_SOCKET=Path(self.t.name)/"notfound.sock"
            state=engine.read_saved_message_tests(self.store)
            self.assertFalse(state["saved_dialog_verified"])
            self.assertEqual(state["new_test_commands"],0)
        finally:
            engine.TELEGRAM_SOCKET=saved

if __name__=="__main__":
    unittest.main()
