"""CLI entry point for the invoice processing pipeline."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from setup_db import init_db


def _truncate(text: str, max_len: int, suffix: str = "...") -> str:
    """Truncate at word boundary when possible, add suffix if cut."""
    if not text or len(text) <= max_len:
        return text
    cut = text[: max_len + 1]
    last_space = cut.rfind(" ")
    if last_space > max_len // 2:
        return cut[:last_space].rstrip() + suffix
    return text[:max_len].rstrip() + suffix


def format_result(result: dict, verbose: bool = False) -> str:
    lines = []
    invoice = result.get("invoice", {})
    validation = result.get("validation_result", {})
    fraud = result.get("fraud_result", {})
    approval = result.get("approval_result", {})
    payment = result.get("payment_result", {})

    lines.append("=" * 70)
    lines.append(f"  INVOICE: {invoice.get('invoice_number', 'UNKNOWN')}")
    lines.append(f"  Vendor:  {invoice.get('vendor', 'N/A')}")
    lines.append(f"  Total:   ${invoice.get('total', 0):,.2f} {invoice.get('currency', 'USD')}")
    lines.append(f"  Items:   {len(invoice.get('line_items', []))}")
    if result.get("duplicate_of"):
        dup = result["duplicate_of"]
        processed_at = (dup.get("processed_at") or "?")[:19].replace("T", " ")
        lines.append(f"  [DUPLICATE] Already processed on {processed_at} — this run for audit only")
    lines.append("=" * 70)

    lines.append("\n--- INGESTION ---")
    for item in invoice.get("line_items", []):
        lines.append(f"  {item['item']}: qty={item['quantity']} @ ${item['unit_price']:.2f}")

    lines.append("\n--- VALIDATION ---")
    val_status = "PASSED" if validation.get("passed") else "FAILED"
    lines.append(f"  Status: {val_status}")
    lines.append(f"  Summary: {validation.get('summary', 'N/A')}")
    for flag in validation.get("item_flags", []):
        lines.append(f"  [{flag['severity'].upper()}] {flag['item']}: {flag['detail']}")
    for af in validation.get("arithmetic_flags", []):
        lines.append(f"  [ARITHMETIC] {af['detail']}")

    lines.append("\n--- FRAUD DETECTION ---")
    risk_level = fraud.get("risk_level", "unknown")
    risk_score = fraud.get("risk_score", 0)
    lines.append(f"  Risk Level: {risk_level.upper()} ({risk_score}/100)")
    lines.append(f"  Recommendation: {fraud.get('recommendation', 'N/A')}")
    for sig in fraud.get("signals", []):
        if sig.get("score", 0) > 0:
            lines.append(f"  [{sig['category']}] score={sig['score']}/10: {_truncate(sig['description'], 120)}")

    lines.append("\n--- APPROVAL ---")
    decision = approval.get("decision", "N/A")
    lines.append(f"  Decision: {decision.upper()}")
    lines.append(f"  Reasoning: {_truncate(approval.get('reasoning', 'N/A'), 400)}")
    if approval.get("critique"):
        lines.append(f"  Critique: {_truncate(approval['critique'], 400)}")

    lines.append("\n--- PAYMENT ---")
    pay_status = payment.get("status", "N/A")
    lines.append(f"  Status: {pay_status.upper()}")
    lines.append(f"  Detail: {payment.get('detail', 'N/A')}")

    if verbose:
        lines.append("\n--- PROCESSING LOG ---")
        for entry in result.get("processing_log", []):
            lines.append(f"  [{entry['stage']}] {entry['action']}: {entry['result']} - {_truncate(entry.get('details', ''), 200)}")

    lines.append("")
    return "\n".join(lines)


def process_single(file_path: str, verbose: bool = False) -> dict:
    from src.agents.graph import run_pipeline

    start = time.time()
    result = run_pipeline(file_path)
    elapsed_ms = int((time.time() - start) * 1000)

    print(format_result(result, verbose))
    print(f"  Processing time: {elapsed_ms}ms\n")
    return result


def process_batch(directory: str, verbose: bool = False) -> list:
    dir_path = Path(directory)
    if not dir_path.is_dir():
        print(f"Error: {directory} is not a directory")
        sys.exit(1)

    extensions = {".txt", ".json", ".csv", ".xml", ".pdf"}
    files = sorted(f for f in dir_path.iterdir() if f.suffix.lower() in extensions)

    if not files:
        print(f"No invoice files found in {directory}")
        sys.exit(1)

    print(f"Processing {len(files)} invoice(s) from {directory}\n")

    from src.agents.graph import run_pipeline

    results = []
    summary = {"approved": 0, "rejected": 0, "flagged": 0, "errors": 0}

    for file in files:
        try:
            start = time.time()
            result = run_pipeline(str(file))
            elapsed_ms = int((time.time() - start) * 1000)

            print(format_result(result, verbose))

            status = result.get("payment_result", {}).get("status", "error")
            if status == "paid":
                summary["approved"] += 1
            elif status == "rejected":
                decision = result.get("approval_result", {}).get("decision", "rejected")
                if decision == "flagged":
                    summary["flagged"] += 1
                else:
                    summary["rejected"] += 1
            else:
                summary["errors"] += 1

            results.append(result)
        except Exception as e:
            print(f"ERROR processing {file}: {e}")
            summary["errors"] += 1

    print("\n" + "=" * 70)
    print("  BATCH SUMMARY")
    print("=" * 70)
    print(f"  Total processed: {len(results)}")
    print(f"  Approved:  {summary['approved']}")
    print(f"  Rejected:  {summary['rejected']}")
    print(f"  Flagged:   {summary['flagged']}")
    print(f"  Errors:    {summary['errors']}")
    print("=" * 70)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Invoice Processing Pipeline - Multi-Agent System"
    )
    parser.add_argument(
        "--invoice_path",
        type=str,
        required=True,
        help="Path to an invoice file or directory of invoices",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed processing log",
    )
    args = parser.parse_args()

    init_db()

    path = Path(args.invoice_path)
    if path.is_dir():
        process_batch(str(path), args.verbose)
    elif path.is_file():
        process_single(str(path), args.verbose)
    else:
        print(f"Error: {args.invoice_path} not found")
        sys.exit(1)


if __name__ == "__main__":
    main()
