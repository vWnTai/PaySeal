import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pyotp
import pytest
from app.core.config import settings
from app.models.entities import Collection, PaymentChannel, Transfer
from app.services.payos_gateway import gateway, live_blockers
from payos import PayOS
from payos.types import PayoutRequest
from sqlalchemy import func, select

from tests.test_operations import actors as actors
from tests.test_operations import approve, create_transfer, signed_payment, submit


@pytest.fixture()
def live(monkeypatch, actors):
    import app.services.live_payments as operations
    from app.security.auth import create_access_token

    for name, value in {
        "payments_live_enabled": True,
        "environment": "production",
        "public_app_url": "https://payseal.example.com",
        "refresh_cookie_secure": True,
        "account_encryption_key": "ZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWU=",
        "database_url": "postgresql://test",
        "jwt_secret": "a" * 40,
        "refresh_token_secret": "b" * 40,
        "account_lookup_hmac_key": "c" * 40,
        "key_encryption_secret": "d" * 40,
        "minio_secret_key": "e" * 40,
        "transfer_mode": "live",
        "max_live_transfer_amount": 10_000_000,
        "trusted_hosts": "localhost,testserver,payseal.example.com",
        "cors_origins": "https://payseal.example.com",
    }.items():
        monkeypatch.setattr(settings, name, value)
    assert not live_blockers()
    for person in actors[0].values():
        person["Authorization"] = "Bearer " + create_access_token(person["user"].id)
        person["headers"]["Authorization"] = person["Authorization"]

    class FakePayOS:
        def __init__(self):
            self.created = []
            self.sent = []
            self.links = {}
            self.outcomes = {}
            self.timeout = False
            self.account = "987654321"
            self.name = "OPERATIONS LTD"
            self.payouts_account = SimpleNamespace(balance=self.balance)
            self.webhooks = SimpleNamespace(confirm=self.confirm)
            self.payment_requests = SimpleNamespace(create=self.create, get=self.get)
            self.payouts = SimpleNamespace(create=self.send, list=self.list)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def balance(self):
            return SimpleNamespace(
                account_number=self.account,
                account_name=self.name,
                currency="VND",
                balance=100_000_000,
            )

        def confirm(self, callback):
            assert callback.startswith("https://payseal.example.com/api/v1/")
            return self.balance()

        def create(self, data):
            self.created.append(data)
            self.links[data.order_code] = SimpleNamespace(
                id="link" + str(data.order_code),
                order_code=data.order_code,
                amount=data.amount,
                amount_paid=0,
                status="PENDING",
                transactions=[],
            )
            if self.timeout:
                raise TimeoutError("private API key must never appear in a response")
            return SimpleNamespace(
                order_code=data.order_code,
                amount=data.amount,
                currency="VND",
                bin="970436",
                account_number=self.account,
                account_name=self.name,
                payment_link_id="link" + str(data.order_code),
                checkout_url="https://pay.payos.vn/web/test",
                status="PENDING",
            )

        def get(self, order):
            return self.links[order]

        def send(self, data, *, idempotency_key):
            self.sent.append((data, idempotency_key))
            transaction = SimpleNamespace(
                reference_id=data.reference_id,
                amount=data.amount,
                to_bin=data.to_bin,
                to_account_number=data.to_account_number,
                state="PROCESSING",
            )
            result = SimpleNamespace(
                reference_id=data.reference_id,
                transactions=[transaction],
                approval_state="PROCESSING",
            )
            self.outcomes[data.reference_id] = result
            if self.timeout:
                raise TimeoutError("private bank data")
            return result

        def list(self, params):
            result = self.outcomes.get(params.reference_id)
            return SimpleNamespace(data=[result] if result else [])

    provider = FakePayOS()
    monkeypatch.setattr(operations, "gateway", lambda channel: provider)
    return provider


