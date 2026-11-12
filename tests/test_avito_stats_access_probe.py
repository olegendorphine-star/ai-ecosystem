import unittest
from tools.avito_stats_access_probe import stats_path

class StatsProbeTests(unittest.TestCase):
    def test_v1(self):
        self.assertEqual(stats_path("v1",123),"/stats/v1/accounts/123/items")
    def test_v2(self):
        self.assertEqual(stats_path("v2",123),"/stats/v2/accounts/123/items")
    def test_reject_unsafe(self):
        for version,ident in [("v3",123),("v1","123/vas"),("v2","foo")]:
            with self.assertRaises(ValueError):
                stats_path(version,ident)

if __name__ == "__main__":
    unittest.main()
