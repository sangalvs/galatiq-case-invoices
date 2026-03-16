# Implementation Guide

## Overview

Multi-agent AI invoice processing system. Invoices flow through a 5-stage LangGraph pipeline:

```
Ingestion → Validation → Fraud Detection → Approval → Payment
```

Supports PDF, JSON, CSV, XML, TXT, and email (.eml) formats. Outputs to SQLite with a full audit trail.

---

## Setup

**Requirements:** Python 3.9+

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Initialize the database
python setup_db.py
```

This creates `inventory.db` with 4 sample inventory items (WidgetA, WidgetB, GadgetX, FakeItem) and exchange rates for USD, EUR, GBP, CAD, JPY.

**Optional — Enable real LLM (xAI Grok):**

Create a `.env` file in the project root:
```
XAI_API_KEY=your_key_here
```

Without a key, the system uses a deterministic MockLLM that produces accurate results.

---

## Running the System

### CLI

Process a single invoice:
```bash
python main.py --invoice_path=data/invoices/invoice_1001.txt --verbose
```

Process a directory of invoices:
```bash
python main.py --invoice_path=data/invoices/
```

### Streamlit Dashboard

```bash
streamlit run app.py
```

Four modes available in the UI:
- **Single Invoice** — upload or paste an invoice and step through the pipeline
- **Batch Processing** — process a folder of invoices at once
- **Email Inbox** — process `.eml` files from `data/inbox/`
- **Analytics** — view processed invoice history and fraud stats from the DB

### REST API

```bash
uvicorn api:app --reload
```

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

Key endpoints:
| Method | Path | Description |
|--------|------|-------------|
| POST | `/process` | Process a single invoice file |
| POST | `/process/batch` | Process all invoices in a directory |
| GET | `/invoices` | List all processed invoices |
| GET | `/invoices/{id}` | Get invoice details and audit log |
| GET | `/analytics` | Fraud and approval summary stats |
| GET | `/health` | Health check |

---

## Tests

```bash
python -m pytest tests/ -q
```

### Test Modules

Each pipeline module has dedicated unit tests:

| Module | Test File | What It Covers |
|--------|-----------|---------------|
| Parsers | `tests/test_parsers.py` | JSON, CSV, XML, TXT parsers; OCR artifact correction; parser registry dispatch |
| Arithmetic | `tests/test_arithmetic.py` | Subtotal/tax/total verification with ±2% tolerance |
| Fuzzy matching | `tests/test_fuzzy.py` | Item name normalization, OCR variants (W1dgetB → WidgetB), confidence thresholds |
| Validation | `tests/test_validation.py` | Stock checks, unknown items, negative quantities, duplicate detection |
| Fraud | `tests/test_fraud.py` | Each fraud signal scored independently; composite risk thresholds |
| Approval | `tests/test_approval.py` | Rule-based decisions, threshold gates, LLM critique path |
| End-to-end | `tests/test_evaluation.py` | Ground truth scorecard across all 16 invoices; extraction, validation, fraud, and approval accuracy gates |

Run just the fast unit tests (no LLM calls, ~35s):
```bash
python -m pytest tests/test_parsers.py tests/test_arithmetic.py tests/test_fuzzy.py -q
```

Run the full evaluation scorecard (~7 min with real LLM):
```bash
python -m pytest tests/test_evaluation.py -v
```

### Test Data

The `data/invoices/` directory contains 22 invoices across all supported formats, including deliberately challenging cases generated to stress-test the pipeline:

**Standard invoices (INV-1001 to INV-1016):** 16 invoices with known ground truth used by the evaluation harness. Cover happy paths, stock exceeded, unknown items, zero-stock fraud, negative quantities, arithmetic errors, OCR noise, multi-currency (EUR), and duplicate detection.

**Additional messy test files generated for robustness:**

| File | Format | What It Tests |
|------|--------|--------------|
| `invoice_1017.pdf` | PDF | Scanned PDF with heavy OCR artifacts and irregular layout |
| `invoice_1018.pdf` | PDF | Multi-page PDF with embedded tables |
| `invoice_1019.pdf` | PDF | PDF with mixed fonts and misaligned columns |
| `invoice_1020.pdf` | PDF | Minimal PDF with missing optional fields |
| `invoice_1021.json` | JSON | Malformed/missing fields, non-standard key names |
| `invoice_1022.csv` | CSV | Inconsistent delimiters, extra whitespace, mixed numeric formats |

These files exercise the parser fallback chain (parser → LLM extraction → self-correction) and validate that the system degrades gracefully on real-world messy input rather than crashing.

---

## Error Handling & LLM Resilience

### LLM Client Configuration

The Grok client (`src/llm.py`) is configured with a 30-second timeout and 2 automatic retries for transient errors (network blips, rate limits). These retries happen at the HTTP level before any application-level error handling kicks in:

```python
ChatOpenAI(timeout=30, max_retries=2, ...)
```

### Failure Behavior by Stage

LLM failures are never silently swallowed. The guiding principle is: **failures must either surface a user-facing message or escalate to manual review — never silently degrade safety.**

| Stage | Failure | Behavior |
|-------|---------|----------|
| **Ingestion** — primary extraction | LLM timeout/error | Pipeline halted. `invoice_parse_error` set in state. User sees: *"LLM extraction failed — please try again shortly."* |
| **Ingestion** — self-correction loop | LLM timeout/error | Loop exits early. Partial extraction kept with validation warnings surfaced downstream. |
| **Fraud** — LLM pattern analysis | LLM timeout/error | Warning logged. `llm_check_failed=True` set in state. Rule-based signals still apply. |
| **Approval** — sees `llm_check_failed` | (from fraud stage) | Invoice demoted from `APPROVED` → `FLAGGED`. Reason: *"Fraud analysis incomplete — manual review required."* |
| **Approval** — VP critique | LLM timeout/error | If invoice was `APPROVED`, demoted to `FLAGGED`. Reason: *"Approval critique unavailable — manual review required."* |

### Key Safety Decisions

- **Fraud LLM failure never scores 0.** Scoring 0 would let potentially fraudulent invoices sail through. Instead, the invoice is flagged for human review.
- **Approval LLM failure never auto-approves.** If the VP critique can't run, the invoice is held for manual review rather than approved on rule-based signals alone.
- **Ingestion failure is terminal.** If the LLM can't extract a structured invoice and the deterministic parser also failed, the pipeline halts cleanly — there's nothing safe to validate or approve.
- **Error messages are user-readable.** All `RuntimeError` messages (e.g. *"please try again shortly"*) appear in the processing log, the Streamlit dashboard, and the API response — not just in server logs.

---

## Additional Features

### Multi-format Ingestion

The ingestion agent tries a deterministic parser first (JSON, CSV, XML, TXT, PDF), then falls back to LLM extraction if the parser fails or returns incomplete data. It also runs a self-correction loop (configurable retries) when extracted totals don't reconcile.

### Fraud Scoring

Five independent signals are scored 0–10 and combined into a 0–100 composite:

| Signal | What It Checks |
|--------|---------------|
| Urgency | Keywords like "urgent", "wire transfer", "pay now" |
| Price Anomaly | Unit prices outside ±20% of catalog price |
| Vendor Risk | Unknown vendors, suspicious name patterns |
| Data Integrity | Missing fields, negative quantities, zero-stock orders |
| LLM Pattern | Grok/MockLLM heuristic analysis of the full invoice |

Risk levels: LOW (0–25) → MEDIUM (26–50) → HIGH (51–75) → CRITICAL (76–100)

### LLM Optimization Flags

Set these in `.env` to reduce API calls in production:

```
SKIP_LLM_FRAUD_WHEN_HIGH=true   # Skip LLM fraud check when rule-based signals already flag HIGH
SKIP_LLM_CRITIQUE_WHEN_OBVIOUS=true  # Skip LLM approval critique on clear approvals/rejections
PARSER_FIRST_FOR_UNSTRUCTURED=true   # Try deterministic parser before LLM (default: true)
INGESTION_REFINE_RETRIES=1      # Number of LLM self-correction retries on extraction failure
```

### Email Ingestion

Drop `.eml` files into `data/inbox/`. The system extracts invoice attachments (PDF, JSON, CSV, XML, TXT) and processes them through the same pipeline. Accessible via the Streamlit dashboard's "Email Inbox" mode.

### Duplicate Detection

The system detects duplicate invoice numbers against the SQLite `processed_invoices` table. Duplicates are flagged in the processing log and re-run in audit-only mode (not recorded again).

### Multi-currency Support

Exchange rates are stored in the DB (USD, EUR, GBP, CAD, JPY). All invoice totals are converted to USD for approval threshold comparisons. Unknown currencies default to a 1.0 rate with a warning.

### Auto-approval Threshold

Invoices above $10,000 USD are flagged for human review by default. To enable auto-approval above threshold (demo/test mode):

```
AUTO_APPROVE_OVER_THRESHOLD=true
```

---

## Future: Gmail Auto-ingestion

The system already handles `.eml` files via `src/email_ingestion.py`. Connecting a live Gmail inbox requires two additions: a Gmail poller and a bridge that feeds fetched messages into the existing email ingestion pipeline.

### How it would work

```
Gmail API (polling / Push) → fetch raw email → email_ingestion.py → pipeline
```

The existing `src/email_ingestion.py` already parses raw `.eml` content and extracts attachments — no changes needed there. The new work is only in the Gmail connectivity layer.

### Step 1 — Google Cloud credentials

1. Create a project at [console.cloud.google.com](https://console.cloud.google.com)
2. Enable the **Gmail API**
3. Create an **OAuth 2.0 Client ID** (Desktop app) and download `credentials.json`
4. Add to `.env`:
```
GMAIL_CREDENTIALS_PATH=credentials.json
GMAIL_TOKEN_PATH=token.json
GMAIL_POLL_LABEL=INBOX          # or a dedicated label like "invoices"
GMAIL_POLL_INTERVAL_SECONDS=60
```

### Step 2 — Install the Gmail client

```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

