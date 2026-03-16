from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    item: str
    quantity: Union[int, float]
    unit_price: float
    amount: Optional[float] = None
    note: Optional[str] = None

    @property
    def computed_amount(self) -> float:
        return round(self.quantity * self.unit_price, 2)


class Invoice(BaseModel):
    invoice_number: str
    vendor: str
    date: Optional[str] = None
    due_date: Optional[str] = None
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Optional[float] = None
    tax_rate: Optional[float] = None
    tax_amount: Optional[float] = None
    total: Optional[float] = None
    currency: str = "USD"
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    revision: Optional[str] = None
    raw_text: Optional[str] = None


class ItemFlag(BaseModel):
    item: str
    issue: str  # "unknown_item", "stock_exceeded", "zero_stock", "negative_qty", "price_anomaly"
    detail: str
    severity: str = "error"  # "error", "warning", "info"


class ArithmeticFlag(BaseModel):
    field: str  # "subtotal", "tax", "total"
    expected: float
    actual: Optional[float]
    detail: str


class ValidationResult(BaseModel):
    passed: bool
    item_flags: list[ItemFlag] = Field(default_factory=list)
    arithmetic_flags: list[ArithmeticFlag] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: str = ""


class FraudSignal(BaseModel):
    category: str  # "urgency", "price_anomaly", "vendor_risk", "data_integrity", "pattern_analysis"
    description: str
    score: int = Field(ge=0, le=10)


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FraudRecommendation(str, Enum):
    PROCEED = "proceed"
    FLAG_FOR_REVIEW = "flag_for_review"
    REJECT = "reject"


class FraudResult(BaseModel):
    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    signals: list[FraudSignal] = Field(default_factory=list)
    llm_reasoning: str = ""
    recommendation: FraudRecommendation


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    FLAGGED = "flagged"


class ApprovalResult(BaseModel):
    decision: ApprovalDecision
    reasoning: str
    critique: str = ""
    requires_scrutiny: bool = False
    fraud_considerations: str = ""


class PaymentStatus(str, Enum):
    PAID = "paid"
    REJECTED = "rejected"
    ERROR = "error"


class PaymentResult(BaseModel):
    status: PaymentStatus
    vendor: str
    amount: float
    currency: str = "USD"
    detail: str = ""


class ProcessingLogEntry(BaseModel):
    invoice_number: str
    stage: str
    action: str
    result: str
    details: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
