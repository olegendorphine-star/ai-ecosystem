"""Offline acceptance tests for FL-003. No platform sessions or paid API calls."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from fl003_client_demo import create_synthetic_mail, parse_mail, draft_reply, run, best_price

class ClientDemoTests(unittest.TestCase):
    def test_real_docx_attachment_is_parsed_without_ocr(self):
        d = parse_mail(create_synthetic_mail())
        docx = next(a for a in d["attachments"] if a["file"]=="brief.docx")
        self.assertEqual(docx["status"], "parsed_docx")
        self.assertIn("7 календарных дней", docx["summary"])
        self.assertIn("Нужна гарантия", docx["summary"])

    def test_docx_requirements_reach_draft(self):
        mail=parse_mail(create_synthetic_mail())
        shop={"products":[{"marketplace":"Ozon","source_url":"https://www.ozon.ru/product/test/",
                           "price_rub":None,"status":"site_access_or_human_login_required"}]}
        result=draft_reply(mail,shop)
        self.assertIn("7 календарных дней",result["text"])
        self.assertFalse(result["sent"])

    def test_real_csv_attachment_is_decoded(self):
        d = parse_mail(create_synthetic_mail())
        self.assertEqual(d["structured_requirements"][0]["quantity"], 2)
        self.assertEqual(d["structured_requirements"][0]["cap_per_item_rub"], 2000)
        self.assertFalse(d["mail_sent"])
        self.assertFalse(d["mailbox_accessed"])
    def test_unknown_price_is_never_invented(self):
        mail = parse_mail(create_synthetic_mail())
        reply = draft_reply(mail, {"products": [{"marketplace": "Ozon", "source_url": "https://www.ozon.ru/product/example/", "status": "site_access_or_human_login_required", "price_rub": None}]})
        self.assertIn("цена НЕ подтверждена", reply["text"])
        self.assertTrue(reply["approval_required"])
        self.assertFalse(reply["sent"])
    def test_price_requires_rub_currency(self):
        self.assertEqual(best_price({"offers": {"price": 1300, "priceCurrency": "USD"}})[0], None)
        self.assertEqual(best_price({"offers": {"price": 1300, "priceCurrency": "RUB"}})[0], 1300.0)
    def test_offline_produces_draft_not_shop_recommendation(self):
        d = run(offline=True)
        self.assertTrue(d["mail"]["structured_requirements"])
        self.assertFalse(d["shopping"]["full_comparison_verified"])
        self.assertFalse(d["client_facing_full_demo_ready"])
        self.assertEqual(d["external_write_actions"], 0)
        self.assertEqual(d["external_messages_sent"], 0)
        self.assertFalse(d["telegram_connected"])

if __name__ == "__main__":
    unittest.main()
