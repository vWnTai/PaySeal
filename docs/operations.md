# Business verification and transfer operations

## Boundaries

Business verification means manual PaySeal review, not a government certificate or guarantee that a payment is safe. Three checks (registration, tax identity, authority) plus a recorded reason are mandatory for approval. PDF evidence is private, size/type/magic-checked and SHA-256-bound. Downloads are audited and attachment-only. There is no malware scanning or external registry lookup yet.

Only a server operator grants reviewer permission with python -m app.manage_reviewer EMAIL --grant (or --revoke). Reviewers require MFA and cannot review/download evidence from a company they belong to. There is no hidden reviewer/password or client-assignable platform role.

Approvals expire after 365 days. Pending cases freeze identity edits; later changes invalidate approval even if the old name is restored. New certificates reflect updated assurance. Public verification preserves the signed issuer snapshot and separately reports current business trust. DEMO_SEEDED never authorizes transfers.

Sandbox transfers require an independent OWNER/APPROVER, recent MFA, a current manual business approval and an active signed VND request. The signed manifest supplies amount/account. Plaintext account is transient provider input, not an API/log field. Database constraints and locking enforce organization-scoped idempotency and one transfer per signed version.

The sandbox ledger is durable and separate from transfer state. SUBMITTED ends in SUCCEEDED or FAILED: all outcomes mean simulation, never money movement. Terminal states cannot change/automatically retry. Reconciliation verifies provider reference/amount/currency. Revocation is not a refund or cancellation of an already submitted transfer.

## API

All paths have /api/v1 prefix.

| Endpoint | Access |
|---|---|
| GET /organizations/{id}/verification | Organization OWNER/AUDITOR |
| POST /organizations/{id}/verification | OWNER; multipart document PDF, registration_number, representative_name, registered_address, contact_email, attested |
| GET /platform/verifications?status=PENDING&offset=0 | MFA-enabled independent reviewer; 50/page |
| GET /platform/verifications/{id}/document | Independent reviewer; audited attachment |
| POST /platform/verifications/{id}/review | Independent reviewer + recent MFA + reason/checks |
| POST /platform/verifications/{id}/revoke | Same authority; current approved case only |
| GET /transfers/capabilities | Tenant member; real_money_enabled requires live mode, security readiness and a connected payout channel |
| GET /transfers | Tenant member; latest 200 records |
| POST /transfers | OWNER/APPROVER; Idempotency-Key; payment_request_id, totp_code and confirm_live (mandatory true for live) |
| POST /transfers/{id}/sandbox-outcome | Same-tenant OWNER/APPROVER; simulation only |
| POST /transfers/{id}/reconcile | Same-tenant OWNER/APPROVER |
| POST /transfers/webhooks/sandbox | HMAC authentication, not user JWT |

## Sandbox callbacks

TRANSFER_MODE=sandbox selects the local adapter; disabled blocks transfers; live additionally requires PAYMENTS_LIVE_ENABLED, production/HTTPS/security readiness, an approved business, connected tenant-bound payOS payout channel, explicit confirmation and fresh MFA. See [go-live guide](go-live.md). A flag alone never enables real payouts.

TRANSFER_WEBHOOK_SECRET defaults to empty, rejecting every external callback with 503. Configure a separately generated random secret of at least 32 bytes through secret management/.env, never frontend code. Internal simulations do not reveal/require this secret.

Example body:

    {"event_id":"UUID","provider_reference":"sandbox_<transfer UUID without hyphens>","status":"SUCCEEDED","amount_minor":5000000,"currency":"VND"}

X-PaySeal-Timestamp is Unix seconds. X-PaySeal-Signature is hex HMAC-SHA256(secret, timestamp + "." + exact raw JSON bytes). Timestamps outside a 300-second window and bodies over 16 KiB are rejected. Event IDs/payload hashes are persisted: identical retries are acknowledged; altered ID reuse, amount/reference mismatch and conflicting terminal outcomes are rejected. Re-sign retries with a current timestamp.

This is PaySeal's sandbox contract, not a bank-compatible scheme. Live adapters must implement their provider's documented scheme/status semantics. Security references: [OWASP transaction authorization](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html), [OWASP webhook security](https://cheatsheetseries.owasp.org/cheatsheets/Webhook_Security_Cheat_Sheet.html).

## payOS integration and remaining prerequisites

Implemented: official SDK 1.1.0, encrypted immutable COLLECTION/PAYOUT channels, provider account checks, independent receivables, signed collection callbacks, durable financial dispatch, timeout-as-unknown, provider idempotency, reference-based lookups, query-only scheduled reconciliation and explicit reversal state. GET/POST /payment-integrations/channels and GET /payment-integrations/status expose no secrets. POST /channels/{id}/disconnect requires owner/fresh MFA. GET/POST /collections and POST /collections/{id}/reconcile are tenant-bound. POST /transfers/{id}/dispatch only sends previously reserved QUEUED live records after fresh MFA and rechecking safety. See [activation and recovery](go-live.md).

- Named payout/bank and KYB providers, approved business/source accounts, contracts, sandbox access, official API docs and credentials in secret management. Do not paste credentials in chat.
- Legal ownership checks, daily limits, fees, stronger transaction-bound authorization and live-provider acceptance tests.
- Independent statement/settlement reconciliation and operational review of unknown outcomes; never automatically resubmit an ambiguous payout.
- Recovery/retry review, reversals/refunds where supported, settlement references and monitoring.
- Public HTTPS hostname, production secrets, non-exportable signing keys, evidence retention/access policies, malware quarantine and independent security/operational review.
- Jurisdiction-specific legal/compliance review. This code does not certify compliance.

Tests use isolated databases/storage and cover independent review, evidence integrity, profile/expiry/revocation, IDOR, signed transfer binding, duplicates, MFA, live fail-closed behavior, reconciliation and callback forgery/expiry/replay.
