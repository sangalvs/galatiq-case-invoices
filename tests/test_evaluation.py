"""Evaluation harness: ground-truth expected outcomes for all invoices."""

from __future__ import annotations

from pathlib import Path

import pytest

from setup_db import init_db
from src.agents.graph import run_pipeline

DATA_DIR = Path(__file__).parent.parent / "data" / "invoices"

GROUND_TRUTH = {
    "invoice_1001.txt": {
        "invoice_number": "INV-1001",
        "expected_validation": "pass",
        "expected_fraud_max": "low",
        "expected_decision": "approved",
    },
    "invoice_1002.txt": {
        "invoice_number": "INV-1002",
        "expected_validation": "fail",
        "expected_fraud_max": "low",
        "expected_decision": "rejected",
        "expected_flags": ["stock_exceeded"],
    },
    "invoice_1003.txt": {
        "invoice_number": "INV-1003",
        "expected_validation": "fail",
        "expected_fraud_max": "critical",
        "expected_decision": "rejected",
        "expected_flags": ["zero_stock"],
    },
    "invoice_1004.json": {
        "invoice_number": "INV-1004",
        "expected_validation": "pass",
        "expected_fraud_max": "low",
        "expected_decision": "approved",
    },
    "invoice_1005.json": {
        "invoice_number": "INV-1005",
        "expected_validation": "fail",
        "expected_fraud_max": "low",
        "expected_decision": "rejected",
        "expected_flags": ["stock_exceeded"],
    },
    "invoice_1006.csv": {
        "invoice_number": "INV-1006",
        "expected_validation": "pass",
        "expected_fraud_max": "low",
        "expected_decision": "approved",
    },
    "invoice_1007.csv": {
        "invoice_number": "INV-1007",
        "expected_validation": "fail",
        "expected_fraud_max": "low",
        "expected_decision": "rejected",
        "expected_flags": ["stock_exceeded"],
    },
    "invoice_1008.txt": {
        "invoice_number": "INV-1008",
        "expected_validation": "fail",
        "expected_fraud_max": "medium",
        "expected_decision": "rejected",
        "expected_flags": ["unknown_item"],
    },
    "invoice_1009.json": {
        "invoice_number": "INV-1009",
        "expected_validation": "fail",
        "expected_fraud_max": "critical",
        "expected_decision": "rejected",
        "expected_flags": ["negative_qty"],
    },
    "invoice_1010.txt": {
        "invoice_number": "INV-1010",
        "expected_validation": "pass",
        "expected_fraud_max": "low",
        "expected_decision": "approved",
    },
    "invoice_1011.txt": {
        "invoice_number": "INV-1011",
        "expected_validation": "pass",
        "expected_fraud_max": "low",
        "expected_decision": "approved",
    },
    "invoice_1012.txt": {
        "invoice_number": "INV-1012",
        "expected_validation": "pass",
        "expected_fraud_max": "low",
        "expected_decision": "approved",
    },
    "invoice_1013.json": {
        "invoice_number": "INV-1013",
        "expected_validation": "fail",
        "expected_fraud_max": "low",
        "expected_decision": "rejected",
        "expected_flags": ["stock_exceeded"],
    },
    "invoice_1014.xml": {
        "invoice_number": "INV-1014",
        "expected_validation": "pass",
        "expected_fraud_max": "low",
        "expected_decision": "approved",
    },
    "invoice_1015.csv": {
        "invoice_number": "INV-1015",
        "expected_validation": "pass",
        "expected_fraud_max": "low",
        "expected_decision": "approved",
    },
    "invoice_1016.json": {
        "invoice_number": "INV-1016",
        "expected_validation": "fail",
        "expected_fraud_max": "low",
        "expected_decision": "rejected",
        "expected_flags": ["unknown_item"],
    },
}

RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()


@pytest.fixture(scope="module")
def all_results():
    """Run all invoices once, reuse results across tests."""
    results = {}
    for filename in GROUND_TRUTH:
        path = DATA_DIR / filename
        if path.exists():
            results[filename] = run_pipeline(str(path))
    return results


class TestExtractionAccuracy:
    def test_invoice_numbers_extracted(self, all_results):
        correct = 0
        total = 0
        for filename, truth in GROUND_TRUTH.items():
            if filename not in all_results:
                continue
            total += 1
            result = all_results[filename]
            inv_num = result.get("invoice", {}).get("invoice_number", "")
            expected = truth["invoice_number"]
            if expected in inv_num or inv_num == expected:
                correct += 1
            else:
                print(f"  MISS: {filename}: expected={expected}, got={inv_num}")

        accuracy = correct / total if total > 0 else 0
        print(f"\nExtraction Accuracy: {correct}/{total} ({accuracy:.0%})")
        assert accuracy >= 0.8, f"Extraction accuracy {accuracy:.0%} below 80% threshold"


