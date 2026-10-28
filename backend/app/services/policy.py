from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovalRequirement:
    approvers: int
    recent_mfa: bool


class ApprovalPolicy:
    """Central backend policy; replace with persisted per-organization rules later."""

    def evaluate(self, amount_minor: int, currency: str) -> ApprovalRequirement:
        if currency != "VND":
            return ApprovalRequirement(1, True)
        if amount_minor < 10_000_000:
            return ApprovalRequirement(1, False)
        if amount_minor <= 100_000_000:
            return ApprovalRequirement(1, True)
        return ApprovalRequirement(2, True)
