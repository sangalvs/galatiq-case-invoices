"""FastAPI REST API exposing the invoice pipeline.

Endpoints:
- POST /api/process-single   – run pipeline on one invoice (upload or sample path)
- POST /api/process-batch    – run pipeline on all files in DATA_DIR
- POST /api/process-inbox    – process simulated email inbox
- GET  /api/analytics        – aggregated analytics from processed_invoices
- GET  /api/samples          – list sample invoice files
- GET  /api/health           – simple health check

Run with:
    uvicorn api:app --reload
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from setup_db import init_db
from src.agents.graph import run_pipeline
from src.config import DATA_DIR
from src.email_ingestion import INBOX_DIR, process_inbox, read_inbox
from src.tools.db import get_batch_analytics

app = FastAPI(title="InvoiceIQ API", version="1.0.0")

# Allow local frontend (Vite default ports, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event() -> None:
    # Ensure DB and schema are ready
    init_db()


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"status": "ok"}


@app.get("/api/samples")
def list_samples() -> Dict[str, Any]:
    root = Path(DATA_DIR)
    files: List[Dict[str, Any]] = []
    for f in sorted(root.iterdir()):
        if f.is_file() and f.suffix.lower() in {".txt", ".json", ".csv", ".xml", ".pdf"}:
            files.append(
                {
                    "name": f.name,
                    "path": str(f),
                    "size_bytes": f.stat().st_size,
                    "ext": f.suffix.lower(),
                }
            )
    return {"samples": files}


def _run_pipeline_on_temp_file(upload: UploadFile) -> Dict[str, Any]:
    suffix = Path(upload.filename or "").suffix or ".bin"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        import os
        os.write(tmp_fd, upload.file.read())
        os.close(tmp_fd)
        return run_pipeline(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.post("/api/process-single")
async def process_single(
    file: Optional[UploadFile] = File(default=None),
    sample_path: Optional[str] = Form(default=None),
) -> JSONResponse:
    """
    Run the pipeline on a single invoice.

    - If `file` is provided, it is processed.
    - Else if `sample_path` is provided, that path is processed.
    """
    if file is None and not sample_path:
        return JSONResponse(
            status_code=400,
            content={"error": "Provide either an uploaded file or a sample_path."},
        )

    if file is not None:
        result = await asyncio.to_thread(_run_pipeline_on_temp_file, file)
    else:
        path = Path(sample_path)
        if not path.exists():
            return JSONResponse(status_code=404, content={"error": f"File not found: {sample_path}"})
        result = await asyncio.to_thread(run_pipeline, str(path))

    return JSONResponse(content=result)


@app.post("/api/process-batch")
async def process_batch(directory: Optional[str] = Form(default=None)) -> Dict[str, Any]:
    """
    Run the pipeline on all invoices in a directory (default: DATA_DIR).
    Returns per-invoice results and a small summary.
    """
    root = Path(directory) if directory else Path(DATA_DIR)
    if not root.is_dir():
        raise HTTPException(status_code=400, detail=f"{root} is not a directory")

    files = sorted(
        f for f in root.iterdir() if f.suffix.lower() in {".txt", ".json", ".csv", ".xml", ".pdf"}
    )

    def _run_batch() -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for f in files:
            try:
                results.append(run_pipeline(str(f)))
            except Exception as e:
                results.append({"file": str(f), "error": str(e)})
        return results

    results = await asyncio.to_thread(_run_batch)
    return {"results": results, "summary": {"total": len(results)}}


@app.get("/api/analytics")
def analytics() -> Dict[str, Any]:
    """
    Return aggregated analytics from the processed_invoices table.
    """
    return get_batch_analytics()


@app.get("/api/inbox/messages")
def inbox_messages() -> Dict[str, Any]:
    """
    List emails in the simulated inbox (metadata only).
    """
    messages = read_inbox()
    data = [
        {
            "message_id": m.message_id,
            "subject": m.subject,
            "sender": m.sender,
            "date": m.date,
            "has_attachments": bool(m.attachments),
            "eml_path": m.eml_path,
        }
        for m in messages
    ]
    return {"count": len(data), "messages": data, "inbox_dir": str(INBOX_DIR)}


@app.post("/api/inbox/process")
async def inbox_process() -> Dict[str, Any]:
    """
    Process all emails in the simulated inbox via the pipeline.
    """
    results = await asyncio.to_thread(process_inbox)
    return {"count": len(results), "results": results}

