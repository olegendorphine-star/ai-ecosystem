#!/usr/bin/env python3
"""Safely restrict access to existing Avito browser state on the owner VPS.

Uses openat and O_NOFOLLOW. Never reads, prints, rewrites or copies credentials.
"""
from __future__ import annotations
import json
import os
import stat
from pathlib import Path


def secure_profile(root: Path) -> dict:
    result = {
        "action": "session_permissions",
        "ok": False,
        "profile_owner_only": False,
        "session_file_owner_only": False,
        "write_account_actions": False,
    }
    dirfd = None
    filefd = None
    try:
        dirfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        directory = os.fstat(dirfd)
        if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid():
            return result
        # Only chmod a directory owned by the SSH user, never a symlink or foreign folder.
        os.fchmod(dirfd, 0o700)
        result["profile_owner_only"] = stat.S_IMODE(os.fstat(dirfd).st_mode) == 0o700
        try:
            filefd = os.open("storage_state.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dirfd)
        except FileNotFoundError:
            # A missing state is legitimate before initial login.
            result["ok"] = result["profile_owner_only"]
            return result
        info = os.fstat(filefd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            return result
        os.fchmod(filefd, 0o600)
        result["session_file_owner_only"] = stat.S_IMODE(os.fstat(filefd).st_mode) == 0o600
        result["ok"] = result["profile_owner_only"] and result["session_file_owner_only"]
    except OSError:
        pass
    finally:
        if filefd is not None:
            os.close(filefd)
        if dirfd is not None:
            os.close(dirfd)
    return result


def main() -> None:
    root = Path(os.environ.get("AVITO_BROWSER_PROFILE_DIR") or Path.home() / ".avito-agent" / "profile").expanduser()
    print(json.dumps(secure_profile(root), sort_keys=True))


if __name__ == "__main__":
    main()
