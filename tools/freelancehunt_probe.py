#!/usr/bin/env python3
"""Read-only Freelancehunt API connectivity probe. Never prints credentials or personal data."""
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_BASE = "https://api.freelancehunt.com/v2"


class ProbeError(Exception):
    """Sanitized failure reason safe for public CI logs."""


def get_json(path: str, token: str):
    if not path.startswith("/") or "://" in path:
        raise ProbeError("invalid_path")
    request = Request(
        API_BASE + path,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "Accept-Language": "ru",
            "User-Agent": "ai-ecosystem-freelancehunt-probe/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=15) as response:
            data = json.load(response)
    except HTTPError as error:
        raise ProbeError("http_" + str(error.code)) from None
    except (URLError, TimeoutError, OSError):
        raise ProbeError("network_error") from None
    except (ValueError, UnicodeDecodeError):
        raise ProbeError("invalid_json") from None
    if not isinstance(data, dict) or "data" not in data:
        raise ProbeError("invalid_response")
    return data["data"]


def probe(token: str) -> int:
    profile = get_json("/my/profile", token)
    if not isinstance(profile, dict):
        raise ProbeError("profile_unavailable")
    projects = get_json("/projects?page[number]=1", token)
    if not isinstance(projects, list):
        raise ProbeError("projects_unavailable")
    return len(projects)


def main() -> int:
    token = os.environ.get("FREELANCEHUNT_API_TOKEN", "").strip()
    if not token:
        print(json.dumps({"status": "not_connected", "reason": "secret_missing"}))
        return 2
    try:
        project_count = probe(token)
    except ProbeError as error:
        print(json.dumps({"status": "error", "reason": str(error)}))
        return 1
    print(json.dumps({"status": "connected_read_only", "first_page_project_count": project_count}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
