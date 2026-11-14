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


    def test_confirmed_fifth_id_is_counted_with_response_presence(self):
        from tools.avito_stats_views_report import REPORT_IDS
        self.assertIn(8378846522, REPORT_IDS)
        report=summarize({"result":{"items":[
            {"itemId":8378846522,"stats":[
                {"date":"2026-11-13","views":2,"contacts":1,"favorites":0},
                {"date":"2026-11-14","views":0,"contacts":0,"favorites":1}]}
        ]}})
        fifth=report["8378846522"]
        self.assertEqual(fifth["views"],2)
        self.assertEqual(fifth["contacts"],1)
        self.assertEqual(fifth["favorites"],1)
        self.assertTrue(fifth["response_item_present"])
        self.assertFalse(report["8347570435"]["response_item_present"])
        self.assertIsNone(report["8347570435"]["contacts"])

    def test_no_contacts_is_unknown_and_zero_is_valid(self):
        report=summarize({"result":{"items":[
            {"itemId":8378846522,"stats":[{"date":"2026-11-13","views":0}]},
            {"itemId":8347570435,"stats":[{"date":"2026-11-13","views":0,"contacts":0,"favorites":0}]}]}})
        self.assertIsNone(report["8378846522"]["contacts"])
        self.assertTrue(report["8378846522"]["response_item_present"])
        self.assertEqual(report["8347570435"]["contacts"],0)

    def test_partial_contacts_do_not_create_false_total(self):
        report=summarize({"result":{"items":[{"itemId":8378846522,"stats":[
            {"date":"2026-11-12","views":1,"contacts":2},
            {"date":"2026-11-13","views":1}]}]}})
        self.assertIsNone(report["8378846522"]["contacts"])
        self.assertIsNone(report["8378846522"]["favorites"])

if __name__=="__main__":
    unittest.main()
