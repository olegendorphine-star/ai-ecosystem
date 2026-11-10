# FL-003 — proof-oriented demonstration for the VPS AI assistant prospect

Date: 2026-11-10. Freelancer: olegendorphine. Lead #5528431.

## Exactly what the client asked to see

1. The assistant carries out tasks while the owner's physical computer is off.
2. Finds real Ozon and Avito product cards and compares current prices/specifications/sellers with source links. If a marketplace demands human login/CAPTCHA, report the gate rather than invent data.
3. Reads an email with attachment, extracts structured requirements, prepares an answer and waits for human confirmation before sending.
4. Demonstrates live capabilities, not only architecture slides. Future integration to Telegram, the model and actual mailbox is a separate acceptance step.

## This executable's verified boundaries

The server executable is **not** the final client-ready assistant. It performs a bounded evidence test:
- Starts separate anonymous Chromium on the VPS from GitHub Actions over pinned SSH. No workstation or owner's FL.ru session is used.
- Opens one public Logitech M185 listing on Ozon and one on Avito. Extracts a price only from relevant product JSON-LD Offer with RUB currency. A blocker or missing price means unverified, not success. No anti-bot bypass.
- Constructs a synthetic .eml email with a **real CSV attachment**, parses MIME and the CSV and extracts quantity/limit/interface. Never connects a private Gmail account, never sends messages or buys products.
- Creates an approval-gated draft clearly distinguishing verified and unverified product links. This stage is deterministic, **not yet using Kimi or another LLM**.
- Keeps one private JSON report under HOME/.fl003-demo/reports/latest.json on VPS, and uploads a synthetic-only JSON evidence artifact to GitHub Actions.

## Technical test

Use python3 -m unittest discover -s tests -p test_fl003_client_demo.py -v
and python3 tools/fl003_client_demo.py --offline.

## Live run and acceptance

GitHub Actions workflow: .github/workflows/fl003-client-demo.yml.
- offline: tests, no network.
- vps_live_public_read: executes on the owner's VPS over SSH, opens current product pages and produces a JSON evidence artifact. Only in-repository PRs may use existing SSH secrets.
- Must show workstation_needed=false, mail.structured_requirements populated, reply.approval_required=true, external_messages_sent=0.
- **Client-ready live product comparison only if** both marketplace cards yield independently verified prices; otherwise client_facing_full_demo_ready=false.
- Not evidence of Telegram control, Kimi reasoning, real email integration, persistent task queue, recovery from reboot, 24/7 monitoring or fully working production product. Those features require separately witnessed end-to-end tests.

## Offer/price alignment

Earlier prepared response to the customer suggested phase one **from 60,000 RUB and 10–14 workdays** for 2–3 bounded scenarios, support separate. This is a draft estimate, not an accepted or verified account message. A later 30,000 RUB suggestion should not replace the 60,000 RUB scope without a matching reduction in deliverables.

## External disclosure

Do not send the internal CI artifact as a finished assistant demo. It is engineering evidence. Only send the client an accurate screen recording or live demonstration after the product checks, real mailbox, Telegram, approvals and permissions are tested. Do not share personal medical/legal data, session tokens, private dialogue or cookies.
