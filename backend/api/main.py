from __future__ import annotations

import csv
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.classifier.service import make_classifier
from backend.batch import BatchInputError, classify_rows, parse_tickets_csv
from backend.reporting.workbook import workbook_bytes
from backend.db import connection, init_db, record
from backend.evaluation.metrics import calculate
from backend.routing.engine import DEPARTMENTS, INTENTS, URGENCIES, decide

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "dataset" / "tickets.csv"
BALANCED_DATASET = ROOT / "dataset" / "tickets_balanced_50_50.csv"
GITHUB_DATASET = ROOT / "dataset" / "github_issues_100.csv"
classifier = make_classifier()
inference_lock = Lock()
batch_jobs_lock = Lock()
batch_jobs: dict[str, dict] = {}


def predict_one(ticket: dict) -> dict:
    with inference_lock:
        return classifier.predict(ticket)


def predict_batch(rows: list[dict]) -> list[dict]:
    with inference_lock:
        return classify_rows(rows, classifier)


def _update_batch_job(job_id: str, **changes) -> None:
    with batch_jobs_lock:
        batch_jobs[job_id].update(changes)


def _batch_job_snapshot(job_id: str) -> dict:
    with batch_jobs_lock:
        job = batch_jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Batch job not found")
        return {key: value for key, value in job.items() if key not in ("payload", "created_at")}


def _run_batch_job(job_id: str, rows: list[dict]) -> None:
    _update_batch_job(job_id, status="running")

    def progress(processed: int, total: int, item: dict) -> None:
        _update_batch_job(job_id, processed=processed, current_ticket=item["input"]["ticket_id"])

    try:
        with inference_lock:
            results = classify_rows(rows, classifier, progress)
        payload = workbook_bytes(results, "uploaded-tickets.csv")
        _update_batch_job(job_id, status="complete", processed=len(rows), current_ticket="", payload=payload)
    except Exception as exc:
        _update_batch_job(job_id, status="failed", error=str(exc), current_ticket="")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=180)
    body: str = Field(min_length=8, max_length=5000)
    customer_id: str | None = None
    customer_tier: str = "Standard"
    product: str = "LayaDesk"
    source_channel: str = "Web"
    previous_ticket_count: int = Field(default=0, ge=0)


class CorrectionIn(BaseModel):
    department: str
    intent: str
    urgency: str
    refund: bool
    churn: bool
    escalation: bool


