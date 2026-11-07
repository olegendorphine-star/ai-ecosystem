"""Offline regression tests for public, read-only GitHub-to-server transport."""
import datetime as dt
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import avito_github_bridge_worker as b

NOW = dt.datetime(2026, 11, 6, 8, 0, tzinfo=dt.timezone.utc)


def command(action="ping"):
    return {"schema": b.SCHEMA, "command_id": str(uuid.UUID("abdf18b6-fc1b-44ed-a073-88f06315e6d2")),
            "action": action, "issued_at": "2026-11-06T07:58:00+00:00",
            "expires_at": "2026-11-06T08:12:00+00:00"}


def comment(cmd=None, user=b.OWNER):
    return {"user": {"login": user},
            "body": b.COMMAND_PREFIX + json.dumps(cmd if cmd is not None else command())}


def xml_source(spb_prices=("5000", "30000", "150000")):
    prices = "".join("<Service><ServicePrice>" + p + "</ServicePrice></Service>" for p in spb_prices)
    images = "<Images>" + "<Image url='https://example.org/img.jpg'/>" * 6 + "</Images>"
    return ("<Ads><Ad><Id>ai-assistant-memory-moscow-001</Id>" + images + "</Ad>"
            "<Ad><Id>ai-assistant-memory-spb-001</Id>"
            "<PriceList>" + prices + "</PriceList>" + images + "</Ad></Ads>").encode()


