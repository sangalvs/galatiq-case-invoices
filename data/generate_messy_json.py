"""
Generate messy JSON invoice for testing parser robustness.

Usage: python data/generate_messy_json.py
"""

import json
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "invoices")

# Messy JSON: nested structures, alternate keys, typos, extra noise fields
MESSY_JSON = {
    "inv_num": "INV-1021",  # alternate key for invoice_number
    "invoice_number": "INV-1021",  # duplicate with typo variant
    "vendor_name": "Chaotic Data Corp",  # alternate key
    "vendor": {"name": "Chaotic Data Corp", "legal_name": "Chaotic Data Corporation LLC"},
    "bill_to": "ACME Corp",
    "invoice_date": "2026-01-31",  # alternate
    "date": "2026-01-31",
    "due_date": "2026-02-28",
    "dueDate": "2026-02-28",  # camelCase variant
    "line_items": [
        {"item": "WidgetA", "qty": 5, "quantity": 5, "unit_price": 250.0, "unitPrice": 250.0},
        {"item": "WidgetB", "qty": 3, "quantity": 3, "unit_price": 500.0, "amt": 1500},
        {"product": "GadgetX", "item": "GadgetX", "quantity": 2, "unit_price": 750.0},
    ],
    "lineItems": [  # duplicate with different structure
        {"name": "WidgetA", "qty": 5, "price": 250},
    ],
    "subtotal": 4750.0,
    "sub_total": 4750.0,  # typo variant
    "tax_rate": 0.08,
    "taxRate": 0.08,
    "tax_amount": 380.0,
    "taxAmount": 380.0,
    "total": 5130.0,
    "grand_total": 5130.0,
    "currency": "USD",
    "payment_terms": "Net 30",
    "paymentTerms": "Net 30",
    "notes": "Ref PO-20260131",
    "_internal_id": "xyz-789",
    "metadata": {"generated": "2026-01-31", "version": "2.0"},
    "extra_noise": ["unused", "fields", "for", "testing"],
}


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "invoice_1021.json")
    with open(path, "w") as f:
        json.dump(MESSY_JSON, f, indent=2)
    print(f"  Created invoice_1021.json")


if __name__ == "__main__":
    print("Generating messy JSON invoice...")
    main()
    print("Done.")