def channel_payload(actors, purpose="COLLECTION"):
    people, _ = actors
    return {
        "purpose": purpose,
        "client_id": "test-client-id",
        "api_key": "test-api-key" * 3,
        "checksum_key": "test-checksum-key" * 3,
        "bank_bin": "970436",
        "account_number": "987654321",
        "account_name": "OPERATIONS LTD",
        "attested": True,
        "totp_code": pyotp.TOTP(people["maker"]["secret"]).now(),
    }


def connect(client, actors, purpose="COLLECTION"):
    response = client.post(
        "/api/v1/payment-integrations/channels",
        headers=actors[0]["maker"]["headers"],
        json=channel_payload(actors, purpose),
    )
    assert response.status_code == 201, response.text
    return response.json()


def collection_payload(actors):
    return {
        "invoice_reference": "INVOICE-1",
        "amount_minor": 200_000,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "totp_code": pyotp.TOTP(actors[0]["maker"]["secret"]).now(),
    }


def receive(client, actors, data, key="collection-key-1"):
    return client.post(
        "/api/v1/collections",
        headers={**actors[0]["maker"]["headers"], "Idempotency-Key": key},
        json=data,
    )


def test_local_readiness_never_claims_live_and_never_contacts_provider(client, actors):
    status = client.get(
        "/api/v1/payment-integrations/status", headers=actors[0]["maker"]["headers"]
    ).json()
    assert not status["infrastructure_ready"]
    assert "LIVE_DISABLED" in status["blockers"] and "HTTPS_DOMAIN_REQUIRED" in status["blockers"]
    assert (
        client.post(
            "/api/v1/payment-integrations/channels",
            headers=actors[0]["maker"]["headers"],
            json=channel_payload(actors),
        ).status_code
        == 503
    )


def test_channel_requires_kyb_owner_fresh_mfa_and_encrypts_keys(client, actors, live, db_session):
    people, _ = actors
    payload = channel_payload(actors)
    assert (
        client.post(
            "/api/v1/payment-integrations/channels",
            headers=people["maker"]["headers"],
            json=payload,
        ).status_code
        == 409
    )
    approve(client, actors, submit(client, actors).json()["id"])
    assert (
        client.post(
            "/api/v1/payment-integrations/channels",
            headers=people["approver"]["headers"],
            json=payload,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/payment-integrations/channels",
            headers=people["maker"]["headers"],
            json={**payload, "totp_code": "invalid"},
        ).status_code
        == 422
    )
    result = connect(client, actors)
    assert not any(
        key in result
        for key in ("api_key", "checksum_key", "credentials_ciphertext", "account_number")
    )
    record = db_session.get(PaymentChannel, uuid.UUID(result["id"]))
    assert payload["api_key"].encode() not in record.credentials_ciphertext
    assert record.account_last4 == "4321"
    with gateway(record) as provider:
        assert provider.base_url == "https://api-merchant.payos.vn" and provider.max_retries == 0
        assert provider.api_key == payload["api_key"]
    assert (
        client.post(
            "/api/v1/payment-integrations/channels",
            headers=people["maker"]["headers"],
            json=payload,
        ).status_code
        == 409
    )


def test_provider_account_mismatch_disables_channel_without_exposing_keys(
    client, actors, live, db_session
):
    approve(client, actors, submit(client, actors).json()["id"])
    live.account = "000000000"
    response = client.post(
        "/api/v1/payment-integrations/channels",
        headers=actors[0]["maker"]["headers"],
        json=channel_payload(actors),
    )
    assert response.status_code == 502
    assert "000000000" not in response.text and "test-api-key" not in response.text
    assert db_session.scalar(select(PaymentChannel)).status == "DISABLED"


