import unittest
from tools.avito_offline_feed_audit import audit


def feed(ads):
    return ("<Ads>" + ads + "</Ads>").encode()


def ad(ident, city, prices=(5000, 30000, 150000), images=6):
    return (f"<Ad><Id>{ident}</Id><Address>{city}</Address>"
            "<Title>ИИ-ассистент</Title><WorkingWithAI>Да</WorkingWithAI>"
            "<PriceList>" + "".join(f"<Service><ServicePrice>{p}</ServicePrice></Service>" for p in prices)
            + "</PriceList><Images>" + "<Image/>" * images + "</Images></Ad>")


class OfflineAuditTests(unittest.TestCase):
    def test_all_four_known_ads(self):
        names = [
            ("ai-assistant-memory-moscow-001", "Москва"),
            ("ai-assistant-memory-spb-001", "Санкт-Петербург"),
            ("ai-assistant-memory-surgut-001", "Сургут"),
            ("ai-assistant-memory-chita-001", "Чита"),
        ]
        result = audit(feed("".join(ad(*n) for n in names)))
        self.assertEqual(result["issues"], [])
        self.assertFalse(result["safe_to_propose_migration"])

    def test_duplicate_and_missing_ads(self):
        result = audit(feed(ad("ai-assistant-memory-moscow-001", "Москва") * 2))
        self.assertIn("missing_or_duplicate_id", result["issues"])
        self.assertIn("expected_exactly_four_known_ads", result["issues"])

    def test_wrong_prices_and_images(self):
        result = audit(feed(ad("ai-assistant-memory-moscow-001", "Москва", (5000,), 0)))
        self.assertIn("unexpected_price_tiers", result["issues"])
        self.assertIn("unexpected_image_count", result["issues"])

    def test_wrong_root(self):
        with self.assertRaises(ValueError):
            audit(b"<Other/>")


if __name__ == "__main__":
    unittest.main()
