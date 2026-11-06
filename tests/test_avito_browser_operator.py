"""Offline guardrail tests; never contacts Avito or starts a browser."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import avito_browser_operator as op


def good_plan():
    return {
        "purpose": "public-profile",
        "steps": [
            {"action": "fill", "by": "label", "name": "Описание профиля", "value": "Проверенный текст"},
            {"action": "click", "by": "role", "name": "Сохранить"},
        ],
    }


class SafeOperatorTests(unittest.TestCase):
    def test_valid_minimal(self):
        op.validate_plan(good_plan())

    def test_valid_portfolio_image_upload(self):
        op.validate_plan({"purpose": "portfolio", "steps": [
            {"action": "upload", "by": "label", "name": "Загрузить фотографию", "value": "~/Pictures/demo.webp"}
        ]})

    def test_restrict_domain_and_scheme(self):
        for url in ["http://www.avito.ru/profile", "https://www.avito.ru.evil.com/profile",
                    "https://evil.com/", "https://user@www.avito.ru/profile",
                    "https://www.avito.ru:444/profile", "https://www.avito.ru/profile?token=x"]:
            self.assertFalse(op.safe_avito_url(url), url)
        self.assertTrue(op.safe_avito_url("https://www.avito.ru/profile"))

    def test_restrict_payment_messaging_and_security_pages(self):
        for path in ["messenger", "messages", "payment", "pay", "balance", "wallet",
                     "promotion", "security", "password"]:
            self.assertFalse(op.safe_avito_url("https://www.avito.ru/" + path))

    def test_reject_no_steps(self):
        p = good_plan()
        p["steps"] = []
        with self.assertRaises(op.OperatorSafetyError):
            op.validate_plan(p)

    def test_reject_unknown_action(self):
        p = good_plan()
        p["steps"][0]["action"] = "evaluate_javascript"
        with self.assertRaises(op.OperatorSafetyError):
            op.validate_plan(p)

    def test_reject_payment_locator(self):
        p = good_plan()
        p["steps"][1]["name"] = "Купить продвижение"
        with self.assertRaises(op.OperatorSafetyError):
            op.validate_plan(p)

    def test_reject_chat_locator(self):
        p = good_plan()
        p["steps"][1]["name"] = "Отправить сообщение"
        with self.assertRaises(op.OperatorSafetyError):
            op.validate_plan(p)

    def test_reject_bad_purpose(self):
        p = good_plan()
        p["purpose"] = "messenger"
        with self.assertRaises(op.OperatorSafetyError):
            op.validate_plan(p)

    def test_reject_js_or_extra_fields(self):
        p = good_plan()
        p["steps"][0]["eval"] = "alert('bad')"
        with self.assertRaises(op.OperatorSafetyError):
            op.validate_plan(p)

    def test_reject_non_image_upload(self):
        with self.assertRaises(op.OperatorSafetyError):
            op.validate_plan({"purpose": "portfolio", "steps": [
                {"action": "upload", "by": "label", "name": "Добавить файл", "value": "/tmp/.env"}
            ]})

    def test_reject_oversized_plan(self):
        p = good_plan()
        p["steps"] *= 8
        with self.assertRaises(op.OperatorSafetyError):
            op.validate_plan(p)

    def test_reject_ambiguous_unlisted_locator(self):
        p = good_plan()
        p["steps"][0]["by"] = "css"
        with self.assertRaises(op.OperatorSafetyError):
            op.validate_plan(p)

    def test_reject_click_placeholder(self):
        p = good_plan()
        p["steps"][1]["by"] = "placeholder"
        with self.assertRaises(op.OperatorSafetyError):
            op.validate_plan(p)

    def test_reject_destructive_locator(self):
        for phrase in ("Удалить профиль", "Архивировать", "Отправить", "Опубликовать"):
            p = good_plan()
            p["steps"][1]["name"] = phrase
            with self.assertRaises(op.OperatorSafetyError):
                op.validate_plan(p)

    def test_reject_destructive_urls(self):
        for path in ("profile/delete", "profile/billing", "profile/orders"):
            self.assertFalse(op.safe_avito_url("https://www.avito.ru/" + path))

    def test_reject_nonstring_value(self):
        p = good_plan()
        p["steps"][0]["value"] = {"unsafe": True}
        with self.assertRaises(op.OperatorSafetyError):
            op.validate_plan(p)

    def test_reject_huge_value(self):
        p = good_plan()
        p["steps"][0]["value"] = "A" * 4001
        with self.assertRaises(op.OperatorSafetyError):
            op.validate_plan(p)


if __name__ == "__main__":
    unittest.main()
