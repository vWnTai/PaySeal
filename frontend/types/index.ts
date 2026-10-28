export type Payment = {
  id: string;
  organization_id: string;
  status: string;
  current_version: number;
  invoice_reference: string;
  currency: string;
  amount_minor: number;
  beneficiary_id: string;
  beneficiary_name: string;
  bank_code: string;
  account_masked: string;
  expires_at: string;
  created_at: string;
  approvals_required: number;
  approvals_completed: number;
  recent_mfa_required: boolean;
  public_url?: string | null;
};

export type Beneficiary = {
  id: string;
  organization_id: string;
  name: string;
  bank_code: string;
  account_masked: string;
  status: string;
  verified_at?: string | null;
  created_at: string;
};
export type AuditEvent = {
  id: string;
  event_type: string;
  object_type: string;
  object_id: string;
  event_data: Record<string, unknown>;
  event_hash: string;
  created_at: string;
  correlation_id: string;
};
export type Verification = {
  status: string;
  signature_valid: boolean;
  issuer_verified: boolean;
  document_status: string;
  expired: boolean;
  revoked: boolean;
  superseded: boolean;
  organization: {
    name: string;
    tax_id: string;
    domain: string;
    verification_level: number;
    verification_status?: string;
    verification_method?: string | null;
    signed_verification_level?: number;
  } | null;
  payment: {
    amount_minor: number;
    currency: string;
    beneficiary: string;
    bank_code: string;
    account_masked: string;
    invoice_reference: string;
  } | null;
  issued_at?: string;
  expires_at?: string;
  warnings: string[];
};

export type User = {
  id: string;
  full_name: string;
  email: string;
  mfa_enabled: boolean;
  is_platform_reviewer?: boolean;
  organizations: { id: string; role: string }[];
};

export type Organization = {
  id: string;
  name: string;
  tax_id: string;
  domain: string;
  verification_level: number;
  verification_status?: string;
  verification_method?: string | null;
  verification_valid_until?: string | null;
  status: string;
};

export type Member = { id: string; email: string; full_name: string; role: string };
export type LoginResponse = { access_token: string; csrf_token: string };

export type BusinessVerification = {
  id: string;
  organization_id: string;
  profile: { name: string; tax_id: string; domain: string };
  representative_name: string;
  contact_email: string;
  registered_address: string;
  registration_number: string;
  document_sha256: string;
  status: string;
  review_reason: string | null;
  reviewed_at: string | null;
  valid_until: string | null;
  created_at: string;
};

export type Transfer = {
  id: string;
  organization_id: string;
  payment_request_id: string;
  payment_version: number;
  provider: string;
  provider_reference: string;
  status: string;
  amount_minor: number;
  currency: string;
  beneficiary_name: string;
  bank_code: string;
  account_last4: string;
  invoice_reference: string;
  failure_reason: string | null;
  created_at: string;
  completed_at: string | null;
  reconciled_at: string | null;
};

export type PaymentReadiness = {
  provider: string;
  infrastructure_ready: boolean;
  blockers: string[];
  business_verified: boolean;
  collection_connected: boolean;
  payout_connected: boolean;
};

export type PaymentChannel = {
  id: string;
  purpose: "COLLECTION" | "PAYOUT";
  status: string;
  bank_bin: string;
  account_name: string;
  account_last4: string;
  created_at: string;
};

export type Collection = {
  id: string;
  invoice_reference: string;
  order_code: number;
  amount_minor: number;
  amount_paid: number;
  status: string;
  checkout_url: string | null;
  expires_at: string;
  reconciled_at: string | null;
  created_at: string;
};
