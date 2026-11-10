import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from fl003_retail_fallback import classify,selftest

class RetailFallbackTests(unittest.TestCase):
    def test_main_price_not_cross_sells(self):
        sample=("Войдите — цена станет ниже\n1 014 ₽ 2 990 ₽\n"
                "В корзину\nЗавтра,склад продавца\nООО «МАГ ДЕВАЙС»\n"
                "Защитим покупку 202 ₽\nРекомендуем 100 ₽")
        x=classify("MVideo","Мышь Logitech M185 Black",sample,200)
        self.assertEqual(x["price_rub"],1014)
        self.assertEqual(x["status"],"price_and_orderability_seen_on_public_page")
    def test_out_of_stock_not_assumed_price(self):
        r=classify("KNS","Мышь Logitech M185",
                   "Последняя цена: 1 193 руб. Наличие: Нет в наличии",200)
        self.assertEqual(r["status"],"not_available")
        self.assertIsNone(r["price_rub"])
    def test_blocked_site_not_called_live_price(self):
        self.assertEqual(classify("MVideo","Мышь Logitech M185","Доступ ограничен",200)["status"],"access_challenge_detected")
        self.assertEqual(classify("MVideo","Мышь Logitech M185","",403)["status"],"http_access_blocked_or_error")
    def test_no_communication(self):
        self.assertEqual(selftest()["outbound_messages"],0)
if __name__=="__main__":unittest.main()
