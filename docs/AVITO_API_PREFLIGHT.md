# Avito API — read-only diagnostic v0.1, 2026-11-04

**Status: offline tested; live authorization NOT verified.** This is a new diagnostic helper, not a recovered deployed Kimi program.

## Historical source and research boundary

- Commercial project source of truth: [Google Drive project passport](https://docs.google.com/document/d/1jzJFE1vcO4YwN6Xs7z9aEQAPom1ODerh79ndQZYzMQE/edit).
- Kimi handoff source: original ZIP `ПОЛНАЯ ПЕРЕДАЧА ПРОЕКТА — Персональная ИИ-экосистема_Авито.zip` (Drive ID `1c6mbRdvnoEogfYo7PFuzCUecF2FAVUsY`; SHA-256 `7e505880d0c7499c198cab8737f7eaec8ad1d9a02a955e331337cbe5d42c4966`; 9,400,280 bytes; ZIP CRC OK).
- The handoff ZIP includes 33 documents, commercial materials, sanitized XML and images, **not** a deployable Avito Python client. It must not be treated as production source.
- Historical 2026-10-29: read-only API successes for own profile, items, uploads/reports, and messenger read; four successful upload cycles for **the same item** Avito ID `449877076`.
- Historical 2026-10-30: `POST /token/` `client_credentials` returned `unauthorized_client`. The cause remains unknown; prior attempts tried body, Basic Auth, slash/no slash. Do not repeat them without new evidence.
- Approved advertisement and six replacement images in Google Drive are authoritative. Do not publish sanitized historical XML, create a duplicate item, modify prices, or send customer messages.
- Support ticket number from project context: `79233707`, but no reply found in current connected Gmail searches as of 2026-11-04. Avito internal support inbox is **not** connected by Gmail.

## Relevant external API references (must be re-checked before live use)

- Official portal: https://developers.avito.ru/api-catalog
- Official token docs: https://developers.avito.ru/api-catalog/auth/documentation#/token
- Account API key settings: https://www.avito.ru/professionals/api

Historical and public reference point: personal authorization uses `POST https://api.avito.ru/token/` with `grant_type=client_credentials`, `client_id`, `client_secret`; access token then permits authorized endpoints, subject to account rights. The prior `unauthorized_client` error can mean that this client is not permitted to use this grant; it does not prove incorrect credentials or permanent exclusion. Do not switch to another OAuth flow without the provider's rights/response.

## Safe offline checks

```bash
python3 tools/avito_preflight.py
python3 -m unittest discover -s tests -p 'test_avito_preflight.py' -v
```

Default execution does not read credentials, create files or contact a server. Tests use injected mock transports. No external dependencies beyond Python 3.10+.

## Explicitly gated live diagnostic (NOT YET AUTHORIZED / NOT RUN)

Only after Avito support or current official instructions confirm the grant and credentials are securely installed **in the operator's isolated environment**, with separate owner approval to run a real read-only API check:

```bash
# Use protected secret injection rather than typing secrets in chat/CLI/history.
AVITO_ALLOW_READONLY_PREFLIGHT=YES python3 tools/avito_preflight.py --live
```

`AVITO_CLIENT_ID` and `AVITO_CLIENT_SECRET` must already exist in the protected environment, never in source control. The diagnostic performs no more than two requests and no retries: an authorization request, then one read-only `GET /core/v1/accounts/self` if auth succeeds. It returns ONLY status/error categories; does not print or save account details, client credentials, or access tokens. No actions on advertisements or messages.

## Acceptance gate

Offline tests passing **does not** mean API is connected. For a GO decision, record support/account confirmation of grant and permissions, approved secure runtime, explicit authorized first check, resulting HTTP statuses and timestamp without secrets, and a read-back of the current item state before considering any publication.