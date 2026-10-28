from __future__ import annotations

import pytest
from app.api.dependencies import get_db
from app.core.config import settings
from app.main import app, rate_buckets
from app.models import Base
from app.services.runtime import root_authority, signing_provider
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


class FakeStorage:
    objects: dict[str, bytes] = {}

    def put_pdf(self, object_key: str, data: bytes) -> None:
        self.objects[object_key] = data

    def get_pdf(self, object_key: str) -> bytes:
        return self.objects[object_key]


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(settings, "signing_key_directory", str(tmp_path / "organizations"))
    monkeypatch.setattr(settings, "payseal_root_key_path", str(tmp_path / "root-private.pem.enc"))
    monkeypatch.setattr(settings, "payseal_root_public_key_path", str(tmp_path / "root-public.pem"))
    signing_provider.cache_clear()
    root_authority.cache_clear()
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        signing_provider.cache_clear()
        root_authority.cache_clear()


@pytest.fixture()
def client(db_session, monkeypatch):
    import app.api.business_verification as verification_api
    import app.api.payments as payment_api
    import app.services.payments as payment_service

    FakeStorage.objects.clear()
    rate_buckets.clear()
    monkeypatch.setattr(payment_service, "MinioStorage", FakeStorage)
    monkeypatch.setattr(payment_api, "MinioStorage", FakeStorage)
    monkeypatch.setattr(verification_api, "MinioStorage", FakeStorage)

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
