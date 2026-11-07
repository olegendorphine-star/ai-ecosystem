# Avito operator agent

The operator agent is the policy layer above the persistent server bridge. It
turns a work request into a gated, auditable action. The first implementation
plans and approves actions; a browser worker will execute only after the
read-only session checks pass.

## Flow

`task -> qualify -> session check -> draft -> approval gate -> submit -> verify -> journal`

A task contains the source (`fl`, `telegram`, `connect` or `avito`), order URL,
title and exact response text. The policy engine hashes the response text and
returns one of these decisions:

- `ready_to_submit` — free action, valid session and unexpired approval;
- `approval_required` — no current send approval;
- `blocked_paid` — payment or paid response detected without explicit approval;
- `auth_required` — the browser session needs human reauthorization;
- `approval_expired` — the previous approval is no longer valid.

The agent never stores passwords, OTPs or cookies in GitHub or Google Drive. A
write worker must record the order ID, response hash, free/paid state, time and
verification result. Contracts, payments and security challenges always stop
for the owner.

The current CLI is deterministic and has no network or browser side effects.
It is the tested core for the later server worker integration.
