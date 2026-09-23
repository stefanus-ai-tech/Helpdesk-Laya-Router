from __future__ import annotations

import csv
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.classifier.service import make_classifier
from backend.db import connection, init_db, record
from backend.evaluation.metrics import calculate
from backend.routing.engine import DEPARTMENTS, INTENTS, URGENCIES, decide

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "dataset" / "tickets.csv"
classifier = make_classifier()


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
        prediction = classifier.predict(ticket)
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
