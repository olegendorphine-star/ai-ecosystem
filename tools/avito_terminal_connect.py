#!/usr/bin/env python3
"""Operator-only Avito read-only check. No secrets in CLI flags, files or history.

Runs offline by default. Explicit --live and interactive confirmation required.
Use from a trusted terminal controlled by the account owner, not an AI chat.
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
import warnings

from avito_preflight import diagnostics


def main(argv=None, *, input_fn=None, secret_fn=None, run_fn=None, stdin=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--live', action='store_true', help='Allow at most one token and one profile read')
    args = p.parse_args(argv)

    if not args.live:
        print(json.dumps({'status': 'OFFLINE_READY', 'network': False, 'secrets_read': False,
                          'writes': False}, sort_keys=True))
        return 0

    stream = sys.stdin if stdin is None else stdin
    if not stream.isatty():
        print('BLOCKED: interactive trusted terminal required', file=sys.stderr)
        return 2

    ask = input if input_fn is None else input_fn
    hidden = getpass.getpass if secret_fn is None else secret_fn
    check = diagnostics if run_fn is None else run_fn

    print('Read-only Avito API check: at most 1 token request and 1 GET profile.')
    print('No ads, customer messages or changes; do not paste credentials into chat.')
    if ask('Type YES to make the live read-only check: ').strip() != 'YES':
        print('CANCELLED')
        return 2

    try:
        with warnings.catch_warnings():
            # getpass can fall back to visible input on an unusual terminal.
            # Treat that as a hard error instead of risking credential echo.
            warnings.simplefilter('error', getpass.GetPassWarning)
            client_id = hidden('Avito Client ID (hidden): ')
            client_secret = hidden('Avito Client Secret (hidden): ')
        if not client_id or not client_secret:
            print('BLOCKED: both Client ID and Client Secret are required', file=sys.stderr)
            return 2
        results = check(client_id, client_secret)
    except (KeyboardInterrupt, EOFError):
        print('CANCELLED', file=sys.stderr)
        return 2
    except Exception:
        # Never display exception text: transport failures may contain secrets.
        print('ERROR: diagnostic failed without exposing details', file=sys.stderr)
        return 2
    finally:
        # No persistence of secrets; CPython strings cannot be securely zeroized.
        client_id = None
        client_secret = None

    for result in results:
        print(json.dumps(result.as_dict(), sort_keys=True))
    return 0 if len(results) == 2 and all(result.success for result in results) else 1


if __name__ == '__main__':
    sys.exit(main())