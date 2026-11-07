"""Offline safety gate for the once-only 2026-11-07 Chita publication workflow."""
import ast
import re
import textwrap
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "avito-chita-owner-upload-2026-11-07.yml"
FEED = ROOT / "docs" / "avito-feed.xml"
STABLE_IDS = ["ai-assistant-memory-moscow-001",
              "ai-assistant-memory-spb-001",
              "ai-assistant-memory-surgut-001",
              "ai-assistant-memory-chita-001"]


class ChitaAuthorizedOnceSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.yaml = WORKFLOW.read_text(encoding="utf-8")
        found = re.search(r"          python3 - <<'PY'\n(.*?)\n          PY", cls.yaml, re.S)
        assert found, "expected a single bounded Python preflight script"
        cls.script = textwrap.dedent(found.group(1))

    def test_inline_python_compiles(self):
        ast.parse(self.script, filename=str(WORKFLOW))

    def test_only_owner_approved_main_push_first_attempt(self):
        self.assertIn("github.event_name == 'push'", self.yaml)
        self.assertIn("github.ref == 'refs/heads/main'", self.yaml)
        self.assertIn("github.run_attempt == 1", self.yaml)
        self.assertIn("RUN_ONCE_CHITA_PACKAGE_2026_11_07", self.yaml)
        self.assertNotIn("\n  schedule:", self.yaml)
        self.assertNotIn("\n  workflow_dispatch:", self.yaml)
        self.assertIn("STOP_NOT_EXACT_OWNER_AUTHORIZED_COMMIT", self.script)
        self.assertIn("STOP_FROZEN_FEED_CHANGED", self.script)

    def test_only_one_autoload_post_and_no_paid_endpoints(self):
        self.assertEqual(self.script.count("api+'/autoload/v1/upload'"), 1)
        self.assertIn("data=b'{}'", self.script)
        self.assertIn("ONE_SAFE_PACKAGE_UPLOAD_START", self.script)
        self.assertIn("STOP_LAST_MINUTE_UPLOAD_CHANGED", self.script)
        for forbidden in ("core/v2/items", "/vas/", "/payment/", "/promo/",
                          "messenger/", "charges/"):
            self.assertNotIn(forbidden, self.script)

    def test_four_city_package_only_unmodified_feed(self):
        ads = ET.parse(FEED).getroot().findall("Ad")
        self.assertEqual([a.findtext("Id") for a in ads], STABLE_IDS)
        self.assertEqual([a.findtext("Address") for a in ads],
                         ["Москва", "Санкт-Петербург", "Сургут", "Чита"])
        self.assertEqual(ads[0].findtext("AvitoId"), "8347570435")
        self.assertIsNone(ads[3].find("AvitoId"))
        for a in ads:
            self.assertEqual(a.findtext("Price"), "5000")
            self.assertEqual(a.findtext("ListingFee"), "Package")
            self.assertEqual(a.findtext("AdStatus"), "Free")
            self.assertIsNone(a.find("Promo"))
            self.assertEqual(len(a.findall("./Images/Image")), 6)

    def test_success_requires_matching_current_item_and_active_card(self):
        self.assertIn("slug=='success_published'", self.script)
        self.assertIn("str(item_id)==str(found.get('id'))", self.script)
        self.assertIn("CHITA_PUBLICATION_PENDING_UNCONFIRMED_NO_RETRY", self.script)
        self.assertIn("STOP_CHITA_ALREADY_IN_AUTOLOAD_NO_SECOND_POST", self.script)
        self.assertIn("STOP_POSSIBLE_CHITA_ALREADY_ACTIVE_RECHECK", self.script)


if __name__ == "__main__":
    unittest.main()
