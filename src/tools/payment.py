"""Mock payment API."""

from __future__ import annotations

from src.models import PaymentResult, PaymentStatus


def mock_payment(vendor: str, amount: float, currency: str = "USD") -> PaymentResult:
    if not vendor:
        return PaymentResult(
            status=PaymentStatus.ERROR,
            vendor=vendor,
            amount=amount,
            currency=currency,
            detail="Payment failed: no vendor specified",
        )

    if amount <= 0:
        return PaymentResult(
            status=PaymentStatus.ERROR,
            vendor=vendor,
            amount=amount,
            currency=currency,
            detail=f"Payment failed: invalid amount ${amount:.2f}",
        )

    return PaymentResult(
        status=PaymentStatus.PAID,
        vendor=vendor,
        amount=amount,
        currency=currency,
        detail=f"Paid ${amount:,.2f} {currency} to {vendor}",
    )