class TestValidationAccuracy:
    def test_validation_decisions(self, all_results):
        correct = 0
        total = 0
        for filename, truth in GROUND_TRUTH.items():
            if filename not in all_results:
                continue
            total += 1
            result = all_results[filename]
            val_passed = result.get("validation_result", {}).get("passed", False)
            expected_pass = truth["expected_validation"] == "pass"

            if val_passed == expected_pass:
                correct += 1
            else:
                print(f"  MISS: {filename}: expected={'pass' if expected_pass else 'fail'}, got={'pass' if val_passed else 'fail'}")

        accuracy = correct / total if total > 0 else 0
        print(f"\nValidation Accuracy: {correct}/{total} ({accuracy:.0%})")
        assert accuracy >= 0.8, f"Validation accuracy {accuracy:.0%} below 80% threshold"

    def test_expected_flags_present(self, all_results):
        correct = 0
        total = 0
        for filename, truth in GROUND_TRUTH.items():
            if filename not in all_results:
                continue
            expected_flags = truth.get("expected_flags", [])
            if not expected_flags:
                continue
            total += 1
            result = all_results[filename]
            actual_flags = [
                f.get("issue") for f in result.get("validation_result", {}).get("item_flags", [])
            ]
            if all(ef in actual_flags for ef in expected_flags):
                correct += 1
            else:
                print(f"  MISS: {filename}: expected_flags={expected_flags}, got={actual_flags}")

        accuracy = correct / total if total > 0 else 0
        print(f"\nFlag Detection Accuracy: {correct}/{total} ({accuracy:.0%})")
        assert accuracy >= 0.7, f"Flag detection accuracy {accuracy:.0%} below 70% threshold"


class TestFraudAccuracy:
    def test_fraud_risk_levels(self, all_results):
        correct = 0
        total = 0
        for filename, truth in GROUND_TRUTH.items():
            if filename not in all_results:
                continue
            total += 1
            result = all_results[filename]
            actual_level = result.get("fraud_result", {}).get("risk_level", "low")
            expected_max = truth["expected_fraud_max"]

            if RISK_ORDER.get(actual_level, 0) <= RISK_ORDER.get(expected_max, 0):
                correct += 1
            else:
                print(f"  MISS: {filename}: expected_max={expected_max}, got={actual_level}")

        accuracy = correct / total if total > 0 else 0
        print(f"\nFraud Detection Accuracy: {correct}/{total} ({accuracy:.0%})")
        assert accuracy >= 0.8, f"Fraud detection accuracy {accuracy:.0%} below 80% threshold"


class TestApprovalAccuracy:
    def test_approval_decisions(self, all_results):
        correct = 0
        total = 0
        for filename, truth in GROUND_TRUTH.items():
            if filename not in all_results:
                continue
            total += 1
            result = all_results[filename]
            actual = result.get("approval_result", {}).get("decision", "")
            expected = truth["expected_decision"]

            if actual == expected:
                correct += 1
            elif expected == "rejected" and actual in ("rejected", "flagged"):
                correct += 1
            else:
                print(f"  MISS: {filename}: expected={expected}, got={actual}")

        accuracy = correct / total if total > 0 else 0
        print(f"\nApproval Accuracy: {correct}/{total} ({accuracy:.0%})")
        assert accuracy >= 0.8, f"Approval accuracy {accuracy:.0%} below 80% threshold"


class TestOverallPipeline:
    def test_end_to_end_scorecard(self, all_results):
        """Generate the full scorecard."""
        metrics = {
            "extraction": {"correct": 0, "total": 0},
            "validation": {"correct": 0, "total": 0},
            "fraud": {"correct": 0, "total": 0},
            "approval": {"correct": 0, "total": 0},
            "overall": {"correct": 0, "total": 0},
        }

        for filename, truth in GROUND_TRUTH.items():
            if filename not in all_results:
                continue
            result = all_results[filename]
            inv = result.get("invoice", {})
            val = result.get("validation_result", {})
            fraud = result.get("fraud_result", {})
            approval = result.get("approval_result", {})

            all_correct = True

            # Extraction
            metrics["extraction"]["total"] += 1
            inv_num = inv.get("invoice_number", "")
            if truth["invoice_number"] in inv_num:
                metrics["extraction"]["correct"] += 1
            else:
                all_correct = False

            # Validation
            metrics["validation"]["total"] += 1
            val_passed = val.get("passed", False)
            expected_pass = truth["expected_validation"] == "pass"
            if val_passed == expected_pass:
                metrics["validation"]["correct"] += 1
            else:
                all_correct = False

            # Fraud
            metrics["fraud"]["total"] += 1
            actual_level = fraud.get("risk_level", "low")
            if RISK_ORDER.get(actual_level, 0) <= RISK_ORDER.get(truth["expected_fraud_max"], 0):
                metrics["fraud"]["correct"] += 1
            else:
                all_correct = False

            # Approval
            metrics["approval"]["total"] += 1
            actual_dec = approval.get("decision", "")
            expected_dec = truth["expected_decision"]
            if actual_dec == expected_dec or (expected_dec == "rejected" and actual_dec in ("rejected", "flagged")):
                metrics["approval"]["correct"] += 1
            else:
                all_correct = False

            # Overall
            metrics["overall"]["total"] += 1
            if all_correct:
                metrics["overall"]["correct"] += 1

        print("\n" + "=" * 50)
        print("  EVALUATION SCORECARD")
        print("=" * 50)
        for stage, m in metrics.items():
            pct = m["correct"] / m["total"] * 100 if m["total"] > 0 else 0
            print(f"  {stage:>12}: {m['correct']}/{m['total']} ({pct:.0f}%)")
        print("=" * 50)

        overall_pct = metrics["overall"]["correct"] / metrics["overall"]["total"] if metrics["overall"]["total"] > 0 else 0
        assert overall_pct >= 0.7, f"Overall accuracy {overall_pct:.0%} below 70% threshold"
