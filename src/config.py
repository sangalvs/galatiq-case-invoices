import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "invoices"
DB_PATH = BASE_DIR / "inventory.db"

XAI_API_KEY = os.getenv("XAI_API_KEY", "")
XAI_BASE_URL = "https://api.x.ai/v1"
XAI_MODEL = "grok-3-mini-fast"

USE_MOCK_LLM = not bool(XAI_API_KEY)

APPROVAL_THRESHOLD = 10_000.00

# When False, invoices over APPROVAL_THRESHOLD are FLAGGED (no auto-payment). When True, they are APPROVED with requires_scrutiny (demo mode).
AUTO_APPROVE_OVER_THRESHOLD = os.getenv("AUTO_APPROVE_OVER_THRESHOLD", "false").lower() in ("1", "true", "yes")

EXCHANGE_RATES_FALLBACK = {
    "USD": 1.00,
    "EUR": 1.08,
    "GBP": 1.27,
    "CAD": 0.74,
    "JPY": 0.0067,
}

FRAUD_RISK_THRESHOLDS = {
    "low": 25,
    "medium": 50,
    "high": 75,
    "critical": 100,
}

URGENCY_KEYWORDS = [
    "urgent",
    "immediately",
    "wire transfer",
    "asap",
    "pay now",
    "penalty",
    "penalties",
]

# LLM optimization flags
SKIP_LLM_FRAUD_WHEN_HIGH = os.getenv("SKIP_LLM_FRAUD_WHEN_HIGH", "false").lower() in ("1", "true", "yes")
SKIP_LLM_CRITIQUE_WHEN_OBVIOUS = os.getenv("SKIP_LLM_CRITIQUE_WHEN_OBVIOUS", "false").lower() in ("1", "true", "yes")
INGESTION_REFINE_RETRIES = int(os.getenv("INGESTION_REFINE_RETRIES", "1"))
PARSER_FIRST_FOR_UNSTRUCTURED = os.getenv("PARSER_FIRST_FOR_UNSTRUCTURED", "true").lower() in ("1", "true", "yes")
