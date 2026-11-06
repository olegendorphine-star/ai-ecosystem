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
                 patch.object(b, "execute", return_value={"bridge": "alive"}):
                out = b.single_pass(dry_run=True, state_file=path)
            self.assertEqual(out["simulated"], 1)
            self.assertEqual(out["posted"], 0)
            self.assertFalse(path.exists())

    def test_single_pass_ignore_old_result(self):
        result = b.make_result(command(), {"bridge": "alive"}, NOW)
        comments = [comment(), {"user": {"login": b.OWNER},
                     "body": b.RESULT_PREFIX + json.dumps(result)}]
        with tempfile.TemporaryDirectory() as d:
            with patch.object(b, "get_issue_comments", return_value=comments), \
                 patch.object(b, "execute", side_effect=AssertionError("must not rerun")):
                self.assertEqual(b.single_pass(dry_run=True, state_file=Path(d)/"state.json")["pending"], 0)


if __name__ == "__main__":
    unittest.main()
