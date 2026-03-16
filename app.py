"""Streamlit dashboard for the invoice processing pipeline."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from setup_db import init_db
from src.agents.graph import run_pipeline
from src.config import DATA_DIR, USE_MOCK_LLM
from src.email_ingestion import INBOX_DIR, process_inbox, read_inbox
from src.tools.db import get_batch_analytics

st.set_page_config(page_title="InvoiceIQ — AI Processing Pipeline", page_icon="🧾", layout="wide")
init_db()

VALID_EXTENSIONS = {".txt", ".json", ".csv", ".xml", ".pdf"}
PIPELINE_STAGES = [
    ("📥", "Ingestion"),
    ("✅", "Validation"),
    ("🔍", "Fraud"),
    ("⚖️", "Approval"),
    ("💳", "Payment"),
]


def render_header():
    st.title("🧾 InvoiceIQ")
    st.markdown("Multi-agent pipeline: **Ingestion** → **Validation** → **Fraud** → **Approval** → **Payment**")
    if USE_MOCK_LLM:
        st.caption("LLM: Mock mode (no API key)")


def render_sidebar():
    st.sidebar.header("Process Invoices")
    mode = st.sidebar.radio("Mode", ["Single Invoice", "Batch Processing", "Email Inbox", "Analytics"])
    file_path = None
    is_temp = False

    if mode == "Single Invoice":
        source = st.sidebar.radio("Source", ["Sample invoices", "Upload file"])
        if source == "Sample invoices":
            files = sorted(f for f in DATA_DIR.iterdir() if f.suffix.lower() in VALID_EXTENSIONS)
            selected = st.sidebar.selectbox("Invoice", files, format_func=lambda f: f.name)
            file_path = str(selected) if selected else None
        else:
            uploaded = st.sidebar.file_uploader("Upload", type=["txt", "json", "csv", "xml", "pdf"])
            if uploaded:
                import tempfile, os
                suffix = Path(uploaded.name).suffix or ".bin"
                tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
                try:
                    os.write(tmp_fd, uploaded.getvalue())
                finally:
                    os.close(tmp_fd)
                file_path = tmp_path
                is_temp = True

    return mode, file_path, is_temp


def render_invoice_details(invoice: dict):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Invoice #", invoice.get("invoice_number", "N/A"))
    with col2:
        st.metric("Vendor", invoice.get("vendor", "N/A"))
    with col3:
        total = invoice.get("total", 0) or 0
        currency = invoice.get("currency", "USD")
        st.metric("Total", f"${total:,.2f} {currency}")
    if invoice.get("line_items"):
        st.subheader("Line Items")
        rows = [f"| {i.get('item', '?')} | {i.get('quantity', '?')} | ${i.get('unit_price', 0):,.2f} |" for i in invoice["line_items"]]
        st.markdown("| Item | Qty | Unit Price |\n|------|-----|------------|\n" + "\n".join(rows))


def render_single_result(result: dict):
    invoice = result.get("invoice", {})
    validation = result.get("validation_result", {})
    fraud = result.get("fraud_result", {})
    approval = result.get("approval_result", {})
    payment = result.get("payment_result", {})

    if result.get("duplicate_of"):
        dup = result["duplicate_of"]
        processed_at = (dup.get("processed_at") or "?")[:19].replace("T", " ")
        st.info(f"**Already processed** on {processed_at}. This run is for audit only.")

    render_invoice_details(invoice)
    st.divider()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Validation", "Fraud", "Approval", "Payment", "Log"])
    with tab1:
        passed = validation.get("passed", False)
        st.markdown(f"**Status:** {'PASSED' if passed else 'FAILED'}")
        st.markdown(f"**Summary:** {validation.get('summary', 'N/A')}")
        for flag in validation.get("item_flags", []):
            st.markdown(f"- **{flag['item']}**: {flag['detail']}")
        for af in validation.get("arithmetic_flags", []):
            st.markdown(f"- **{af['field']}**: {af['detail']}")
    with tab2:
        st.metric("Risk Score", f"{fraud.get('risk_score', 0)}/100")
        st.markdown(f"**Level:** {(fraud.get('risk_level') or '?').upper()}")
        st.markdown(f"**Recommendation:** {fraud.get('recommendation', 'N/A')}")
        for sig in fraud.get("signals", []):
            if sig.get("score", 0) > 0:
                st.markdown(f"- **{sig['category']}** ({sig['score']}/10): {sig.get('description', '')[:100]}")
    with tab3:
        decision = approval.get("decision", "N/A")
        st.markdown(f"### Decision: **{decision.upper()}**")
        st.markdown(f"**Reasoning:** {approval.get('reasoning', 'N/A')}")
        if approval.get("critique"):
            with st.expander("VP Critique"):
                st.markdown(approval["critique"])
    with tab4:
        status = payment.get("status", "N/A")
        st.markdown(f"**Status:** {status.upper()}")
        st.markdown(f"**Detail:** {payment.get('detail', 'N/A')}")
    with tab5:
        for entry in result.get("processing_log", []):
            icon = {"success": "✅", "info": "ℹ️", "warning": "⚠️", "error": "❌"}.get(entry.get("result", ""), "📝")
            st.markdown(f"{icon} `[{entry.get('stage')}]` **{entry.get('action')}**: {entry.get('details', '')[:120]}")


def render_batch_analytics(results: list):
    if not results:
        st.info("No invoices processed yet.")
        return
    total = len(results)
    approved = sum(1 for r in results if r.get("approval_result", {}).get("decision") == "approved")
    rejected = sum(1 for r in results if r.get("approval_result", {}).get("decision") == "rejected")
    flagged = sum(1 for r in results if r.get("approval_result", {}).get("decision") == "flagged")
    total_value = sum(r.get("invoice", {}).get("total") or 0 for r in results)

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total", total)
    with col2:
        st.metric("Approved", approved)
    with col3:
        st.metric("Rejected", rejected)
    with col4:
        st.metric("Flagged", flagged)
    with col5:
        st.metric("Total Value", f"${total_value:,.2f}")

    import plotly.express as px
    status_data = [
        {
            "Invoice": r.get("invoice", {}).get("invoice_number", "?"),
            "Vendor": (r.get("invoice", {}).get("vendor") or "?")[:20],
            "Total": r.get("invoice", {}).get("total") or 0,
            "Decision": r.get("approval_result", {}).get("decision", "?"),
            "Fraud Risk": r.get("fraud_result", {}).get("risk_level", "?"),
            "Fraud Score": r.get("fraud_result", {}).get("risk_score", 0),
        }
        for r in results
    ]
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Decision Distribution")
        fig = px.pie(
            names=["Approved", "Rejected", "Flagged"],
            values=[approved, rejected, flagged],
            color_discrete_sequence=["#2ecc71", "#e74c3c", "#f39c12"],
        )
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.subheader("Fraud Risk Scores")
        fig2 = px.bar(status_data, x="Invoice", y="Fraud Score", color="Fraud Risk")
        st.plotly_chart(fig2, use_container_width=True)
    st.subheader("All Invoices")
    if status_data:
        cols = list(status_data[0].keys())
        header = "| " + " | ".join(cols) + " |"
        sep = "|" + "|".join(["---"] * len(cols)) + "|"
        rows = ["| " + " | ".join(str(d.get(c, "")) for c in cols) + " |" for d in status_data]
        st.markdown(header + "\n" + sep + "\n" + "\n".join(rows))


def render_email_inbox():
    st.subheader("📬 Email Inbox")
    st.markdown(f"Reads `.eml` files from `{INBOX_DIR}`. Extracts attachments and runs the pipeline.")
    messages = read_inbox()
    if not messages:
        st.warning(f"No .eml files in `{INBOX_DIR}`. Add sample emails.")
        return
    st.markdown(f"**{len(messages)} email(s) in inbox**")
    for msg in messages:
        st.markdown(f"- **{msg.subject}** — {msg.sender} ({len(msg.attachments)} attachment(s))")
    if st.button("Process All Inbox Emails", type="primary"):
        with st.spinner("Processing..."):
            results = process_inbox()
        if results:
            st.success(f"Processed {len(results)} invoice(s)")
            for r in results:
                with st.expander(f"📧 {r.get('_email_subject', '?')} — {r.get('invoice', {}).get('invoice_number', '?')}"):
                    render_single_result(r)
        else:
            st.warning("No invoices extracted from inbox.")


def render_historical_analytics():
    analytics = get_batch_analytics()
    if analytics.get("total", 0) == 0:
        st.info("No invoices processed yet. Run Batch or Email Inbox first.")
        return
    st.subheader("Historical Summary")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Processed", analytics["total"])
    with col2:
        st.metric("Approved", analytics["approved"])
    with col3:
        st.metric("Rejected", analytics["rejected"])
    with col4:
        st.metric("Total Value", f"${analytics['total_value_usd']:,.2f}")
    if analytics.get("invoices"):
        history = [
            {
                "Invoice #": i.get("invoice_number", "?"),
                "Vendor": (i.get("vendor") or "?")[:24],
                "Amount": f"${i.get('total_amount', 0):,.2f}",
                "Status": i.get("status", "?"),
                "Fraud Risk": i.get("fraud_risk_level", "?"),
            }
            for i in analytics["invoices"]
        ]
        if history:
            cols = list(history[0].keys())
            header = "| " + " | ".join(cols) + " |"
            sep = "|" + "|".join(["---"] * len(cols)) + "|"
            rows = ["| " + " | ".join(str(h.get(c, "")) for c in cols) + " |" for h in history]
            st.markdown(header + "\n" + sep + "\n" + "\n".join(rows))
        else:
            st.markdown("_No history._")


def main():
    render_header()
    mode, file_path, is_temp = render_sidebar()

    if mode == "Single Invoice":
        if file_path and st.sidebar.button("Process Invoice", type="primary"):
            with st.spinner("Running pipeline..."):
                start = time.time()
                try:
                    result = run_pipeline(file_path)
                finally:
                    if is_temp:
                        Path(file_path).unlink(missing_ok=True)
                elapsed = time.time() - start
            st.success(f"Done in {elapsed:.1f}s")
            render_single_result(result)
        elif not file_path:
            st.info("Select or upload an invoice.")

    elif mode == "Batch Processing":
        if st.sidebar.button("Process All Invoices", type="primary"):
            files = sorted(f for f in DATA_DIR.iterdir() if f.suffix.lower() in VALID_EXTENSIONS)
            if not files:
                st.warning("No invoice files found in the data directory.")
            else:
                results = []
                progress = st.progress(0, text="Processing...")
                for i, f in enumerate(files):
                    progress.progress((i + 1) / len(files), text=f"Processing {f.name}...")
                    try:
                        results.append(run_pipeline(str(f)))
                    except Exception as e:
                        st.error(f"Error on {f.name}: {e}")
                progress.empty()
                st.success(f"Processed {len(results)} invoices")
                render_batch_analytics(results)

    elif mode == "Email Inbox":
        render_email_inbox()

    else:
        render_historical_analytics()


if __name__ == "__main__":
    main()
