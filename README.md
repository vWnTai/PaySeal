# PaySeal

PaySeal implements maker–checker approval, signed manifests/certificates, QR/public verification, PDF integrity comparison, independent manual business review, sandbox operations and guarded payOS collection/payout integration. Local defaults never move real money; no live provider account is currently configured. There is no AI/blockchain component.

## Thu và chi tiền với payOS

Giao diện có **Thu tiền**, **Chi tiền** và **Kết nối thanh toán**. Kênh thu/chi riêng theo tổ chức, khóa được mã hóa, MFA và xác nhận tiền thật là bắt buộc. Lệnh được lưu trước khi gửi; mất kết nối chuyển sang trạng thái chưa rõ và chỉ đối soát, không tự gửi lại.

Chưa có ngân hàng/tên miền/máy chủ: xem **Kết nối thanh toán** trong ứng dụng hoặc [hướng dẫn triển khai và kích hoạt](docs/go-live.md). SDK và cấu hình HTTPS đã được chuẩn bị; **chưa nghiệm thu với payOS thật, chưa có giao dịch thật**. Production vẫn cần kiểm tra bảo mật/vận hành độc lập.

## Business verification and sandbox transfers

Open **Tổ chức → Hồ sơ xác minh** to submit a private PDF with registration/representation evidence. Independent reviewers approve, reject, request additions, or revoke a current approval. They must check registration, tax identity and authority independently and record sources/date. Manual review is not a government/bank certification. PDF malware scanning is not implemented: reviewers must use an isolated review environment.

Register a separate reviewer account normally and enable MFA. An authorized server operator explicitly grants access:

    docker compose exec backend python -m app.manage_reviewer reviewer@example.com --grant

Sign in again to open **Xét duyệt doanh nghiệp**. Do not add this reviewer to the company being reviewed. There is no default reviewer/password or public role-elevation API. Use --revoke to remove permission.

Approvals expire after 12 months; identity changes require re-verification. Seeded organizations are demo-only and do not authorize transfers.

Open **Chuyển tiền thử nghiệm** as an OWNER/APPROVER independent of the payment maker. A current manual business approval, active signed VND request and MFA are required. Amount/account come from the signed manifest. Repeated requests cannot transfer the same signed version twice. Simulate success/failure, or a lost notification followed by **Đối soát**. No real balance is debited/credited. Revocation does not reverse past transfers; failed requests do not automatically retry.

Migrations 0002/0003 preserve existing records. Back up PostgreSQL before upgrading; the backend applies migrations on startup. See [operations guide](docs/operations.md) for callbacks and [go-live guide](docs/go-live.md) for provider activation.

## Quick start

Requirements: Docker Engine with Compose v2 and `make` (the equivalent Docker commands also work on Windows).

```bash
git clone <repository-url> payseal
cd payseal
cp .env.example .env
docker compose up --build
```

