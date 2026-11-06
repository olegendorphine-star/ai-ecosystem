#!/usr/bin/env python3
"""Opt-in trusted-machine UI worker for Avito. Strictly read-only.

NOT a GitHub Actions job and NOT an account login bot. Bootstrap a trusted
local Chromium session interactively as the owner. Commands are read from a
public GitHub issue but never include private content. Only pre-approved local
Avito pages may be inventoried; public reports contain counts, not values.
This code never edits Avito, sends messages, publishes ads or handles payments.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import stat
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from contextlib import contextmanager
from typing import Any

import avito_browser_operator as browser
import avito_trusted_ui_handoff as handoff

API = "https://api.github.com"
REPOSITORY = "olegendorphine-star/ai-ecosystem"
ISSUE = 32
COMMENTS_URL = f"{API}/repos/{REPOSITORY}/issues/{ISSUE}/comments"
DEFAULT_ROOT = Path.home() / ".local" / "share" / "avito-trusted-ui"
MAX_BODY = 1_000_000
MAX_PAGES = 10
OWNER_USER_ID = handoff.OWNER_USER_ID


class WorkerBlocked(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise WorkerBlocked("GitHub redirect refused")


def private_root(root: Path) -> Path:
    root = root.expanduser()
    if root.exists() and root.is_symlink():
        raise WorkerBlocked("symlink session root prohibited")
    resolved = root.resolve()
    if resolved.exists() and not resolved.is_dir():
        raise WorkerBlocked("session root is not a directory")
    resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        resolved.chmod(0o700)
    return resolved


def private_json_write(path: Path, document: dict | list) -> None:
    if path.exists() and path.is_symlink():
        raise WorkerBlocked("symlink state file prohibited")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-avito-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as dest:
            json.dump(document, dest, ensure_ascii=False, sort_keys=True)
            dest.flush()
            os.fsync(dest.fileno())
        os.replace(tmp_name, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def read_private_json(path: Path) -> Any:
    if not path.is_file() or path.is_symlink():
        raise WorkerBlocked("private state is missing or a link")
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise WorkerBlocked("private state permissions are too broad")
    if path.stat().st_size > 20000:
        raise WorkerBlocked("private state too large")
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def exclusive_worker_lock(root: Path):
    """One owner session and command processor per private root on Linux."""
    if os.name != "posix":
        raise WorkerBlocked("trusted worker lock requires POSIX")
    root = private_root(root)
    lock_path = root / "worker.lock"
    if lock_path.is_symlink():
        raise WorkerBlocked("lock path must not be a symlink")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(lock_path, flags, 0o600)
    try:
        if stat.S_IMODE(os.fstat(fd).st_mode) & 0o077:
            raise WorkerBlocked("lock permissions are too broad")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WorkerBlocked("another worker owns the session") from exc
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def target_path(root: Path) -> Path:
    return root / "targets.json"


def replay_path(root: Path) -> Path:
    return root / "processed.json"


def valid_targets(data: Any) -> dict[str, str]:
    if not isinstance(data, dict) or not data or not set(data).issubset(handoff.PURPOSES):
        raise WorkerBlocked("invalid target mapping")
    for key, url in data.items():
        if not isinstance(url, str) or len(url) > 500 or not browser.safe_avito_url(url):
            raise WorkerBlocked("unapproved target URL")
        parsed = urllib.parse.urlsplit(url)
        path = parsed.path.lower()
        if key == "portfolio" and not ("portfolio" in path or "profile" in path):
            raise WorkerBlocked("target not a portfolio/profile page")
        if key == "public-profile" and "profile" not in path:
            raise WorkerBlocked("target not a profile page")
    return data


def _bootstrap_unlocked(root: Path, purpose: str) -> dict[str, str]:
    """Owner manually signs in and selects screen. Never touches GitHub."""
    if purpose not in handoff.PURPOSES:
        raise WorkerBlocked("invalid bootstrap purpose")
    root = private_root(root)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise WorkerBlocked("Playwright not installed on trusted machine") from exc
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(root / "owner-session"),
            headless=False, accept_downloads=False,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.avito.ru/", wait_until="domcontentloaded", timeout=45000)
            print("Owner: sign in and open the intended profile/portfolio screen in Chromium.")
            input("When the intended page is open, press Enter in this LOCAL terminal: ")
            browser.check_page(page, purpose)
            confirmed = input("Enter CONFIRM to save this URL as a LOCAL read-only target: ")
            if confirmed != "CONFIRM":
                raise WorkerBlocked("not confirmed; no target saved")
            url = page.url
        finally:
            context.close()
    try:
        targets = valid_targets(read_private_json(target_path(root)))
    except WorkerBlocked:
        targets = {}
    targets[purpose] = url
    valid_targets(targets)
    private_json_write(target_path(root), targets)
    return {"purpose": purpose, "saved": "local_only", "owner_session": "owner_managed"}


def bootstrap(root: Path, purpose: str) -> dict[str, str]:
    """Keep bootstrap from racing the scheduled browser session."""
    root = private_root(root)
    with exclusive_worker_lock(root):
        return _bootstrap_unlocked(root, purpose)


def read_only_inventory(root: Path, purpose: str) -> dict[str, Any]:
    """Use only previously manually approved URL; fail closed on redirects."""
    root = private_root(root)
    targets = valid_targets(read_private_json(target_path(root)))
    url = targets.get(purpose)
    if not url:
        raise WorkerBlocked("target not approved by owner")
    if not (root / "owner-session").is_dir():
        raise WorkerBlocked("owner session has not been established")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(root / "owner-session"),
            headless=True, accept_downloads=False,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            browser.check_page(page, purpose)
            if page.url != url:
                raise WorkerBlocked("unapproved redirect")
            counts = browser.inspect_controls(page)
            # Do not infer valid account login or real profile access from a URL.
            # No count means even the read-only inventory could not be established.
            if not any(counts.get("categories", {}).values()):
                raise WorkerBlocked("no relevant controls visible")
            return counts
        finally:
            context.close()


def _github_request(url: str, token: str | None = None, body: dict | None = None) -> Any:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "api.github.com" or parsed.fragment:
        raise WorkerBlocked("GitHub host not allowed")
    if body is None:
        if parsed.path != urllib.parse.urlsplit(COMMENTS_URL).path:
            raise WorkerBlocked("GitHub GET path not allowed")
        params = urllib.parse.parse_qs(parsed.query)
        if set(params) != {"per_page", "page"} or params["per_page"] != ["100"]:
            raise WorkerBlocked("GitHub pagination parameters rejected")
        if len(params["page"]) != 1 or not re.fullmatch(r"[1-9][0-9]?", params["page"][0]):
            raise WorkerBlocked("GitHub page rejected")
    else:
        if url != COMMENTS_URL or not token:
            raise WorkerBlocked("GitHub POST needs exact comments endpoint and auth")
        if not isinstance(body, dict) or set(body) != {"body"}:
            raise WorkerBlocked("unexpected GitHub POST body")
        if not isinstance(body["body"], str) or not body["body"].startswith(handoff.RESULT_PREFIX):
            raise WorkerBlocked("non-result Github POST prohibited")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "AvitoTrustedUiWorker/0.1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url, data=data, headers=headers, method="POST" if data else "GET",
    )
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=20) as response:
            if response.status != (201 if data else 200):
                raise WorkerBlocked("unexpected GitHub response code")
            payload = response.read(MAX_BODY + 1)
            if len(payload) > MAX_BODY:
                raise WorkerBlocked("GitHub response too large")
            return json.loads(payload)
    except urllib.error.HTTPError as exc:
        raise WorkerBlocked("GitHub HTTP failure") from exc


def list_comments(token: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for page in range(1, MAX_PAGES + 1):
        result = _github_request(COMMENTS_URL + f"?per_page=100&page={page}", token)
        if not isinstance(result, list):
            raise WorkerBlocked("GitHub comments invalid")
        rows.extend(result)
        if len(result) < 100:
            return rows
    raise WorkerBlocked("GitHub pagination limit reached")


def completed_request_ids(comments: list[Any]) -> set[str]:
    completed = set()
    for item in comments:
        if not isinstance(item, dict) or not isinstance(item.get("user"), dict):
            continue
        if item["user"].get("id") != OWNER_USER_ID or item["user"].get("login") != handoff.OWNER_LOGIN:
            continue
        body = item.get("body")
        if not isinstance(body, str) or len(body) > 2000 or not body.startswith(handoff.RESULT_PREFIX):
            continue
        try:
            doc = json.loads(body[len(handoff.RESULT_PREFIX):])
            if doc.get("schema") != handoff.RESULT_SCHEMA or not isinstance(doc.get("request_id"), str):
                continue
            parsed = __import__("uuid").UUID(doc["request_id"])
            if parsed.version == 4 and str(parsed) == doc["request_id"]:
                completed.add(doc["request_id"])
        except (TypeError, ValueError, AttributeError):
            continue
    return completed


def load_processed(root: Path) -> set[str]:
    path = replay_path(root)
    if not path.exists():
        return set()
    data = read_private_json(path)
    if not isinstance(data, list) or len(data) > 10000 or any(not isinstance(x, str) for x in data):
        raise WorkerBlocked("invalid replay state")
    return set(data)


def _run_once_unlocked(
    root: Path, *, dry_run: bool = True,
    enable_browser: bool = False, token: str | None = None,
    comments: list[dict] | None = None,
    inventory_fn=None,
    now: dt.datetime | None = None,
) -> dict[str, int]:
    """Public commands can only trigger counts; no arbitrary user-supplied URLs."""
    root = private_root(root)
    if not dry_run and not token:
        raise WorkerBlocked("No Github token: use --dry-run until provisioned")
    # GET and POST both use this ONE fixed public GitHub issue.
    all_comments = comments if comments is not None else list_comments(token)
    processed = completed_request_ids(all_comments) | load_processed(root)
    commands = handoff.fresh_requests(all_comments, processed, now=now)
    reported = 0
    for command in commands:
        observed = None
        session_ok = False
        if enable_browser:
            try:
                observed = (inventory_fn or (lambda p: read_only_inventory(root, p)))(command["purpose"])
                # Only owner-approved local config or explicitly injected OFFLINE test can reach here.
                session_ok = observed is not None
            except Exception:
                # Never print errors from browser or site to public GitHub.
                session_ok = False
        body = handoff.make_public_result(command, observed, session_verified=session_ok, now=now)
        if not dry_run:
            _github_request(COMMENTS_URL, token, {"body": body})
            processed.add(command["request_id"])
            private_json_write(replay_path(root), sorted(processed)[-1000:])
            reported += 1
    return {"pending": len(commands), "posted": reported, "simulated": len(commands) if dry_run else 0}


def run_once(root: Path, *, dry_run: bool = True,
             enable_browser: bool = False, token: str | None = None,
             comments: list[dict] | None = None, inventory_fn=None,
             now: dt.datetime | None = None) -> dict[str, int]:
    """Hold lock throughout reading commands, browser use and replay commit."""
    root = private_root(root)
    with exclusive_worker_lock(root):
        return _run_once_unlocked(
            root, dry_run=dry_run, enable_browser=enable_browser,
            token=token, comments=comments, inventory_fn=inventory_fn, now=now)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="command", required=True)
    setup = command.add_parser("bootstrap", help="Owner signs in interactively on trusted machine")
    setup.add_argument("--purpose", choices=sorted(handoff.PURPOSES), required=True)
    once = command.add_parser("once", help="Inspect one batch from GitHub issue #32")
    once.add_argument("--dry-run", action="store_true", help="No issue comments or state writes")
    once.add_argument("--post-results", action="store_true", help="Post sanitized reports to issue")
    once.add_argument("--enable-browser-readonly", action="store_true", help="Use owner-configured Chromium session")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    try:
        if args.command == "bootstrap":
            print(json.dumps(bootstrap(args.root, args.purpose), sort_keys=True))
        else:
            if args.dry_run == args.post_results:
                parser.error("Choose exactly one of --dry-run or --post-results")
            result = run_once(
                args.root,
                dry_run=args.dry_run,
                enable_browser=args.enable_browser_readonly,
                token=os.environ.get("AVITO_BRIDGE_GITHUB_TOKEN"),
            )
            print(json.dumps(result, sort_keys=True))
    except Exception as exc:
        # Suppress potentially private browser errors, URLs and token-bearing text.
        raise SystemExit("trusted_ui_worker_blocked: " + type(exc).__name__) from None


if __name__ == "__main__":
    main()
