import unittest
from tools.avito_offline_metrics import COLUMNS, parse, summarize


def row(**updates):
    base = dict.fromkeys(COLUMNS, "")
    base.update(date="2026-11-11",ad_id="8347570435",city="Москва")
    base.update(updates)
    return base


class MetricsTests(unittest.TestCase):
    def test_blank_is_not_zero(self):
        records, errors = parse([row(views="0")])
        self.assertEqual(errors, [])
        s = summarize(records)["listing_summaries"][0]
        self.assertIsNone(s["totals"]["impressions"])
        self.assertEqual(s["totals"]["views"], 0)
        self.assertIsNone(s["ctr"])

    def test_aggregate_numerators_before_rates(self):
        records, errors = parse([row(impressions="100",views="20",contacts="2"),
            row(date="2026-11-12",impressions="300",views="30",contacts="3")])
        self.assertEqual(errors, [])
        s = summarize(records)["listing_summaries"][0]
        self.assertAlmostEqual(s["ctr"], 50/400)
        self.assertAlmostEqual(s["view_to_contact"], 5/50)

    def test_partial_coverage_blocks_rate(self):
        records, errors = parse([row(impressions="100",views="20"),
            row(date="2026-11-12",impressions="200")])
        self.assertEqual(errors, [])
        self.assertIsNone(summarize(records)["listing_summaries"][0]["ctr"])

    def test_reject_duplicate(self):
        _, errors = parse([row(),row()])
        self.assertIn("duplicate",errors[0])

    def test_reject_invalid_money_and_counts(self):
        _, errors = parse([row(ad_spend_rub="-1"),row(date="2026-11-12",contacts="1.5")])
        self.assertEqual(len(errors),2)

    def test_reject_wrong_city(self):
        _, errors = parse([row(city="Чита")])
        self.assertIn("city mismatch",errors[0])

    def test_empty(self):
        self.assertTrue(summarize([])["no_data"])


if __name__ == "__main__":
    unittest.main()
