import time

import pyotp
from app.models.entities import RefreshSession, User
from app.services.runtime import encryption_service
from sqlalchemy import func, select


def create_account(client, db_session, *, mfa=False):
    credentials = {"email": "mfa@example.com", "password": "Strong-Demo-Password-2026!"}
    response = client.post("/api/v1/auth/register", json={**credentials, "full_name": "MFA Test"})
    assert response.status_code == 201
    secret = pyotp.random_base32()
    if mfa:
        user = db_session.scalar(select(User).where(User.email == credentials["email"]))
        user.mfa_enabled = True
        user.mfa_secret_ciphertext = encryption_service().encrypt(secret, context=b"payseal-mfa-v1")
        db_session.commit()
    return credentials, secret


def test_non_mfa_account_logs_in_without_code(client, db_session):
    credentials, _ = create_account(client, db_session)
    response = client.post("/api/v1/auth/login", json=credentials)
    assert response.status_code == 200
    assert response.json()["access_token"]
    assert "payseal_refresh" in response.cookies
    assert db_session.scalar(select(func.count()).select_from(RefreshSession)) == 1


def test_mfa_requires_correct_password_and_code_before_creating_session(client, db_session):
    credentials, secret = create_account(client, db_session, mfa=True)
    totp = pyotp.TOTP(secret)
    now = int(time.time())
    valid_codes = {totp.at(now + offset) for offset in (-30, 0, 30)}
    wrong_code = next(
        f"{candidate:06d}" for candidate in range(10) if f"{candidate:06d}" not in valid_codes
    )

    for payload, detail in (
        ({**credentials, "password": "wrong-password"}, "Invalid credentials"),
        (credentials, "MFA code required"),
        ({**credentials, "totp_code": wrong_code}, "Invalid MFA code"),
    ):
        response = client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 401
        assert response.json() == {"detail": detail}
        assert "payseal_refresh" not in response.cookies
        assert db_session.scalar(select(func.count()).select_from(RefreshSession)) == 0
        assert client.get("/api/v1/auth/me").status_code == 401

    response = client.post("/api/v1/auth/login", json={**credentials, "totp_code": totp.now()})
    assert response.status_code == 200
    assert "payseal_refresh" in response.cookies
    assert db_session.scalar(select(func.count()).select_from(RefreshSession)) == 1
    assert (
        client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {response.json()['access_token']}"},
        ).status_code
        == 200
    )
