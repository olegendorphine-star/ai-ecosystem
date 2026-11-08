"""Offline handoff tests: no Playwright process or Avito traffic."""
import importlib.util
import unittest
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "tools" / "avito_browser_handoff.py"
spec = importlib.util.spec_from_file_location("avito_handoff", TARGET)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class HandoffSafetyTests(unittest.TestCase):
    def test_unstarted_browser_cannot_appear_ready(self):
        b = mod.Browser()
        self.assertFalse(b.status()["ok"])
        self.assertEqual(b.status()["startup_error"], "browser_not_ready")

    def test_navigation_without_chromium_returns_clear_error(self):
        b = mod.Browser()
        with self.assertRaisesRegex(RuntimeError, "browser_not_ready"):
            b.navigate("https://www.avito.ru/")

    def test_startup_error_classification_never_returns_paths(self):
        samples = [
            (RuntimeError("Chrome exited: error loading libatk-1.0.so.0 from /home/user/private"), "missing_libatk"),
            (RuntimeError("libother.so: cannot open shared object file"), "missing_shared_library"),
            (RuntimeError("Chrome remote debugging endpoint did not start"), "browser_debugging_unavailable"),
            (RuntimeError("Chrome exited: crash /home/user/private"), "browser_process_exited"),
            (RuntimeError("executable doesn't exist at /home/user/private"), "browser_executable_missing"),
            (RuntimeError("secret path /home/user/private"), "browser_start_failed"),
        ]
        for exception, expected in samples:
            with self.subTest(expected=expected):
                self.assertEqual(mod.startup_error_code(exception), expected)

    def test_live_page_is_required_for_healthy_status(self):
        class Page:
            url = "about:blank"
            def is_closed(self):
                return False
        b = mod.Browser()
        b.page = Page()
        result = b.status()
        self.assertTrue(result["ok"])
        self.assertEqual(result["url"], "about:blank")
        self.assertNotIn("profile", result)
        self.assertNotIn("title", result)

    def test_closed_page_is_not_healthy(self):
        class Page:
            def is_closed(self):
                return True
        b = mod.Browser()
        b.page = Page()
        self.assertFalse(b.status()["ok"])

    def test_avito_ip_error_in_page_is_flagged_without_text_leak(self):
        class Response:
            status = 200
        class Locator:
            def inner_text(self, timeout=None):
                return "Страница не загрузилась из-за проблем с IP"
        class Page:
            url = "https://www.avito.ru/"
            def is_closed(self):
                return False
            def goto(self, url, wait_until=None, timeout=None):
                self.url = url
                return Response()
            def locator(self, selector):
                return Locator()
        b = mod.Browser()
        b.page = Page()
        b.navigate("https://www.avito.ru/")
        result = b.status()
        self.assertTrue(result["ok"])
        self.assertTrue(result["last_navigation_ip_blocked"])
        self.assertEqual(result["last_navigation_http_status"], 200)
        self.assertNotIn("Страница", str(result))



if __name__ == "__main__":
    unittest.main()
