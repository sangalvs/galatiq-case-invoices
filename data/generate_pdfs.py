"""
Optional utility to generate PDF versions of the sample invoices.

Requires: pip install fpdf2

Usage: python data/generate_pdfs.py
"""

import os
import sys

try:
    from fpdf import FPDF
except ImportError:
    print("fpdf2 is required to generate PDFs: pip install fpdf2")
    sys.exit(1)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "invoices")


def create_clean_invoice():
    """INV-1011: Clean, well-structured invoice."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "INVOICE", ln=True, align="C")
    pdf.ln(5)

    pdf.set_font("Helvetica", "", 11)
    for label, value in [
        ("Invoice Number:", "INV-1011"),
        ("Vendor:", "Summit Manufacturing Co."),
        ("Date:", "2026-01-20"),
        ("Due Date:", "2026-02-20"),
    ]:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(45, 7, label)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 7, value, ln=True)

    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 11)
    for header, w in [("Item", 80), ("Qty", 25), ("Unit Price", 35), ("Amount", 35)]:
        align = "C" if header == "Qty" else ("R" if header != "Item" else "L")
        pdf.cell(w, 8, header, border=1, align=align)
    pdf.ln()

    pdf.set_font("Helvetica", "", 11)
    items = [("WidgetA", 6, 250.00), ("WidgetB", 3, 500.00)]
    subtotal = 0
    for item, qty, price in items:
        amount = qty * price
        subtotal += amount
        pdf.cell(80, 7, item, border=1)
        pdf.cell(25, 7, str(qty), border=1, align="C")
        pdf.cell(35, 7, f"${price:,.2f}", border=1, align="R")
        pdf.cell(35, 7, f"${amount:,.2f}", border=1, align="R")
        pdf.ln()

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(140, 7, "Total:", align="R")
    pdf.cell(35, 7, f"${subtotal:,.2f}", align="R", ln=True)

    pdf.output(os.path.join(OUTPUT_DIR, "invoice_1011.pdf"))
    print("  Created invoice_1011.pdf")


def create_messy_invoice():
    """INV-1012: Scanned-style messy invoice with OCR-like artifacts."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Courier", "", 12)

    lines = [
        "                    I N V O I C E",
        "",
        "  FROM:  QuickShip Distributers",
        "         (formerly FastShip Ltd.)",
        "",
        "  INV NO:    INV 1012",
        "  DATE:      26-Jan-2O26",
        "  DUE:       25-Feb-2026",
        "",
        "  TO:    ACME Corp",
        "         Attn: Accounts Payble",
        "",
        "  ----------------------------------------",
        "  ITEM          QTY    PRICE     TOTAL",
        "  ----------------------------------------",
        "  Widget A       12    $250     $3,000.00",
        "  WidgetB         7    $500     $3,500.O0",
        "  Gadget X        4    $750     $3,000.00",
        "  ----------------------------------------",
        "                  SUBTOTAL:     $9,500.00",
        "                  TAX (5%):       $475.00",
        "                  TOTAL:        $9,975.00",
        "",
        "  NOTES: Ref PO-20260115. Deliver to",
        "         warehouse dock B. Contact Jim",
        "         at ext 4421 with questions.",
        "",
        "  Terms: Net 30",
    ]

    for line in lines:
        pdf.cell(0, 6, line, ln=True)

    pdf.output(os.path.join(OUTPUT_DIR, "invoice_1012.pdf"))
    print("  Created invoice_1012.pdf")


