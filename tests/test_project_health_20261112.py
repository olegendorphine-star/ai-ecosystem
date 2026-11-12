"""Current production feed, failure classification and auth regressions."""
import copy
import datetime as dt
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
import yaml
from tools import avito_spb_pricelist_live_status as live
from tools import avito_github_bridge_worker as bridge
from tools import avito_offline_feed_audit as offline
from tools import yandex_wordstat_bridge as wordstat

ROOT = Path(__file__).resolve().parents[1]


class ProjectHealthTests(unittest.TestCase):
    def test_workflows_have_no_duplicate_mapping_keys(self):
        class Unique(yaml.SafeLoader):
            pass
        def mapping(loader, node, deep=False):
            result = {}
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node, deep=deep)
                if key in result:
                    raise ValueError(f"Duplicate key {key} at line {key_node.start_mark.line + 1}")
                result[key] = loader.construct_object(value_node, deep=deep)
            return result
        Unique.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            with self.subTest(workflow=path.name):
                yaml.load(path.read_text(), Loader=Unique)

    def setUp(self):
        self.raw = (ROOT / "docs/avito-feed.xml").read_bytes()
        self.root = ET.fromstring(self.raw)

    def test_current_five_ads_pass_both_validators(self):
        self.assertEqual(len(self.root.findall("Ad")), 5)
        self.assertTrue(all(live.feed_check(self.raw).values()))
        self.assertEqual(offline.audit(self.raw)["issues"], [])

    def test_original_four_ads_are_unchanged(self):
        expected = ET.parse(ROOT / "reference/avito-seo-proposal-2026-11-10.xml").getroot()
        def normalized(e):
            return e.tag, sorted(e.attrib.items()), (e.text or "").strip(), [normalized(c) for c in e]
        self.assertEqual([normalized(e) for e in self.root.findall("Ad")[:4]],
                         [normalized(e) for e in expected.findall("Ad")])

    def test_unreviewed_duplicate_missing_and_paid_ads_fail_closed(self):
        for mutation in ("unknown", "duplicate", "missing", "paid", "extra_price", "bad_image"):
            root = copy.deepcopy(self.root)
            fifth = root.findall("Ad")[-1]
            if mutation == "unknown": fifth.find("Id").text = "unexpected-ad"
            if mutation == "duplicate": root.append(copy.deepcopy(fifth))
            if mutation == "missing": root.remove(root.findall("Ad")[0])
            if mutation == "paid": ET.SubElement(fifth, "Promotion").text = "XL"
            if mutation == "extra_price": ET.SubElement(fifth, "PriceList")
            if mutation == "bad_image": fifth.find("./Images/Image").set("url", "https://untrusted.invalid/a.png")
            with self.subTest(mutation=mutation):
                self.assertFalse(all(live.feed_check(ET.tostring(root)).values()))

    def test_feed_mismatch_is_not_oauth_failure_and_never_calls_oauth(self):
        self.root.findall("Ad")[-1].find("Price").text = "1"
        with patch.object(live, "http", return_value=(200, ET.tostring(self.root))) as api:
            raw = live.inspect()
        api.assert_called_once_with(live.FEED)
        self.assertEqual(raw["api_check_status"], "skipped_feed_mismatch")
        safe = bridge.sanitize_live_api_report(raw)
        self.assertEqual(safe["result"], "skipped")
        self.assertIsNone(safe["oauth_ok"])

    def test_actual_oauth_denial_remains_false(self):
        with patch.dict("os.environ", {"AVITO_CLIENT_ID": "fake", "AVITO_CLIENT_SECRET": "fake"}):
            with patch.object(live, "http", side_effect=[(200, self.raw), (403, None)]):
                result = live.inspect()
        self.assertFalse(result["oauth_ok"])
        self.assertEqual(result["api_check_status"], "oauth_attempted")

    def test_only_actual_api_checks_consume_cooldown(self):
        now = dt.datetime.now(dt.timezone.utc)
        def comment(detail):
            return {"user": {"login": "github-actions[bot]"}, "body": bridge.RESULT_PREFIX + json.dumps({
                "schema": bridge.RESULT_SCHEMA, "action": "check_live_avito_api",
                "checked_at": now.isoformat(), "detail": detail})}
        skipped = comment({"result": "checked", "feed_integrity_ok": False, "oauth_ok": False})
        self.assertFalse(bridge.has_recent_api_check([skipped], now))
        actual = comment({"result": "checked", "feed_integrity_ok": True,
                          "oauth_ok": True, "http": {"active_items": 429}})
        self.assertTrue(bridge.has_recent_api_check([actual], now))

    def test_regions_uses_key_folder_without_legacy_override_or_paid_call(self):
        with patch.object(wordstat, "request_json", return_value={"regions": []}) as api:
            result = wordstat.call_wordstat({"action": "regions"}, "fake", "wrong-legacy-folder", False)
        self.assertEqual(api.call_args.args[2], {})
        self.assertTrue(api.call_args.args[0].endswith("getRegionsTree"))
        self.assertFalse(result["billable"])


if __name__ == "__main__":
    unittest.main()