def test_collection_is_own_account_idempotent_and_not_paid_by_return_url(
    client, actors, live, db_session
):
    approve(client, actors, submit(client, actors).json()["id"])
    connect(client, actors)
    data = collection_payload(actors)
    first = receive(client, actors, data)
    assert first.status_code == 201, first.text
    item = first.json()
    assert item["status"] == "PENDING" and item["amount_paid"] == 0
    assert receive(client, actors, data).json()["id"] == item["id"]
    assert len(live.created) == 1
    assert receive(client, actors, {**data, "amount_minor": 1}).status_code == 409
    assert (
        client.get(
            "/api/v1/collections?success=true&paid=true", headers=actors[0]["maker"]["headers"]
        ).json()[0]["status"]
        == "PENDING"
    )
    assert db_session.scalar(select(func.count()).select_from(Collection)) == 1


def test_collection_timeout_is_durable_and_retry_does_not_send_again(client, actors, live):
    approve(client, actors, submit(client, actors).json()["id"])
    connect(client, actors)
    live.timeout = True
    data = collection_payload(actors)
    result = receive(client, actors, data).json()
    assert result["status"] == "UNKNOWN" and result["checkout_url"] is None
    assert receive(client, actors, data).json()["id"] == result["id"]
    assert len(live.created) == 1
    response = client.post(
        f"/api/v1/collections/{result['id']}/reconcile", headers=actors[0]["maker"]["headers"]
    )
    assert response.status_code == 200 and response.json()["status"] == "PENDING"


def test_webhook_signature_replay_sample_and_cumulative_receipt(client, actors, live, db_session):
    approve(client, actors, submit(client, actors).json()["id"])
    channel = connect(client, actors)
    item = receive(client, actors, collection_payload(actors)).json()
    record = db_session.get(PaymentChannel, uuid.UUID(channel["id"]))
    result = live.links[item["order_code"]]
    result.status, result.amount_paid = "PAID", item["amount_minor"]
    result.transactions = [
        SimpleNamespace(account_number="987654321", amount=item["amount_minor"], reference="TXN1")
    ]
    data = {
        "orderCode": item["order_code"],
        "amount": item["amount_minor"],
        "description": "payment",
        "accountNumber": "987654321",
        "reference": "TXN1",
        "transactionDateTime": "2026-10-08 10:00:00",
        "currency": "VND",
        "paymentLinkId": "link" + str(item["order_code"]),
        "code": "00",
        "desc": "success",
        "counterAccountBankId": "",
        "counterAccountBankName": "",
        "counterAccountName": "",
        "counterAccountNumber": "",
        "virtualAccountName": "",
        "virtualAccountNumber": "",
    }

    def event(payload=data):
        with gateway(record) as provider:
            signature = provider.crypto.create_signature_from_object(payload, provider.checksum_key)
        return {
            "code": "00",
            "desc": "success",
            "success": True,
            "data": payload,
            "signature": signature,
        }

    path = "/api/v1/payment-integrations/webhooks/payos/" + channel["id"]
    assert client.post(path, json={**event(), "signature": "forged"}).status_code == 401
    assert client.post(
        path, json=event({**data, "orderCode": 123, "accountNumber": "sample"})
    ).json()["ignored"]
    assert client.post(path, json=event()).status_code == 200
    assert client.post(path, json=event()).status_code == 200
    state = client.get("/api/v1/collections", headers=actors[0]["maker"]["headers"]).json()[0]
    assert state["amount_paid"] == item["amount_minor"] and state["status"] == "PAID"
    assert (
        client.post(path, json=event({**data, "accountNumber": "other-account"})).status_code == 409
    )
    result.amount = 1
    assert client.post(path, json=event()).status_code == 409


def test_live_payout_requires_confirmation_bank_bin_limit_and_no_self_send(client, actors, live):
    payment = signed_payment(client, actors, bank_code="970436")
    connect(client, actors, "PAYOUT")
    assert create_transfer(client, actors, payment).status_code == 409
    code = pyotp.TOTP(actors[0]["approver"]["secret"]).now()
    assert create_transfer(client, actors, payment, confirm_live=True).status_code == 403
    assert (
        create_transfer(
            client,
            actors,
            payment,
            actor="maker",
            confirm_live=True,
            totp_code=pyotp.TOTP(actors[0]["maker"]["secret"]).now(),
        ).status_code
        == 403
    )
    result = create_transfer(client, actors, payment, confirm_live=True, totp_code=code)
    assert result.status_code == 201, result.text
    assert result.json()["status"] == "SUBMITTED" and result.json()["provider"] == "payos"
    assert len(live.sent) == 1
    assert live.sent[0][1] == result.json()["id"]