In a second terminal:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed
```

Open:

- Frontend and public verifier: <http://localhost:3000>
- Backend direct proxy: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>
- MinIO console: <http://localhost:9001>

The values in `.env.example` are intentionally local-only. Generate unique secrets before any shared deployment. A 32-byte encryption key can be generated with `python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`.

MinIO Community Edition is source-only as of its final community releases, so Compose builds the pinned upstream `RELEASE.2025-10-15T17-29-55Z` source into a local image. The first cold build downloads Go modules and therefore takes longer; subsequent builds use Docker cache.

## Demo accounts

After seeding, all accounts use the local password `PaySeal-Demo-2026!`:

- `maker@demo.local` — MAKER
- `approver@demo.local` — APPROVER
- `owner@demo.local` — OWNER

The seeded organization is **CÔNG TY PAYSEAL DEMO**, tax ID `0101234567`, domain `demo.payseal.local`, assurance level `BUSINESS_VERIFIED`. Its beneficiary is **CÔNG TY ABC**, VCB, account ending `6789`.

For the VND 28,500,000 scenario, the policy requires recent MFA. Sign in as the approver, enroll TOTP under **Bảo mật**, then approve/sign with the current six-digit code.

## Demo scenarios

1. Đăng nhập bằng tài khoản người tạo, bấm **Tạo yêu cầu**, nhập mã hóa đơn, số tiền và người thụ hưởng. Lưu bản nháp rồi bấm **Gửi phê duyệt**.
2. Đăng nhập bằng tài khoản người phê duyệt, mở **Cần phê duyệt**, kiểm tra thông tin rồi xác nhận. Sau khi đủ lượt duyệt, bấm **Ký và tạo PDF**. Trang chi tiết cho phép tải PDF và sao chép liên kết xác minh.
3. Mở liên kết hoặc quét QR: trang hợp lệ hiển thị **Yêu cầu hợp lệ**. Để thử kiểm tra PDF bị sửa, tải PDF và chạy:

   ```bash
   python scripts/corrupt_pdf.py original.pdf modified.pdf
   ```

   Tải `modified.pdf` lên trang xác minh. Trang sẽ báo **Tài liệu đã bị thay đổi**.
4. Thu hồi yêu cầu cùng lý do. Mở lại liên kết QR: trang sẽ báo **Yêu cầu đã bị thu hồi**.

## Commands

```text
make up              Build and start all containers
make down            Stop containers
make build           Build images
make logs            Follow logs
make migrate         Apply Alembic migrations
make seed            Create local demo data
make test            Run pytest and Vitest
make backend-shell   Open backend shell
make frontend-shell  Open frontend shell
```

Run backend tests locally with Python 3.12 and the test extras: `pip install -e './backend[test]' && pytest backend/tests -q`. Run frontend tests with `cd frontend && npm ci && npm test -- --run`.

Frontend maintenance commands (inside `frontend/`):

- `npm run lint` checks TypeScript and source formatting.
- `npm run format` formats source using the project's shared configuration.
- `npm run build` validates the production build.

Frontend components share session state, cancellable resource queries, loading buttons, payment statuses, and API error handling. The interface supports keyboard navigation, unaccented Vietnamese search, responsive layouts, and reduced-motion preferences.

The CSS build uses Tailwind 4 with automatic source detection and vendor prefixes, eliminating the old Tailwind config and Autoprefixer dependency. Browser support is Safari 16.4+, Chrome/Edge 111+, and Firefox 128+; see the [official upgrade guide](https://tailwindcss.com/docs/upgrade-guide).

Backend source is formatted with Ruff. Install the development extra with `pip install -e './backend[dev]'`, then use `ruff check backend scripts` and `ruff format --check backend scripts`.

## Security controls

- Argon2id password hashes; 15-minute HS256 access JWTs; hashed, rotating opaque refresh sessions with reuse-family revocation and CSRF binding.
- TOTP with a five-minute recent-authentication window for policy-selected operations.
- Backend-only deny-by-default RBAC and tenant predicates; IDOR tests cover payments, beneficiaries, approval, and audit.
- AES-256-GCM account encryption, HMAC-SHA256 lookup, masking, no account/token/secret logging.
- P-256/SHA-256 ES256 compact JWS using `cryptography`; deterministic JSON for the supported manifest value domain.
- Root-signed organization certificates; public JWK storage only; key retirement/revocation/compromise modeling.
- Allow-listed state machine, signed-data immutability, row locks, approval uniqueness, and idempotency records.
- Private MinIO bucket, UUID object keys, upload size/type/magic checks, security headers, trusted hosts, CORS, and layered throttling.
- Correlation IDs and redacted tenant SHA-256 audit chains.

See [architecture](docs/architecture.md), [database model](docs/database.md), [threat model](docs/threat-model.md), and [API overview](docs/api.md).

## Known MVP limitations

- `LocalSigningProvider` has exportable encrypted keys and is for local development only.
- Approval rules are centralized/configurable Python policy, not yet an organization-admin policy editor.
- API rate limiting is in process (Nginx adds another local layer), not distributed.
- The audit chain is tamper-evident but not anchored to external immutable storage.
- Beneficiary account change requests are captured but do not yet expose a separate approval endpoint.
- Business review is manual, with evidence, independence controls, expiry/revocation. No external KYB/KYC provider is connected. Seeded organizations are explicitly demo-only.
- payOS SDK adapters and a query-only reconciliation worker are implemented, with encrypted tenant-bound channels and durable dispatch. No real provider account, live acceptance test, independent bank-statement/settlement reconciliation or refund workflow is configured. Default sandbox and production security gates remain fail-closed.
- PDF metadata sanitization is controlled at generation; uploaded PDFs are hashed only and not malware-scanned.
- The local root public key is generated on first start and mounted from the key volume, not distributed through a production trust ceremony.
- The pinned community MinIO release is compiled from the now-archived upstream source; production should use a maintained, supported S3-compatible object store or licensed MinIO distribution.

## Production-hardening roadmap

1. Replace local signing/root keys with non-exportable HSM-backed Vault/KMS providers and dual-control key ceremonies.
2. Add persisted, versioned organization approval policies and administrative review for beneficiary changes.
3. Move refresh/session and throttling coordination to Redis; add device/session inventory and stronger phishing-resistant MFA.
4. Export signed audit checkpoints to WORM storage/SIEM and add continuous chain verification.
5. Add ClamAV/CDR upload inspection, object-lock retention, encrypted backups, DR drills, and MinIO service credentials scoped to one bucket.
6. Add CA-managed TLS, CSP tuned for the frontend, secret manager injection, SAST/DAST/dependency/container scanning, and Kubernetes network policies.
7. Commission cryptographic/protocol review, multi-tenant penetration testing, load testing, and incident response exercises.
