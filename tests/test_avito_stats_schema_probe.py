import unittest
from tools.avito_stats_schema_probe import shape

class SchemaTests(unittest.TestCase):
    def test_no_values_or_secret_keys(self):
        value={"result":[{"itemId":8347570435,"views":900,"token":"SECRET",
                         "privatePhone":"79999999999"}]}
        encoded=str(shape(value))
        for secret in ("8347570435","900","SECRET","79999999999","privatePhone"):
            self.assertNotIn(secret,encoded)
        self.assertIn("views",encoded)
    def test_empty(self):
        self.assertEqual(shape([])["length_band"],"0")
    def test_unknown_count(self):
        self.assertEqual(shape({"secret":1,"views":4})["unknown_key_count"],1)

if __name__=="__main__":
    unittest.main()
