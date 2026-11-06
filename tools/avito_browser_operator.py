#!/usr/bin/env python3
"""Owner-authorized Avito browser operator. No stealth, no login automation, no CI execution.

Usage:
    python tools/avito_browser_operator.py inspect
    python tools/avito_browser_operator.py check-plan path/to/plan.json
    python tools/avito_browser_operator.py apply-plan path/to/plan.json

Playwright is imported only for interactive inspect/apply; check-plan requires stdlib.
This is an initial operator, NOT a verified map of Avito's live interface.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

AVITO_ORIGIN = "https://www.avito.ru/"
BLOCKED_URL_PARTS = (
    "/messenger", "/messages", "/chat", "/payment", "/pay", "/balance",
    "/wallet", "/promotion", "/promote", "/security", "/password",
    "/notifications", "/delete", "/remove", "/billing", "/finance", "/orders",
)
BLOCKED_WORDS = re.compile(
    r"(?:оплат|купить|продвиг|продвиж|платеж|баланс|кошел|"
    r"сообщен|переписк|чат\b|парол|двухфактор|captcha|"
    r"payment|buy\b|wallet|password|message|security|delete|remove|"\n    r"удал|архив|отключ|снять с публикац|опубликов|отправ|send\b)", re.I
)
ALLOWED_ACTIONS = {"click", "fill", "upload"}
ALLOWED_LOCATORS = {"role", "label", "placeholder"}
ALLOWED_ROLES = {"button", "link", "textbox", "tab"}
MAX_STEPS = 15
DEFAULT_SESSION = Path.home() / ".local" / "share" / "avito-browser-operator"
MAX_VALUE = 4000


class OperatorSafetyError(ValueError):
    """Stop operation instead of guessing when safety requirements fail."""


def safe_avito_url(url: str) -> bool:
    """Allow only ordinary HTTPS Avito pages, excluding messages, finance and security."""
    try:
        p = urlsplit(url)
        if (p.scheme != "https" or p.hostname not in {"avito.ru", "www.avito.ru"}
                or p.username or p.password or p.port or p.query or p.fragment):
            return False
        path = p.path.lower()
        if any(word in path for word in BLOCKED_URL_PARTS):
            return False
        return True
    except ValueError:
        return False


def read_plan(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    validate_plan(doc)
    return doc


def validate_plan(doc: object) -> None:
    if not isinstance(doc, dict) or set(doc) != {"purpose", "steps"}:
        raise OperatorSafetyError("Plan requires exactly 'purpose' and 'steps'.")
    if doc["purpose"] not in ("public-profile", "portfolio"):
        raise OperatorSafetyError("Only owner's public-profile and portfolio actions allowed.")
    steps = doc["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise OperatorSafetyError("Plan must include 1..15 fixed actions.")
    for number, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise OperatorSafetyError(f"Step {number}: not an object.")
        action = step.get("action")
        if action not in ALLOWED_ACTIONS:
            raise OperatorSafetyError(f"Step {number}: unsupported action.")
        expected_keys = {"action", "by", "name", "value"} if action in ("fill", "upload") else {"action", "by", "name"}
        if set(step) != expected_keys:
            raise OperatorSafetyError(f"Step {number}: unexpected/missing fields.")
        name = step["name"]
        by = step["by"]
        if (by not in ALLOWED_LOCATORS or not isinstance(name, str)
                or not 1 <= len(name) <= 100 or BLOCKED_WORDS.search(name)):
            raise OperatorSafetyError(f"Step {number}: prohibited or ambiguous locator.")
        if action == "click" and by == "placeholder":
            raise OperatorSafetyError(f"Step {number}: click requires visible label/role.")
        if action != "click":
            val = step["value"]
            if not isinstance(val, str) or not 1 <= len(val) <= MAX_VALUE:
                raise OperatorSafetyError(f"Step {number}: invalid value.")
            if action == "upload" and Path(val).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                raise OperatorSafetyError(f"Step {number}: only image file uploads permitted.")


def make_locator(page, step: dict):
    if step["by"] == "role":
        return page.get_by_role("button", name=step["name"], exact=True)
    if step["by"] == "label":
        return page.get_by_label(step["name"], exact=True)
    return page.get_by_placeholder(step["name"], exact=True)


def check_page(page, purpose: str) -> None:
    if not safe_avito_url(page.url):
        raise OperatorSafetyError("Unexpected domain or restricted Avito page. Stopping.")
    # The owner selects the right screen manually. We don't navigate from unknown UI instructions.
    path = urlsplit(page.url).path.lower()
    if purpose == "portfolio" and not ("portfolio" in path or "profile" in path):
        raise OperatorSafetyError("Portfolio/profile screen not established; no edits performed.")
    if purpose == "public-profile" and "profile" not in path:
        raise OperatorSafetyError("Profile screen not established; no edits performed.")


def private_directory(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        resolved.chmod(0o700)
    return resolved


def screenshot(page, base: Path, suffix: str) -> Path:
    target = base / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + suffix + ".png")
    page.screenshot(path=str(target), full_page=False)
    if os.name != "nt":
        target.chmod(0o600)
    return target


def interactive(command: str, plan: dict | None, session: Path) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("Install Playwright locally: pip install playwright && playwright install chromium") from exc
    root = private_directory(session)
    print("Session stays ONLY on this computer. Do not upload screenshots or the browser directory.")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(root / "owner-session"),
            headless=False,
            viewport={"width": 1360, "height": 900},
            accept_downloads=False,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(AVITO_ORIGIN, wait_until="domcontentloaded", timeout=45000)
            print("Log in to Avito yourself. Complete CAPTCHA/2FA manually, then navigate to the required page.")
            input("Press Enter on THIS computer when the appropriate page is open: ")
            if not safe_avito_url(page.url):
                raise OperatorSafetyError("Not a permitted Avito page.")
            if command == "inspect":
                path = screenshot(page, root, "inspect")
                print("READ-ONLY inspection completed. Private screenshot:", str(path))
                print("Verified host: Avito. No profile edits, messages or payments performed.")
                return
            assert plan is not None
            check_page(page, plan["purpose"])
            print("Plan purpose:", plan["purpose"], "| actions:", len(plan["steps"]))
            for i, action in enumerate(plan["steps"], 1):
                print(f"  {i}: {action['action']} using {action['by']} '{action['name']}'")
            before = screenshot(page, root, "before")
            print("Private PRE-change screenshot:", str(before))
            phrase = input("Type exactly ПРИМЕНИТЬ to execute the plan (anything else cancels): ")
            if phrase != "ПРИМЕНИТЬ":
                print("Canceled without edits.")
                return
            for i, step in enumerate(plan["steps"], 1):
                check_page(page, plan["purpose"])
                locator = make_locator(page, step)
                if locator.count() != 1:
                    raise OperatorSafetyError(f"Step {i}: locator not unique or unavailable. Stop.")
                action = step["action"]
                if action == "fill":
                    locator.fill(step["value"], timeout=10000)
                elif action == "upload":
                    local_file = Path(step["value"]).expanduser().resolve(strict=True)
                    if not local_file.is_file() or local_file.stat().st_size > 15 * 1024 * 1024:
                        raise OperatorSafetyError(f"Step {i}: invalid image upload size.")
                    locator.set_input_files(str(local_file), timeout=10000)
                else:
                    locator.click(timeout=10000)
                check_page(page, plan["purpose"])
            after = screenshot(page, root, "after")
            print("Executed fixed plan. Private POST-action screenshot:", str(after))
            print("Check the actual public profile manually. A click/save does not prove publication.")
        finally:
            context.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inspect", "check-plan", "apply-plan"])
    parser.add_argument("plan", nargs="?", type=Path)
    parser.add_argument("--session-dir", type=Path, default=DEFAULT_SESSION)
    args = parser.parse_args()
    if args.command == "inspect":
        if args.plan:
            parser.error("inspect takes no plan")
        interactive("inspect", None, args.session_dir)
    else:
        if not args.plan:
            parser.error(f"{args.command} requires a local JSON plan")
        plan = read_plan(args.plan)
        if args.command == "check-plan":
            print("Plan schema and safety checks: OK. Live Avito selectors NOT yet verified.")
        else:
            interactive("apply-plan", plan, args.session_dir)


if __name__ == "__main__":
    main()