def create_bulk_invoice():
    """INV-1013: Large multi-line-item invoice."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Bulk Order Invoice", ln=True, align="C")
    pdf.ln(3)

    pdf.set_font("Helvetica", "", 10)
    for line in [
        "Invoice: INV-1013                              Date: 2026-01-24",
        "Vendor: Atlas Industrial Supply                 Due:  2026-03-24",
        "Terms: Net 60",
    ]:
        pdf.cell(0, 6, line, ln=True)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 10)
    for header, w in [("Item", 60), ("Qty", 20), ("Unit Price", 30), ("Amount", 30), ("Notes", 40)]:
        pdf.cell(w, 7, header, border=1)
    pdf.ln()

    pdf.set_font("Helvetica", "", 10)
    bulk_items = [
        ("WidgetA", 15, 250.00, ""),
        ("WidgetB", 10, 500.00, ""),
        ("GadgetX", 5, 750.00, ""),
        ("WidgetA", 5, 240.00, "Volume discount"),
        ("WidgetB", 8, 480.00, "Volume discount"),
        ("GadgetX", 3, 750.00, "Expedited"),
        ("WidgetA", 2, 250.00, "Replacement"),
        ("GadgetX", 1, 750.00, "Sample"),
    ]

    running_total = 0
    for item, qty, price, note in bulk_items:
        amount = qty * price
        running_total += amount
        pdf.cell(60, 6, item, border=1)
        pdf.cell(20, 6, str(qty), border=1, align="C")
        pdf.cell(30, 6, f"${price:,.2f}", border=1, align="R")
        pdf.cell(30, 6, f"${amount:,.2f}", border=1, align="R")
        pdf.cell(40, 6, note, border=1)
        pdf.ln()

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    tax = running_total * 0.07
    grand_total = running_total + tax
    pdf.cell(110, 7, "Subtotal:", align="R")
    pdf.cell(30, 7, f"${running_total:,.2f}", align="R", ln=True)
    pdf.cell(110, 7, "Tax (7%):", align="R")
    pdf.cell(30, 7, f"${tax:,.2f}", align="R", ln=True)
    pdf.cell(110, 7, "Grand Total:", align="R")
    pdf.cell(30, 7, f"${grand_total + 50:,.2f}", align="R", ln=True)

    pdf.output(os.path.join(OUTPUT_DIR, "invoice_1013.pdf"))
    print("  Created invoice_1013.pdf")


def create_ocr_degraded_invoice():
    """INV-1017: Heavily OCR-degraded with O↔0, l↔1, mixed fonts, stray characters."""
    pdf = FPDF()
    pdf.add_page()
    # Simulate mixed fonts and sizes
    pdf.set_font("Courier", "", 10)
    lines = [
        "  *** SCANNED DOCUMENT - QUALITY MAY VARY ***",
        "",
        "  I N V 0 I C E    # 1 0 1 7",
        "  ~~~ ~~~ ~~~ ~~~ ~~~ ~~~ ~~~ ~~~ ~~~",
        "",
        "  Vndr:  M3gaW1dget C0rp (f0rmerly Widgets Inc)",
        "  Addr:  123 Main St, Anytown ST 12345",
        "",
        "  Inv#:  INV-1O17   (note: letter O not zero)",
        "  D4te:  2O-Jan-2O26   DUE:  2O-Feb-2O26",
        "  Ref:   P0-2O26O115",
        "",
        "  IT3M            QTY    PR1CE      AM0UNT",
        "  ----            ---    -----      ------",
        "  W1dget A         l2    $25O.OO    $3,OOO.OO",
        "  W1dgetB          7     $5OO.OO    $3,5OO.OO",
        "  Gadget X         4     $75O.OO    $3,OOO.OO",
        "  SuperGizmo       l     $4OO.OO    $4OO.OO",
        "  ----            ---    -----      ------",
        "  SUBT0TAL:                    $9,9OO.OO",
        "  TAX (5%):                       $495.OO",
        "  T0TAL:                       $l0,395.OO",
        "",
        "  N0TES: Urgent - wire transfer preferred.",
        "  Contact: j1m@megaw1dget.n0product.com",
        "",
        "  Terms: Net 30 | Conf#: X7K9-M2L",
    ]
    for line in lines:
        pdf.cell(0, 5, line, ln=True)
    pdf.output(os.path.join(OUTPUT_DIR, "invoice_1017.pdf"))
    print("  Created invoice_1017.pdf")


def create_multipage_watermark_invoice():
    """INV-1018: Multi-page with headers/footers, watermarks, handwritten-style notes."""
    pdf = FPDF()
    for page_num in range(1, 4):
        pdf.add_page()
        pdf.set_font("Helvetica", "", 8)
        # Header
        pdf.cell(0, 6, f"  Page {page_num} of 3  |  CONFIDENTIAL  |  INV-1018", ln=True)
        pdf.ln(2)
        # Watermark-style text (faded effect via small font)
        pdf.set_font("Helvetica", "", 6)
        pdf.set_text_color(180, 180, 180)
        for _ in range(3):
            pdf.cell(0, 4, "  DRAFT - NOT FOR PAYMENT - INTERNAL USE ONLY  ", ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 10)
        pdf.ln(2)

        if page_num == 1:
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 8, "INVOICE INV-1018", ln=True)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 6, "Vendor: Global Supply Chain Ltd.", ln=True)
            pdf.cell(0, 6, "Date: 2026-01-28  Due: 2026-02-28", ln=True)
            pdf.ln(5)
            pdf.set_font("Helvetica", "B", 10)
            for h, w in [("Item", 70), ("Qty", 25), ("Price", 35), ("Amount", 40)]:
                pdf.cell(w, 6, h, border=1)
            pdf.ln()
            pdf.set_font("Helvetica", "", 10)
            for item, qty, price in [("WidgetA", 20, 250), ("WidgetB", 15, 500), ("GadgetX", 8, 750)]:
                amt = qty * price
                pdf.cell(70, 6, item, border=1)
                pdf.cell(25, 6, str(qty), border=1)
                pdf.cell(35, 6, f"${price}", border=1)
                pdf.cell(40, 6, f"${amt:,.2f}", border=1)
                pdf.ln()
            pdf.ln(3)
            pdf.cell(130, 6, "Subtotal:", align="R")
            pdf.cell(40, 6, "$21,250.00", ln=True)
            pdf.cell(130, 6, "Tax (5%):", align="R")
            pdf.cell(40, 6, "$1,062.50", ln=True)
            pdf.cell(130, 6, "Total:", align="R")
            pdf.cell(40, 6, "$22,312.50", ln=True)
            pdf.ln(5)
            pdf.set_font("Courier", "", 9)
            pdf.cell(0, 5, "  [Handwritten note: Please expedite - needed for Q1 close]", ln=True)
        elif page_num == 2:
            pdf.cell(0, 6, "Terms: Net 60. Wire transfer to account on file.", ln=True)
            pdf.cell(0, 6, "Notes: Bulk order discount applied. PO-20260128.", ln=True)
            pdf.ln(5)
            pdf.set_font("Courier", "", 9)
            pdf.cell(0, 5, "  [Margin note: Verify vendor bank details before payment]", ln=True)
        else:
            pdf.cell(0, 6, "Authorized by: _________________  Date: ___________", ln=True)
            pdf.ln(10)
            pdf.set_font("Courier", "", 8)
            pdf.cell(0, 4, "  Footer: This invoice is subject to our standard terms.", ln=True)
            pdf.cell(0, 4, "  Invoice generated 2026-01-28. Valid for 90 days.", ln=True)

        # Footer
        pdf.ln(10)
        pdf.set_font("Helvetica", "", 6)
        pdf.cell(0, 4, f"  --- Page {page_num}/3 --- INV-1018 ---", ln=True)

    pdf.output(os.path.join(OUTPUT_DIR, "invoice_1018.pdf"))
    print("  Created invoice_1018.pdf")


def create_prose_invoice():
    """INV-1019: Minimal structure - prose-style invoice, no clear columns."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Times", "", 11)
    prose = """
Dear Customer,

This letter serves as our invoice for the goods delivered on January 30, 2026.

We are billing you for the following: First, 5 units of WidgetA at two hundred fifty dollars each,
which comes to $1,250. Second, 3 units of WidgetB at five hundred dollars per unit, totaling $1,500.
Third, 2 units of GadgetX at seven hundred fifty dollars each, that is $1,500. So the subtotal for
all items is four thousand two hundred fifty dollars ($4,250.00). We have applied a 6% sales tax
of $255.00, making the total amount due four thousand five hundred five dollars ($4,505.00).

Our invoice number is INV-1019. The vendor is Riverside Trading Co. Payment is due by
February 28, 2026. Terms are Net 30. Please reference PO-20260130 when remitting payment.

Thank you for your business.
"""
    for para in prose.strip().split("\n\n"):
        pdf.multi_cell(0, 6, para.strip())
        pdf.ln(2)
    pdf.output(os.path.join(OUTPUT_DIR, "invoice_1019.pdf"))
    print("  Created invoice_1019.pdf")


