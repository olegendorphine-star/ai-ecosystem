# Avito persistent server bridge

This bridge is the connection boundary between the Avito project and the dedicated server environment already used by the Gii staging contour. It is kept in a separate worker and must not reuse Gii databases, processes, ports, browser profiles or research data.

## Transport

GitHub Actions or a trusted operator invokes `tools/avito_server_bridge_client.py` over SSH. The client uses:

- `AVITO_SERVER_HOST`
- `AVITO_SERVER_USER`
- `AVITO_SERVER_SSH_KEY_FILE`
- `AVITO_SERVER_KNOWN_HOSTS_FILE`
- optional `AVITO_SERVER_WORKER` (default `/opt/ai-ecosystem/avito_server_worker.py`)

Host-key verification is mandatory. The client accepts only fixed read-only actions: `health`, `browser_health`, and `connect_status`. It does not accept shell text, URLs, credentials, payment commands or arbitrary remote paths.

## Remote worker contract

The server worker must return one JSON object and must not print credentials, cookies, raw page content or personal data. The first implementation should support:

- `health`: process and filesystem readiness;
- `browser_health`: Chromium/Playwright availability and network reachability;
- `connect_status`: whether the Connect/Telegram route is reachable and whether an authorized browser profile exists, without opening a write form.

A separate, explicitly approved write action may be added only after the read-only health checks pass. Any response submission must require a per-action approval flag and record the target order, exact text hash, free/paid state, timestamp and screenshot path.

## Deployment boundary

The repository does not contain server credentials and does not deploy to the server automatically. The operator must install the remote worker on the dedicated server and configure the GitHub secrets outside the repository. Never place the private key, Telegram session, browser cookies or API tokens in GitHub files, Issues or logs.

Gii remains isolated: no reuse of its database, service unit, research artifacts or browser profile. This bridge is a transport layer only.
