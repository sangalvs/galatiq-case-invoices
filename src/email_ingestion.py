"""Simulated email inbox ingestion.

Reads .eml files from data/inbox/, extracts invoice attachments,
and feeds them into the processing pipeline.

Production extension: swap _read_inbox_local() for _read_inbox_imap()
to connect to a real Gmail/IMAP account using app passwords.
"""

from __future__ import annotations

import email
import email.policy
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from email import message_from_bytes
from pathlib import Path
from typing import Dict, List, Optional, Tuple

INBOX_DIR = Path(__file__).parent.parent / "data" / "inbox"
VALID_ATTACHMENT_EXTENSIONS = {".pdf", ".txt", ".json", ".csv", ".xml"}


@dataclass
class EmailMessage:
    message_id: str
    subject: str
    sender: str
    date: str
    body: str
    attachments: List[Tuple[str, bytes]]  # (filename, content)
    eml_path: str


def read_inbox(inbox_dir: Optional[Path] = None) -> List[EmailMessage]:
    """Read all .eml files from the local inbox directory."""
    dir_path = inbox_dir or INBOX_DIR
    if not dir_path.exists():
        return []

    messages = []
    for eml_file in sorted(dir_path.glob("*.eml")):
        msg = _parse_eml(eml_file)
        if msg:
            messages.append(msg)

    return messages


def _parse_eml(eml_path: Path) -> Optional[EmailMessage]:
    """Parse a single .eml file into an EmailMessage."""
    try:
        raw = eml_path.read_bytes()
        msg = message_from_bytes(raw, policy=email.policy.default)

        subject = str(msg.get("Subject", "(no subject)"))
        sender = str(msg.get("From", "unknown"))
        date = str(msg.get("Date", ""))
        message_id = str(msg.get("Message-ID", eml_path.stem))

        body = ""
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in disposition:
                    filename = part.get_filename() or "attachment"
                    payload = part.get_payload(decode=True)
                    if payload:
                        attachments.append((filename, payload))
                elif content_type == "text/plain" and not body:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="replace")

        return EmailMessage(
            message_id=message_id,
            subject=subject,
            sender=sender,
            date=date,
            body=body,
            attachments=attachments,
            eml_path=str(eml_path),
        )
    except Exception as e:
        print(f"Warning: could not parse {eml_path}: {e}")
        return None


def extract_invoice_attachments(msg: EmailMessage) -> List[str]:
    """Extract invoice attachments to a temp directory. Returns list of file paths."""
    paths = []

    for filename, content in msg.attachments:
        ext = Path(filename).suffix.lower()
        if ext in VALID_ATTACHMENT_EXTENSIONS:
            tmp_dir = Path(tempfile.mkdtemp())
            dest = tmp_dir / filename
            dest.write_bytes(content)
            paths.append(str(dest))

    if not paths and msg.body.strip():
        subject_lower = msg.subject.lower()
        if any(kw in subject_lower for kw in ["invoice", "billing", "payment", "inv-", "inv "]):
            tmp_dir = Path(tempfile.mkdtemp())
            dest = tmp_dir / f"{msg.message_id.strip('<>').replace('@', '_')}.txt"
            dest.write_text(msg.body)
            paths.append(str(dest))

    return paths


def process_inbox(inbox_dir: Optional[Path] = None) -> List[Dict]:
    """Process all emails in the inbox through the pipeline. Returns list of results."""
    from src.agents.graph import run_pipeline

    messages = read_inbox(inbox_dir)
    results = []

    for msg in messages:
        invoice_files = extract_invoice_attachments(msg)
        for file_path in invoice_files:
            try:
                result = run_pipeline(file_path)
                result["_email_subject"] = msg.subject
                result["_email_sender"] = msg.sender
                result["_email_date"] = msg.date
                result["_source_file"] = Path(file_path).name
                results.append(result)
            finally:
                shutil.rmtree(Path(file_path).parent, ignore_errors=True)

    return results


# ---------------------------------------------------------------------------
# Production IMAP extension (documented, not wired up)
# ---------------------------------------------------------------------------
def _read_inbox_imap(
    host: str,
    username: str,
    password: str,
    folder: str = "INBOX",
    subject_filter: str = "invoice",
) -> List[EmailMessage]:
    """
    Production-ready IMAP reader. Uses stdlib imaplib — no extra dependencies.

    Usage:
        messages = _read_inbox_imap(
            host="imap.gmail.com",
            username="accounts@acmecorp.com",
            password="<app-password>",   # Gmail → Settings → App passwords
            subject_filter="invoice",
        )

    To enable in production:
    1. Set IMAP_HOST, IMAP_USER, IMAP_PASS in .env
    2. Replace read_inbox() to call this function
    3. The rest of the pipeline is unchanged
    """
    import imaplib

    messages = []
    with imaplib.IMAP4_SSL(host) as imap:
        imap.login(username, password)
        imap.select(folder)

        _, uids = imap.search(None, f'SUBJECT "{subject_filter}"')
        for uid in uids[0].split():
            _, data = imap.fetch(uid, "(RFC822)")
            for part in data:
                if isinstance(part, tuple):
                    raw = part[1]
                    msg = message_from_bytes(raw, policy=email.policy.default)
                    parsed = EmailMessage(
                        message_id=str(msg.get("Message-ID", uid.decode())),
                        subject=str(msg.get("Subject", "")),
                        sender=str(msg.get("From", "")),
                        date=str(msg.get("Date", "")),
                        body="",
                        attachments=[],
                        eml_path="",
                    )

                    if msg.is_multipart():
                        for p in msg.walk():
                            disp = str(p.get("Content-Disposition", ""))
                            if "attachment" in disp:
                                fname = p.get_filename() or "attachment"
                                payload = p.get_payload(decode=True)
                                if payload:
                                    parsed.attachments.append((fname, payload))
                            elif p.get_content_type() == "text/plain" and not parsed.body:
                                pl = p.get_payload(decode=True)
                                if pl:
                                    parsed.body = pl.decode("utf-8", errors="replace")
                    else:
                        pl = msg.get_payload(decode=True)
                        if pl:
                            parsed.body = pl.decode("utf-8", errors="replace")

                    messages.append(parsed)

    return messages
