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
    def test_only_owner_self_notifications_and_no_resend(self):
        self.assertTrue(self.store.enqueue("tg_mail_synthetic_test","mail_test"))
        engine.execute_tasks(self.store,offline=True)
        previous=engine._telegram_socket_call
        outgoing=[]
        try:
            engine._telegram_socket_call=lambda command:(outgoing.append(command) or {"status":"sent_confirmed"})
            a=engine.notify_own_saved_messages(self.store)
            b=engine.notify_own_saved_messages(self.store)
            self.assertEqual(a["attempted"],1)
            self.assertEqual(b["attempted"],0)
            self.assertEqual(len(outgoing),1)
            self.assertEqual(outgoing[0]["action"],"web_self_note")
            self.assertNotIn("https://",outgoing[0]["params"]["text"])
            self.assertIn("Ничего не отправлено",outgoing[0]["params"]["text"])
        finally:
            engine._telegram_socket_call=previous

    def test_private_saved_messages_intake_ignores_unrelated_content(self):
        orig=engine._telegram_socket_call
        try:
            engine._telegram_socket_call=lambda command:{
                "status":"ok","saved_messages_only":True,
                "messages":[
                    {"message_id":9911,"text":"FL003: ПИСЬМО ТЕСТ"},
                    {"message_id":9912,"text":"личная запись не для агента"},
                    {"message_id":9913,"text":"FL003: ТОВАР M185"}]}
            result=engine.read_saved_message_tests(self.store)
            self.assertEqual(result["status"],"saved_commands_checked")
            self.assertEqual(result["new_test_commands"],2)
            self.assertEqual(len(self.store.pending()),2)
            self.assertEqual(engine.read_saved_message_tests(self.store)["new_test_commands"],0)
        finally:
            engine._telegram_socket_call=orig

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
