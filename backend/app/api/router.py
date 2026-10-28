from fastapi import APIRouter

from app.api import (
    audit,
    auth,
    beneficiaries,
    business_verification,
    organizations,
    payment_integrations,
    payments,
    public,
    transfers,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(beneficiaries.router)
api_router.include_router(payments.router)
api_router.include_router(public.router)
api_router.include_router(audit.router)
api_router.include_router(business_verification.router)
api_router.include_router(transfers.router)
api_router.include_router(payment_integrations.router)
