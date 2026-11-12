import unittest
from tools.avito_stats_views_report import summarize

class ViewsTests(unittest.TestCase):
    def test_sum_and_zero(self):
        result=summarize({"result":{"items":[{"itemId":8347570435,"stats":[
            {"date":"2026-11-10","views":3},{"date":"2026-11-11","views":0}]}]}})
        self.assertEqual(result["8347570435"]["views"],3)
        self.assertEqual(result["8347570435"]["days"],2)
        self.assertEqual(result["8347570435"]["daily"]["2026-11-11"],0)
        self.assertEqual(result["8414224003"]["daily"],{})
        self.assertEqual(result["8414224003"]["days"],0)
    def test_missing_not_zero(self):
        with self.assertRaises(ValueError):
            summarize({"result":{"items":[{"itemId":8347570435,"stats":[{"date":"2026-11-11"}]}]}})
    def test_duplicate(self):
        with self.assertRaises(ValueError):
            summarize({"result":{"items":[{"itemId":8347570435,"stats":[
                {"date":"2026-11-11","views":1},{"date":"2026-11-11","views":2}]}]}})
    def test_invalid(self):
        for value in [-1,True,"5"]:
            with self.assertRaises(ValueError):
                summarize({"result":{"items":[{"itemId":8347570435,"stats":[
                    {"date":"2026-11-11","views":value}]}]}})

if __name__=="__main__":
    unittest.main()