def test_live_timeout_does_not_send_twice_and_reconciles_reversal(client, actors, live, db_session):
    payment = signed_payment(client, actors, bank_code="970436")
    connect(client, actors, "PAYOUT")
    live.timeout = True
    extra = {"confirm_live": True, "totp_code": pyotp.TOTP(actors[0]["approver"]["secret"]).now()}
    result = create_transfer(client, actors, payment, **extra).json()
    assert result["status"] == "UNKNOWN"
    assert create_transfer(client, actors, payment, **extra).json()["id"] == result["id"]
    assert (
        create_transfer(client, actors, payment, key="another-transfer-key", **extra).json()["id"]
        == result["id"]
    )
    assert (
        len(live.sent) == 1 and db_session.scalar(select(func.count()).select_from(Transfer)) == 1
    )
    outcome = live.outcomes[result["provider_reference"]]
    outcome.transactions[0].state = "SUCCEEDED"
    path = f"/api/v1/transfers/{result['id']}/reconcile"
    assert (
        client.post(path, headers=actors[0]["approver"]["headers"]).json()["status"] == "SUCCEEDED"
    )
    outcome.transactions[0].state = "REVERSED"
    assert (
        client.post(path, headers=actors[0]["approver"]["headers"]).json()["status"] == "REVERSED"
    )
    outcome.transactions[0].amount = 1
    assert client.post(path, headers=actors[0]["approver"]["headers"]).status_code == 409