def seed_samples():
    with connection() as db, DATASET.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            labels = {"department": row["department"], "intent": row["intent"], "urgency": row["urgency"],
                      "refund": row["refund"].lower() == "true", "churn": row["churn"].lower() == "true",
                      "escalation": row["escalation"].lower() == "true"}
            db.execute("""INSERT OR IGNORE INTO tickets
                (id, subject, body, customer_id, customer_tier, product, source_channel, previous_ticket_count,
                 created_at, status, sample_labels) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (row["ticket_id"], row["subject"], row["body"], row["customer_id"], row["customer_tier"],
                 row["product"], row["source_channel"], int(row["previous_ticket_count"]),
                 row["created_at"], "INCOMING", json.dumps(labels)))
            db.execute("""INSERT OR IGNORE INTO ground_truth
                (ticket_id, department, intent, urgency, refund, churn, escalation, origin, reviewed_at)
                VALUES (?,?,?,?,?,?,?,?,?)""", (row["ticket_id"], labels["department"], labels["intent"],
                labels["urgency"], int(labels["refund"]), int(labels["churn"]), int(labels["escalation"]),
                "synthetic_label", now()))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_samples()
    yield


app = FastAPI(title="LayaDesk", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")


def fetch_ticket(ticket_id: str):
    with connection() as db:
        row = db.execute("""SELECT t.*, p.department, p.department_confidence, p.intent, p.intent_confidence,
            p.urgency, p.urgency_confidence, p.frustration, p.frustration_confidence,
            p.refund_probability, p.churn_probability, p.escalation_probability, p.model, p.source,
            p.classified_at FROM tickets t LEFT JOIN predictions p ON p.ticket_id=t.id WHERE t.id=?""", (ticket_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Ticket not found")
    return record(row)


@app.get("/")
def index():
    return FileResponse(ROOT / "frontend" / "index.html")


@app.get("/api/health")
def health():
    mode = os.getenv("LAYADESK_MODE", "laya").lower()
    if mode == "demo":
        return {"status": "ok", "mode": "demo", "device": "simulation", "cuda_available": None}
    try:
        import torch
        available = torch.cuda.is_available()
    except ImportError:
        available = False
    return {"status": "ok" if available else "unavailable", "mode": "laya", "device": "cuda", "cuda_available": available}


@app.get("/api/tickets")
def list_tickets(status: str | None = None, q: str = "", limit: int = Query(default=100, ge=1, le=500)):
    query = """SELECT t.*, p.department, p.department_confidence, p.intent, p.intent_confidence,
        p.urgency, p.urgency_confidence, p.frustration, p.frustration_confidence,
        p.refund_probability, p.churn_probability, p.escalation_probability, p.model, p.source,
        p.classified_at FROM tickets t LEFT JOIN predictions p ON p.ticket_id=t.id WHERE 1=1"""
    params = []
    if status:
        query += " AND t.status=?"
        params.append(status)
    if q:
        query += " AND (t.subject LIKE ? OR t.body LIKE ? OR t.id LIKE ?)"
        params.extend([f"%{q}%"] * 3)
    query += " ORDER BY t.created_at DESC LIMIT ?"
    params.append(limit)
    with connection() as db:
        rows = db.execute(query, params).fetchall()
    return [record(r) for r in rows]


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    return fetch_ticket(ticket_id)


@app.post("/api/tickets", status_code=201)
def create_ticket(payload: TicketIn):
    ticket_id = "TCK-" + uuid4().hex[:8].upper()
    with connection() as db:
        db.execute("""INSERT INTO tickets (id, subject, body, customer_id, customer_tier, product,
            source_channel, previous_ticket_count, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (ticket_id, payload.subject, payload.body, payload.customer_id, payload.customer_tier,
             payload.product, payload.source_channel, payload.previous_ticket_count, now()))
    return fetch_ticket(ticket_id)


@app.post("/api/tickets/{ticket_id}/classify")
def classify_ticket(ticket_id: str):
    ticket = fetch_ticket(ticket_id)
    try:
        prediction = predict_one(ticket)
    except Exception as exc:
        raise HTTPException(503, f"Laya inference unavailable: {exc}") from exc
    route = decide(prediction, ticket["customer_tier"], ticket["subject"] + " " + ticket["body"])
    with connection() as db:
        db.execute("""INSERT INTO predictions (ticket_id, department, department_confidence, intent,
            intent_confidence, urgency, urgency_confidence, frustration, frustration_confidence,
            refund_probability, churn_probability, escalation_probability, model, source, classified_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ticket_id) DO UPDATE SET
            department=excluded.department, department_confidence=excluded.department_confidence,
            intent=excluded.intent, intent_confidence=excluded.intent_confidence,
            urgency=excluded.urgency, urgency_confidence=excluded.urgency_confidence,
            frustration=excluded.frustration, frustration_confidence=excluded.frustration_confidence,
            refund_probability=excluded.refund_probability, churn_probability=excluded.churn_probability,
            escalation_probability=excluded.escalation_probability, model=excluded.model,
            source=excluded.source, classified_at=excluded.classified_at""",
            (ticket_id, *[prediction[k] for k in ("department", "department_confidence", "intent", "intent_confidence",
                "urgency", "urgency_confidence", "frustration", "frustration_confidence", "refund_probability",
                "churn_probability", "escalation_probability", "model", "source")], now()))
        db.execute("UPDATE tickets SET status=?, queue=?, priority=?, gate=?, tags=? WHERE id=?",
                   (route["status"], route["queue"], route["priority"], route["gate"], json.dumps(route["tags"]), ticket_id))
    return fetch_ticket(ticket_id)


@app.post("/api/tickets/{ticket_id}/approve")
def approve_ticket(ticket_id: str):
    ticket = fetch_ticket(ticket_id)
    if not ticket["department"]:
        raise HTTPException(409, "Classify this ticket first")
    with connection() as db:
        db.execute("UPDATE tickets SET status='APPROVED', gate='human_approved', queue=? WHERE id=?",
                   (ticket["department"], ticket_id))
        db.execute("""INSERT INTO ground_truth (ticket_id, department, intent, urgency, refund, churn, escalation, origin, reviewed_at)
            VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(ticket_id) DO UPDATE SET department=excluded.department,
            intent=excluded.intent, urgency=excluded.urgency, refund=excluded.refund, churn=excluded.churn,
            escalation=excluded.escalation, origin=excluded.origin, reviewed_at=excluded.reviewed_at""",
            (ticket_id, ticket["department"], ticket["intent"], ticket["urgency"],
             int(ticket["refund_probability"] >= .80), int(ticket["churn_probability"] >= .80),
             int(ticket["escalation_probability"] >= .85), "human_approved", now()))
    return fetch_ticket(ticket_id)


@app.post("/api/tickets/{ticket_id}/correct")
def correct_ticket(ticket_id: str, payload: CorrectionIn):
    ticket = fetch_ticket(ticket_id)
    if not ticket["department"]:
        raise HTTPException(409, "Classify this ticket first")
    if payload.department not in DEPARTMENTS or payload.intent not in INTENTS or payload.urgency not in URGENCIES:
        raise HTTPException(422, "Invalid department, intent, or urgency")
    with connection() as db:
        db.execute("UPDATE tickets SET status='CORRECTED', gate='human_corrected', queue=?, priority=? WHERE id=?",
                   (payload.department, {"Critical":"P1","High":"P2","Medium":"P3","Low":"P4"}[payload.urgency], ticket_id))
        db.execute("""INSERT INTO ground_truth (ticket_id, department, intent, urgency, refund, churn, escalation, origin, reviewed_at)
            VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(ticket_id) DO UPDATE SET department=excluded.department,
            intent=excluded.intent, urgency=excluded.urgency, refund=excluded.refund, churn=excluded.churn,
            escalation=excluded.escalation, origin=excluded.origin, reviewed_at=excluded.reviewed_at""",
            (ticket_id, payload.department, payload.intent, payload.urgency,
             int(payload.refund), int(payload.churn), int(payload.escalation), "human_corrected", now()))
    return fetch_ticket(ticket_id)


@app.get("/api/analytics")
def analytics():
    with connection() as db:
        statuses = {r["status"]: r["n"] for r in db.execute("SELECT status, COUNT(*) n FROM tickets GROUP BY status")}
        departments = {r["department"]: r["n"] for r in db.execute("SELECT department, COUNT(*) n FROM predictions GROUP BY department")}
        total = db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        classified = db.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        avg = db.execute("SELECT AVG(department_confidence) FROM predictions").fetchone()[0]
    return {"total": total, "classified": classified, "statuses": statuses, "departments": departments,
            "average_confidence": round(avg or 0, 3)}


@app.get("/api/evaluation")
def evaluation():
    with connection() as db:
        rows = [dict(r) for r in db.execute("""SELECT t.status, t.priority, p.department pred_department,
            p.intent pred_intent, p.urgency pred_urgency, p.refund_probability, p.churn_probability,
            p.escalation_probability, p.department_confidence, p.source, g.department actual_department,
            g.intent actual_intent, g.urgency actual_urgency, g.refund actual_refund, g.churn actual_churn,
            g.escalation actual_escalation, g.origin FROM predictions p JOIN tickets t ON p.ticket_id=t.id
            JOIN ground_truth g ON g.ticket_id=t.id""")]
    return calculate(rows)


@app.get("/api/dataset.csv")
def download_dataset():
    return FileResponse(DATASET, media_type="text/csv", filename="layadesk-sample-tickets.csv")


@app.get("/api/dataset-balanced.csv")
def download_balanced_dataset():
    if not BALANCED_DATASET.is_file():
        raise HTTPException(404, "Balanced sample has not been generated yet")
    return FileResponse(BALANCED_DATASET, media_type="text/csv", filename="layadesk-balanced-50-50.csv")


@app.get("/api/dataset-github.csv")
def download_github_dataset():
    if not GITHUB_DATASET.is_file():
        raise HTTPException(404, "GitHub sample has not been generated yet")
    return FileResponse(GITHUB_DATASET, media_type="text/csv", filename="layadesk-github-issues-100.csv")


async def _read_batch_rows(request: Request) -> list[dict[str, str]]:
    if os.getenv("LAYADESK_MODE", "laya").lower() != "laya":
        raise HTTPException(409, "Batch Excel export requires Laya CUDA mode")
    try:
        import torch
        if not torch.cuda.is_available():
            raise HTTPException(503, "CUDA is unavailable")
    except ImportError as exc:
        raise HTTPException(503, "CUDA PyTorch is not installed") from exc
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 3_000_000:
            raise HTTPException(413, "CSV exceeds 3 MB")
    try:
        return parse_tickets_csv(bytes(content))
    except BatchInputError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/batches/jobs", status_code=202)
async def start_batch_job(request: Request):
    rows = await _read_batch_rows(request)
    job_id = uuid4().hex
    with batch_jobs_lock:
        expired = [key for key, job in batch_jobs.items()
                   if job["status"] in ("complete", "failed") and monotonic() - job["created_at"] > 3600]
        for key in expired:
            del batch_jobs[key]
        active = sum(job["status"] in ("pending", "running") for job in batch_jobs.values())
        if active >= 2:
            raise HTTPException(429, "Two batch jobs are already running; try again when one finishes")
        batch_jobs[job_id] = {"job_id": job_id, "status": "pending", "processed": 0,
                              "total": len(rows), "current_ticket": "", "error": None,
                              "payload": None, "created_at": monotonic()}
    Thread(target=_run_batch_job, args=(job_id, rows), daemon=True).start()
    return _batch_job_snapshot(job_id)


@app.get("/api/batches/jobs/{job_id}")
def get_batch_job(job_id: str):
    return _batch_job_snapshot(job_id)


@app.get("/api/batches/jobs/{job_id}/download")
def download_batch_job(job_id: str):
    with batch_jobs_lock:
        job = batch_jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Batch job not found")
        if job["status"] == "failed":
            raise HTTPException(503, job["error"] or "Batch job failed")
        if job["status"] != "complete":
            raise HTTPException(409, "Batch job is still processing")
        payload = job["payload"]
    return Response(payload, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="LayaDesk_Batch_Report.xlsx"'})


@app.post("/api/batches/classify")
async def classify_batch(request: Request):
    rows = await _read_batch_rows(request)
    try:
        results = await run_in_threadpool(predict_batch, rows)
        payload = await run_in_threadpool(workbook_bytes, results, "uploaded-tickets.csv")
    except Exception as exc:
        raise HTTPException(503, f"Laya batch inference failed: {exc}") from exc
    return Response(payload, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="LayaDesk_Batch_Report.xlsx"'})
