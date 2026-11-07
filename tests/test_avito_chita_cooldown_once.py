"""Validate the sole post-429 Chita package upload schedule offline."""
import ast
import re
import textwrap
import unittest
from pathlib import Path


class ChitaCooldownOnceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=Path(__file__).resolve().parents[1] / ".github/workflows/avito-chita-cooldown-once-2026-11-07.yml"
        cls.body=p.read_text(encoding="utf-8")
        found=re.search(r"          python3 - <<'PY'\n(.*?)\n          PY",cls.body,re.S)
        assert found
        cls.code=textwrap.dedent(found.group(1))

    def test_script_syntax(self):
        ast.parse(self.code)

    def test_schedule_after_cooldown_only(self):
        self.assertIn("cron: '40 7 7 11 *'",self.body)
        self.assertIn("github.event_name == 'schedule'",self.body)
        self.assertIn("github.run_attempt == 1",self.body)
        self.assertNotIn("\n  workflow_dispatch:",self.body)
        self.assertNotIn("\n  push:",self.body)
        self.assertIn("now().date().isoformat()!='2026-11-07'",self.code)
        self.assertIn("datetime.datetime(2026,11,7,7,40",self.code)
        self.assertIn("STOP_EXPIRED_OR_NOT_SCHEDULED_COOLDOWN",self.code)

    def test_one_post_frozen_feed_and_no_promotion(self):
        self.assertEqual(self.code.count("api+'/autoload/v1/upload'"),1)
        self.assertIn("0118661e27aa4aab5b8db5a306d84e05c526924b",self.code)
        self.assertIn("x.findtext('ListingFee')=='Package'",self.code)
        self.assertIn("x.findtext('AdStatus')=='Free'",self.code)
        self.assertIn("STOP_LAST_MINUTE_UPLOAD_CHANGED",self.code)
        self.assertIn("STOP_CURRENT_ITEMS_HTTP",self.code)
        self.assertIn("STOP_CHITA_ALREADY_IN_AUTOLOAD_NO_SECOND_POST",self.code)
        for prohibited in ("/vas/","/promo/","/payment/","/messenger/"):
            self.assertNotIn(prohibited,self.code)

    def test_post_only_counted_as_confirmed_with_active_id_correlated(self):
        self.assertIn("slug=='success_published'",self.code)
        self.assertIn("str(item_id)==str(found.get('id'))",self.code)
        self.assertIn("CHITA_CONFIRMED_ACTIVE",self.code)
        self.assertIn("CHITA_PUBLICATION_PENDING_UNCONFIRMED_NO_RETRY",self.code)


if __name__ == "__main__":
    unittest.main()
