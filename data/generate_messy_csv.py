"""
Generate messy CSV invoice for testing parser robustness.

Usage: python data/generate_messy_csv.py
"""

import csv
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "invoices")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "invoice_1022.csv")

    # Messy CSV: columnar layout with OCR-like numbers (O instead of 0), extra blank row,
    # inconsistent spacing. Parser should still extract with some tolerance.
    rows = [
        ["invoice_number", "vendor", "date", "due_date", "item", "qty", "unit_price", "line_total"],
        ["INV-1022", "Messy CSV Supplies Inc", "2026-01-31", "2026-02-28", "WidgetA", "5", "25O.OO", "125O.OO"],
        ["", "", "", "", "WidgetB", "3", "5OO.OO", "15OO.OO"],
        ["", "", "", "", "GadgetX", "2", "75O.OO", "15OO.OO"],
        [],
        ["", "", "", "", "", "", "Subtotal", "425O.OO"],
        ["", "", "", "", "", "", "Tax (8%)", "34O.OO"],
        ["", "", "", "", "", "", "Total", "459O.OO"],
        ["payment_terms", "Net 30", "", "", "", "", "", ""],
    ]

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        for row in rows:
            writer.writerow(row)

    print("  Created invoice_1022.csv")


if __name__ == "__main__":
    print("Generating messy CSV invoice...")
    main()
    print("Done.")