def test_official_sdk_signs_payout_requests_and_rejects_unsigned_responses():
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "code": "00",
                "desc": "success",
                "data": {
                    "id": "payout",
                    "referenceId": "ref",
                    "transactions": [],
                    "approvalState": "PROCESSING",
                    "createdAt": "2026-10-08T00:00:00Z",
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        with PayOS(
            client_id="client",
            api_key="key",
            checksum_key="checksum",
            max_retries=0,
            http_client=transport,
        ) as provider:
            with pytest.raises(Exception, match="signature"):
                provider.payouts.create(
                    PayoutRequest(
                        reference_id="ref",
                        amount=200_000,
                        description="test",
                        to_bin="970436",
                        to_account_number="12345",
                    ),
                    idempotency_key="fixed-id",
                )
    assert len(seen) == 1 and seen[0].headers["x-idempotency-key"] == "fixed-id"
    assert seen[0].headers["x-signature"] and json.loads(seen[0].content)["toBin"] == "970436"


@pytest.mark.parametrize("bank_code,limit", [("VCB", 10_000_000), ("970436", 1)])
def test_live_bank_bin_and_limit_are_checked_before_provider_call(
    client, actors, live, monkeypatch, bank_code, limit
):
    payment = signed_payment(client, actors, bank_code=bank_code)
    connect(client, actors, "PAYOUT")
    monkeypatch.setattr(settings, "max_live_transfer_amount", limit)
    code = pyotp.TOTP(actors[0]["approver"]["secret"]).now()
    result = create_transfer(client, actors, payment, confirm_live=True, totp_code=code)
    assert result.status_code in {409, 422}
    assert not live.sent


def test_queued_dispatch_rechecks_signed_amount_and_never_replays_unknown(
    client, actors, live, db_session
):
    from app.api.dependencies import TenantContext
    from app.models.entities import Membership
    from app.services.transfers import create_transfer as reserve

    payment = signed_payment(client, actors, bank_code="970436")
    connect(client, actors, "PAYOUT")
    person = actors[0]["approver"]
    membership = db_session.scalar(
        select(Membership).where(Membership.user_id == person["user"].id)
    )
    context = TenantContext(actors[1].id, person["user"], membership)
    code = pyotp.TOTP(person["secret"]).now()
    item, created = reserve(
        db_session, context, uuid.UUID(payment["id"]), "queued-key-001", code, True
    )
    db_session.commit()
    assert created and item.status == "QUEUED" and not live.sent
    item.amount_minor = 1
    db_session.commit()
    response = client.post(
        f"/api/v1/transfers/{item.id}/dispatch",
        headers=person["headers"],
        json={"confirm_live": True, "totp_code": code},
    )
    assert response.status_code == 200 and response.json()["status"] == "FAILED"
    assert not live.sent


def test_reconciliation_worker_queries_only_and_never_dispatches(
    client, actors, live, db_session, monkeypatch
):
    import app.reconcile_worker as worker
    from sqlalchemy.orm import sessionmaker

    payment = signed_payment(client, actors, bank_code="970436")
    connect(client, actors, "PAYOUT")
    live.timeout = True
    result = create_transfer(
        client,
        actors,
        payment,
        confirm_live=True,
        totp_code=pyotp.TOTP(actors[0]["approver"]["secret"]).now(),
    ).json()
    monkeypatch.setattr(
        worker, "SessionLocal", sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    )
    live.outcomes[result["provider_reference"]].transactions[0].state = "SUCCEEDED"
    assert worker.reconcile_once() == {"checked": 1, "unresolved": 0}
    db_session.expire_all()
    assert db_session.get(Transfer, uuid.UUID(result["id"])).status == "SUCCEEDED"
    assert len(live.sent) == 1
    assert worker.reconcile_once() == {"checked": 0, "unresolved": 0}


def test_disconnect_blocks_new_requests_but_keeps_reconciliation(client, actors, live):
    approve(client, actors, submit(client, actors).json()["id"])
    channel = connect(client, actors)
    original = receive(client, actors, collection_payload(actors)).json()
    response = client.post(
        "/api/v1/payment-integrations/channels/" + channel["id"] + "/disconnect",
        headers=actors[0]["maker"]["headers"],
        json={
            "reason": "Disconnect channel for new payments only.",
            "totp_code": pyotp.TOTP(actors[0]["maker"]["secret"]).now(),
        },
    )
    assert response.status_code == 200 and response.json()["status"] == "DISABLED"
    assert (
        receive(client, actors, collection_payload(actors), key="new-collection-key").status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/collections/{original['id']}/reconcile", headers=actors[0]["maker"]["headers"]
        ).status_code
        == 200
    )


def test_invalid_secret_validation_does_not_echo_input(client, actors):
    data = {**channel_payload(actors), "api_key": "short-secret"}
    response = client.post(
        "/api/v1/payment-integrations/channels", headers=actors[0]["maker"]["headers"], json=data
    )
    assert (
        response.status_code == 422
        and "short-secret" not in response.text
        and '"input"' not in response.text
    )


def test_seed_demo_is_rejected_in_production(monkeypatch):
    from app.seed import run

    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(RuntimeError, match="Demo accounts"):
        run()


def test_signature_from_previous_business_profile_cannot_send_live(client, actors, live):
    payment = signed_payment(client, actors, bank_code="970436")
    connect(client, actors, "PAYOUT")
    person, organization = actors
    assert (
        client.patch(
            f"/api/v1/organizations/{organization.id}",
            headers=person["maker"]["headers"],
            json={"name": "New Legal Profile"},
        ).status_code
        == 200
    )
    approve(client, actors, submit(client, actors).json()["id"])
    response = create_transfer(
        client,
        actors,
        payment,
        confirm_live=True,
        totp_code=pyotp.TOTP(person["approver"]["secret"]).now(),
    )
    assert response.status_code == 409 and not live.sent