def create_mixed_currency_invoice():
    """INV-1020: Mixed languages, unusual date formats, currency symbols (EUR, GBP, USD)."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 10)
    # Use EUR/GBP/$ to avoid Unicode font issues with default Helvetica
    lines = [
        "  FACTURE / INVOICE / RECHNUNG",
        "",
        "  Invoice No: INV-1020",
        "  Vendor: EuroWidget GmbH (Germany)",
        "  Date: 30.01.2026  (DD.MM.YYYY)",
        "  Due: 28.02.2026",
        "",
        "  Item            Qty    Unit Price    Amount",
        "  ----            ---    ----------    ------",
        "  WidgetA          4     EUR 250.00    EUR 1,000.00",
        "  WidgetB          2     GBP 500.00   GBP 1,000.00",
        "  GadgetX          1     $750.00      $750.00",
        "",
        "  Subtotal:  EUR 1,000 + GBP 1,000 + $750  (mixed currencies)",
        "  Tax (VAT 19%):  EUR 190.00",
        "  Total:  EUR 2,190.00  (primary currency)",
        "",
        "  Zahlungstermin: 30 Tage netto",
        "  Payment terms: Net 30",
        "  Reference: PO-20260130",
    ]
    for line in lines:
        pdf.cell(0, 6, line, ln=True)
    pdf.output(os.path.join(OUTPUT_DIR, "invoice_1020.pdf"))
    print("  Created invoice_1020.pdf")


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("Generating PDF invoices...")
    create_clean_invoice()
    create_messy_invoice()
    create_bulk_invoice()
    create_ocr_degraded_invoice()
    create_multipage_watermark_invoice()
    create_prose_invoice()
    create_mixed_currency_invoice()
    print("Done.")
