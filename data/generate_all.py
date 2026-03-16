"""
Run all invoice generators: PDFs, messy JSON, messy CSV.

Requires: pip install fpdf2 (or use: pip install -r requirements.txt)

Usage: python data/generate_all.py
"""

import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "invoices")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    scripts = [
        ("generate_pdfs.py", "PDF invoices (1011-1020)"),
        ("generate_messy_json.py", "Messy JSON (1021)"),
        ("generate_messy_csv.py", "Messy CSV (1022)"),
    ]
    for script, desc in scripts:
        path = os.path.join(SCRIPT_DIR, script)
        print(f"\nRunning {script} ({desc})...")
        result = subprocess.run([sys.executable, path], cwd=SCRIPT_DIR)
        if result.returncode != 0:
            print(f"  WARNING: {script} exited with code {result.returncode}")
    print("\nDone. Output in:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