class ValidationTests(unittest.TestCase):
    def test_allowlisted_command(self):
        self.assertEqual(b.validate_command(command(), NOW)["action"], "ping")

    def test_reject_shell(self):
        with self.assertRaises(b.InvalidCommand):
            b.validate_command(command("shell"), NOW)

    def test_reject_publish(self):
        with self.assertRaises(b.InvalidCommand):
            b.validate_command(command("publish_ad"), NOW)

    def test_reject_api_write(self):
        with self.assertRaises(b.InvalidCommand):
            b.validate_command(command("edit_profile"), NOW)

    def test_reject_extra_parameters(self):
        c = command()
        c["shell"] = "echo danger"
        with self.assertRaises(b.InvalidCommand):
            b.validate_command(c, NOW)

    def test_reject_stale(self):
        with self.assertRaises(b.InvalidCommand):
            b.validate_command(command(), NOW + dt.timedelta(hours=1))

    def test_reject_future(self):
        with self.assertRaises(b.InvalidCommand):
            b.validate_command(command(), NOW - dt.timedelta(hours=1))

    def test_reject_excess_ttl(self):
        c = command()
        c["expires_at"] = "2026-11-06T10:58:00+00:00"
        with self.assertRaises(b.InvalidCommand):
            b.validate_command(c, NOW)

    def test_reject_invalid_id(self):
        c = command()
        c["command_id"] = "run shell"
        with self.assertRaises(b.InvalidCommand):
            b.validate_command(c, NOW)

    def test_reject_invalid_schema(self):
        c = command()
        c["schema"] = "unknown"
        with self.assertRaises(b.InvalidCommand):
            b.validate_command(c, NOW)

    def test_reject_timestamp_without_timezone(self):
        c = command()
        c["issued_at"] = "2026-11-06T07:58:00"
        with self.assertRaises(b.InvalidCommand):
            b.validate_command(c, NOW)

    def test_reject_foreign_comment_author(self):
        self.assertIsNone(b.parse_owner_command(comment(user="randomuser"), NOW))

    def test_accept_owner_comment(self):
        self.assertEqual(b.parse_owner_command(comment(), NOW)["action"], "ping")

    def test_ignores_noncommand(self):
        self.assertIsNone(b.parse_owner_command({"user": {"login": b.OWNER}, "body": "hello"}, NOW))

    def test_result_dedup_only_owner(self):
        result = b.make_result(command(), {"bridge": "alive"}, NOW)
        body = b.RESULT_PREFIX + json.dumps(result)
        self.assertEqual(b.seen_completed_results([
            {"user": {"login": "fake"}, "body": body}
        ]), set())
        self.assertEqual(b.seen_completed_results([
            {"user": {"login": b.OWNER}, "body": body}
        ]), {command()["command_id"]})

    def test_result_dedup_github_bot(self):
        result = b.make_result(command(), {"bridge": "alive"}, NOW)
        body = b.RESULT_PREFIX + json.dumps(result)
        self.assertEqual(b.seen_completed_results([
            {"user": {"login": "github-actions[bot]"}, "body": body}
        ]), {command()["command_id"]})

    def test_feed_good(self):
        flags = b.check_feed_xml(xml_source())
        self.assertTrue(all(flags.values()))

    def test_feed_bad_price(self):
        flags = b.check_feed_xml(xml_source(spb_prices=("5000", "35000", "150000")))
        self.assertFalse(flags["spb_three_prices"])

    def test_ping_does_not_call_network(self):
        with patch.object(b, "request", side_effect=AssertionError("unexpected network")):
            self.assertEqual(b.execute("ping")["bridge"], "alive")

    def test_public_feed_uses_fixed_url(self):
        with patch.object(b, "request", return_value=(200, xml_source())) as mock:
            self.assertEqual(b.execute("check_public_feed")["feed_validation"], "match")
            self.assertEqual(mock.call_args.args, (b.FEED_URL,))

    def test_public_avito_probe_fixed_url(self):
        with patch.object(b, "request", return_value=(403, b"")) as mock:
            out = b.execute("check_avito_public_access")
            self.assertFalse(out["reachable"])
            self.assertEqual(out["http_status"], 403)
            self.assertEqual(mock.call_args.args, (b.AVITO_URL,))

    def test_restrict_post_to_github(self):
        with self.assertRaises(ValueError):
            b.request(b.AVITO_URL, token="not-real", post={"body": "unsafe"})

    def test_state_idempotency(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            b.save_state(path, {command()["command_id"]})
            self.assertEqual(b.load_state(path), {command()["command_id"]})

    def test_single_pass_dry_run_no_post(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "no-state.json"
            with patch.object(b, "get_issue_comments", return_value=[comment()]), \
                 patch.object(b, "utcnow", return_value=NOW), \
                 patch.object(b, "execute", return_value={"bridge": "alive"}):
                out = b.single_pass(dry_run=True, state_file=path)
            self.assertEqual(out["simulated"], 1)
            self.assertEqual(out["posted"], 0)
            self.assertFalse(path.exists())

    def test_single_pass_deduplicates_repeated_command(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(b, "get_issue_comments", return_value=[comment(), comment()]), \
                 patch.object(b, "utcnow", return_value=NOW), \
                 patch.object(b, "execute", return_value={"bridge": "alive"}) as execute:
                out = b.single_pass(dry_run=True, state_file=Path(d)/"state.json")
                self.assertEqual(out["simulated"], 1)
                execute.assert_called_once()

    def test_live_api_action_allowed_but_write_still_blocked(self):
        self.assertEqual(b.validate_command(command("check_live_avito_api"), NOW)["action"],
                         "check_live_avito_api")
        with self.assertRaises(b.InvalidCommand):
            b.validate_command(command("avito_publish"), NOW)

    def test_live_report_never_leaks_secrets(self):
        raw = {"oauth_ok": True, "public_feed_http": 200,
               "public_feed": {"two_ads": True, "spb_three_prices": True},
               "secret": "TOP_SECRET_VALUE", "token": "TOP_SECRET_VALUE",
               "active_items": {"moscow_active": True, "spb_active": True,
                                "phone": "TOP_SECRET_VALUE",
                                "spb_public_url": "https://private.invalid"},
               "current_upload": {"upload_status": "success", "spb_section": "success_published",
                                  "upload_id": 123456789, "private_id": "TOP_SECRET_VALUE"},
               "http": {"active_items": 200, "current_upload": 200, "current_items": 429},
               "current_items_check": "rate_limited"}
        safe = b.sanitize_live_api_report(raw)
        self.assertTrue(safe["spb_active"])
        self.assertTrue(safe["moscow_active"])
        self.assertEqual(safe["current_items_check"], "rate_limited")
        self.assertEqual(safe["price_list_visible_on_public_ad"], "unverified")
        self.assertNotIn("TOP_SECRET_VALUE", json.dumps(safe))
        self.assertNotIn("123456789", json.dumps(safe))
        self.assertNotIn("private.invalid", json.dumps(safe))

    def test_live_report_restricts_http_and_status_fields(self):
        report = {"oauth_ok": False, "public_feed_http": "SECRET",
                  "http": {"active_items": "SECRET", "current_items": 429},
                  "current_upload": {"upload_status": "SECRET",
                                     "spb_section": "SECRET"}}
        safe = b.sanitize_live_api_report(report)
        self.assertEqual(safe["upload_status"], "unknown")
        self.assertEqual(safe["spb_section"], "unknown")
        self.assertIsNone(safe["http"]["active_items"])
        self.assertNotIn("SECRET", json.dumps(safe))

    def test_live_api_execution_calls_existing_read_only_inspector(self):
        import avito_spb_pricelist_live_status as live
        with patch.object(live, "inspect", return_value={
             "oauth_ok": True, "active_items": {
                 "moscow_active": True, "spb_active": True
             }, "user": "SECRET"
        }) as mock:
            result = b.execute("check_live_avito_api")
        mock.assert_called_once()
        self.assertEqual(result["result"], "checked")
        self.assertTrue(result["spb_active"])
        self.assertNotIn("SECRET", json.dumps(result))

    def test_live_api_error_returns_no_exception_content(self):
        import avito_spb_pricelist_live_status as live
        with patch.object(live, "inspect", side_effect=RuntimeError("TOKEN_SECRET")):
            result = b.execute("check_live_avito_api")
        self.assertEqual(result["result"], "unavailable")
        self.assertNotIn("TOKEN_SECRET", json.dumps(result))

    def test_live_api_cooldown(self):
        result = b.make_result(command("check_live_avito_api"),
                               {"result": "checked"}, NOW)
        body = b.RESULT_PREFIX + json.dumps(result)
        comments = [{"user": {"login": "github-actions[bot]"}, "body": body}]
        self.assertTrue(b.has_recent_api_check(comments, NOW + dt.timedelta(minutes=30)))
        self.assertFalse(b.has_recent_api_check(comments, NOW + dt.timedelta(minutes=61)))

    def test_live_api_cooldown_blocks_repeat_execute(self):
        now = NOW
        last = b.make_result(command("check_live_avito_api"),
                             {"result": "checked"}, now)
        recent_result = {"user": {"login": "github-actions[bot]"},
                         "body": b.RESULT_PREFIX + json.dumps(last)}
        new_command = command("check_live_avito_api")
        new_command["command_id"] = str(uuid.uuid4())
        comments = [recent_result, comment(new_command)]
        with tempfile.TemporaryDirectory() as d:
            with patch.object(b, "get_issue_comments", return_value=comments), \
                 patch.object(b, "utcnow", return_value=NOW + dt.timedelta(minutes=5)), \
                 patch.object(b, "execute", side_effect=AssertionError("should not run")):
                with patch("builtins.print"):
                    result = b.single_pass(dry_run=True, state_file=Path(d)/"state.json")
        self.assertEqual(result["simulated"], 1)

    def test_single_pass_ignore_old_result(self):
        result = b.make_result(command(), {"bridge": "alive"}, NOW)
        comments = [comment(), {"user": {"login": b.OWNER},
                     "body": b.RESULT_PREFIX + json.dumps(result)}]
        with tempfile.TemporaryDirectory() as d:
            with patch.object(b, "get_issue_comments", return_value=comments), \
                 patch.object(b, "utcnow", return_value=NOW), \
                 patch.object(b, "execute", side_effect=AssertionError("must not rerun")):
                self.assertEqual(b.single_pass(dry_run=True, state_file=Path(d)/"state.json")["pending"], 0)



    def test_chita_public_result_requires_confirmed_matching_canonical_url(self):
        from copy import deepcopy
        raw = {"oauth_ok": True, "chita_confirmed_active": True,
               "active_items": {"chita_candidate_active": True, "surgut_active": True,
                                "chita_public_ad_id": 8531999999,
                                "chita_public_url": "https://www.avito.ru/chita/test_8531999999?secret=PRIVATE"},
               "current_upload": {"upload_status": "success",
                                  "chita_in_current_items": True,
                                  "chita_section": "success_published"}}
        ok = b.sanitize_live_api_report(raw)
        self.assertTrue(ok["surgut_active"])
        self.assertTrue(ok["chita_confirmed_active"])
        self.assertEqual(ok["chita_public_ad_id"], 8531999999)
        self.assertEqual(ok["chita_public_url"], "https://www.avito.ru/chita/test_8531999999")
        self.assertNotIn("PRIVATE", json.dumps(ok))
        unconfirmed = deepcopy(raw)
        unconfirmed["chita_confirmed_active"] = False
        safe = b.sanitize_live_api_report(unconfirmed)
        self.assertFalse(safe["chita_confirmed_active"])
        self.assertNotIn("chita_public_url", safe)
        invalid = deepcopy(raw)
        invalid["active_items"]["chita_public_url"] = "https://other.example/chita/test_8531999999"
        self.assertFalse(b.sanitize_live_api_report(invalid)["chita_confirmed_active"])

if __name__ == "__main__":
    unittest.main()