### Step 3 — Gmail poller module

Create `src/gmail_poller.py`:

```python
import base64, os, time
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from src.email_ingestion import process_eml_file
from src.agents.graph import run_pipeline

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

def get_gmail_service(credentials_path, token_path):
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

def fetch_unread_invoice_emails(service, label="INBOX"):
    results = service.users().messages().list(
        userId="me", labelIds=[label], q="is:unread"
    ).execute()
    return results.get("messages", [])

def fetch_raw_message(service, msg_id):
    msg = service.users().messages().get(
        userId="me", id=msg_id, format="raw"
    ).execute()
    return base64.urlsafe_b64decode(msg["raw"])

def mark_as_read(service, msg_id):
    service.users().messages().modify(
        userId="me", id=msg_id,
        body={"removeLabelIds": ["UNREAD"]}
    ).execute()

def poll_and_process(credentials_path, token_path, label="INBOX", interval=60):
    service = get_gmail_service(credentials_path, token_path)
    print(f"Polling Gmail ({label}) every {interval}s...")
    while True:
        for msg in fetch_unread_invoice_emails(service, label):
            raw_eml = fetch_raw_message(service, msg["id"])
            attachments = process_eml_file(raw_eml)   # existing parser
            for file_path in attachments:
                result = run_pipeline(file_path)
                print(f"Processed: {result.get('invoice', {}).get('invoice_number')} "
                      f"→ {result.get('approval_result', {}).get('decision')}")
            mark_as_read(service, msg["id"])
        time.sleep(interval)
```

