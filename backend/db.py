from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.getenv("LAYADESK_DB", Path(__file__).resolve().parents[1] / "layadesk.db"))


@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def init_db():
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            customer_id TEXT,
            customer_tier TEXT NOT NULL DEFAULT 'Standard',
            product TEXT,
            source_channel TEXT,
            previous_ticket_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'INCOMING',
            queue TEXT,
            priority TEXT,
            gate TEXT,
            tags TEXT NOT NULL DEFAULT '[]',
            sample_labels TEXT
        );
        CREATE TABLE IF NOT EXISTS predictions (
            ticket_id TEXT PRIMARY KEY REFERENCES tickets(id) ON DELETE CASCADE,
            department TEXT NOT NULL,
            department_confidence REAL NOT NULL,
            intent TEXT NOT NULL,
            intent_confidence REAL NOT NULL,
            urgency TEXT NOT NULL,
            urgency_confidence REAL NOT NULL,
            frustration INTEGER NOT NULL,
            frustration_confidence REAL NOT NULL,
            refund_probability REAL NOT NULL,
            churn_probability REAL NOT NULL,
            escalation_probability REAL NOT NULL,
            model TEXT NOT NULL,
            source TEXT NOT NULL,
            classified_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ground_truth (
            ticket_id TEXT PRIMARY KEY REFERENCES tickets(id) ON DELETE CASCADE,
            department TEXT NOT NULL,
            intent TEXT NOT NULL,
            urgency TEXT NOT NULL,
            refund INTEGER NOT NULL,
            churn INTEGER NOT NULL,
            escalation INTEGER NOT NULL,
            origin TEXT NOT NULL,
            reviewed_at TEXT NOT NULL
        );
        """)


def record(row):
    item = dict(row)
    for key in ("tags", "sample_labels"):
        if key in item:
            item[key] = json.loads(item[key]) if item[key] else ({} if key == "sample_labels" else [])
    return item
