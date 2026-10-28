# API overview

Business verification, independent reviewer, sandbox transfer and guarded payOS endpoints are documented in [operations](operations.md) and [go-live](go-live.md). Transfers require Idempotency-Key and approved business evidence; live additionally requires fresh MFA and explicit real-money confirmation. Platform permissions are server-provisioned, never tenant-owner-granted. Sandbox is not real money movement.

All endpoints are under `/api/v1`. Swagger is available at `/docs` outside production. Authenticated tenant endpoints require `Authorization: Bearer …` and `X-Organization-ID`.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`; `GET /auth/me` |
| MFA | `POST /auth/mfa/setup`, `/enable`, `/verify`, `/disable` |
| Organization | `POST /organizations`; `GET/PATCH /organizations/{id}`; member routes; key rotation/compromise routes |
| Beneficiary | `POST/GET /beneficiaries`; `GET/PATCH /beneficiaries/{id}`; `POST .../change-request` |
| Payment | `POST/GET /payment-requests`; `GET/PATCH /{id}`; submit, approve, reject, sign, revoke, PDF routes |
| Public | `GET /public/verify/{token}`; `POST /public/verify/{token}/document` |
| Audit | `GET /audit-events` |

Create and sign accept `Idempotency-Key`. Login returns the access token in JSON and installs an opaque refresh token as an HttpOnly, SameSite=Strict cookie. Refresh/logout require the matching `X-CSRF-Token` returned at login or refresh.

Public verification deliberately returns a structured result: issuer/signature flags, effective lifecycle status, masked account details, times, and warnings. It never returns the JWS or full account.

