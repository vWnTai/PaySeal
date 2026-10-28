# Database model

```mermaid
erDiagram
  USERS ||--o{ MEMBERSHIPS : belongs
  ORGANIZATIONS ||--o{ MEMBERSHIPS : contains
  ORGANIZATIONS ||--o{ BENEFICIARIES : owns
  BENEFICIARIES ||--o{ BENEFICIARY_CHANGE_REQUESTS : proposes
  ORGANIZATIONS ||--o{ PAYMENT_REQUESTS : owns
  USERS ||--o{ PAYMENT_REQUESTS : makes
  PAYMENT_REQUESTS ||--|{ PAYMENT_REQUEST_VERSIONS : snapshots
  PAYMENT_REQUESTS ||--o{ APPROVALS : receives
  USERS ||--o{ APPROVALS : decides
  ORGANIZATIONS ||--o{ ORGANIZATION_KEYS : owns
  ORGANIZATION_KEYS ||--|| ORGANIZATION_CERTIFICATES : certified
  ORGANIZATIONS ||--o{ AUDIT_EVENTS : chains
  USERS ||--o{ REFRESH_SESSIONS : rotates
  ORGANIZATIONS ||--o{ IDEMPOTENCY_RECORDS : scopes
  ORGANIZATIONS ||--o{ BUSINESS_VERIFICATIONS : submits
  USERS ||--o{ BUSINESS_VERIFICATIONS : reviews
  PAYMENT_REQUESTS ||--o{ TRANSFERS : executes
  ORGANIZATIONS ||--o{ TRANSFERS : owns
  TRANSFERS ||--o{ TRANSFER_EVENTS : deduplicates
  ORGANIZATIONS ||--o{ PAYMENT_CHANNELS : binds
  PAYMENT_CHANNELS ||--o{ TRANSFERS : sources
  PAYMENT_CHANNELS ||--o{ COLLECTIONS : receives
  ORGANIZATIONS ||--o{ COLLECTIONS : owns
```

Payment amounts are signed 64-bit integer minor units. `payment_requests` owns mutable lifecycle metadata; `payment_request_versions` owns the immutable business snapshot used when signing. Unique constraints protect membership, approval-per-user, version numbers, public tokens, key IDs, and idempotency scopes.

Private keys never appear in this schema. Account plaintext never appears in beneficiary or version account columns. The signed JWS payload necessarily carries the account instruction for cryptographic binding, but no authenticated or public API returns that plaintext; public responses return only a masked form.

