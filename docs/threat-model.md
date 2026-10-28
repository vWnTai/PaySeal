# Threat model

PaySeal protects integrity and issuer authenticity of payment instructions. It is not a bank and does not establish beneficial ownership. Default sandbox never moves funds; guarded payOS adapters can submit real instructions only after separate production/account/security activation. No live account is currently configured.

Provider responses are authenticated through the official SDK. Tenant-bound channels are encrypted and immutable, source-account changes are not silently accepted, and payouts require fresh MFA/explicit confirmation. Durable dispatch precedes side effects; ambiguous results are queried rather than retried. Collection callbacks do not increment balances: authenticated cumulative provider state must match the order/amount/account and transaction references. See [go-live](go-live.md) for remaining bank acceptance, ownership, signing-key, settlement and operational requirements.

| Threat | Primary controls |
|---|---|
| Invoice modification | SHA-256 of final PDF bound into ES256 JWS; upload comparison |
| Bank-account replacement | AES-GCM at rest; immutable signed snapshot; account bound into JWS; controlled change request |
| Amount modification | Integer minor units; canonical manifest; ES256 signature verification |
| Fake issuer | Root-signed organization certificate, assurance level, tax ID and domain display |
| Replay | Random nonce, expiration, lifecycle status, random 256-bit public token |
| Account takeover | Argon2id, short JWT lifetime, rotating refresh token, HttpOnly cookie, TOTP, auth rate limits |
| Insider fraud | Maker cannot approve own request; configurable approval count; recent MFA for high value |
| IDOR / tenant escape | Membership dependency plus `organization_id` predicate on every tenant resource query; negative tests |
| Private-key compromise | Provider abstraction, encrypted local volume, rotation, compromised timestamp semantics |
| Audit modification | Tenant hash chain over canonical redacted event content and correlation ID |
| QR replacement | QR contains only a high-entropy HTTPS verification URL; verify page displays issuer and signed values |
| Malicious upload | Size cap, content-type allowlist, `%PDF-` magic check, no execution/unpacking, generated object names |

## Residual risks

Business review is independent and manual, not external KYC/KYB certification. Self-review is denied and demo assurance cannot authorize transfers. Evidence downloads are audited; files are not malware-scanned yet. Sandbox transfer instructions derive from signed data, are protected by MFA/tenant checks and uniqueness constraints, and never move real money. Forged/stale callbacks, altered event replay and conflicting terminal outcomes are rejected; missed outcomes are recovered through reconciliation.

The local provider exposes key material to its process and is only suitable for development. In-memory rate limits are per-process. Audit chaining detects many edits but is not an external transparency log. Production deployments need managed HSM/KMS keys, distributed throttling, append-only audit export, malware scanning, certificate operations, monitored backups, and formal incident response.