Run the poller:
```bash
python -c "
from src.gmail_poller import poll_and_process
import os
poll_and_process(
    credentials_path=os.getenv('GMAIL_CREDENTIALS_PATH', 'credentials.json'),
    token_path=os.getenv('GMAIL_TOKEN_PATH', 'token.json'),
    label=os.getenv('GMAIL_POLL_LABEL', 'INBOX'),
    interval=int(os.getenv('GMAIL_POLL_INTERVAL_SECONDS', 60)),
)
"
```

### Step 4 — Optional: Gmail Push notifications (instead of polling)

For real-time ingestion, use Gmail's **Pub/Sub push** instead of polling:

1. Create a Google Cloud Pub/Sub topic and grant Gmail publish rights
2. Call `users.watch()` to subscribe your inbox to the topic
3. Set up a webhook endpoint (e.g., `POST /gmail/webhook` in `api.py`) that receives Pub/Sub notifications and triggers `poll_and_process` for the specific message

This eliminates the polling interval and processes invoices within seconds of receipt.

### Filtering to invoice emails only

To avoid processing non-invoice emails, apply a Gmail filter or tighten the search query:

```python
# In fetch_unread_invoice_emails, change q= to:
q="is:unread has:attachment (subject:invoice OR subject:inv)"
```

Or create a Gmail label (e.g., `invoices`) and route matching emails there via Gmail's built-in filters, then set `GMAIL_POLL_LABEL=invoices`.
