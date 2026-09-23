"""Reapply current deterministic routing policy to stored Laya predictions."""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path

from backend.routing.engine import decide

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "layadesk-cuda.db")
    parser.add_argument("--csv", type=Path, default=ROOT / "dataset" / "laya_predictions.csv")
    args = parser.parse_args()
    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row
    rows = db.execute("""SELECT t.id, t.subject, t.body, t.customer_tier, t.status,
        p.department, p.department_confidence, p.urgency, p.refund_probability,
        p.churn_probability, p.escalation_probability FROM tickets t
        JOIN predictions p ON p.ticket_id=t.id WHERE p.source='laya'""").fetchall()
    routes = {}
    for row in rows:
        item = dict(row)
        route = decide(item, item["customer_tier"], item["subject"] + " " + item["body"])
        routes[item["id"]] = route
        if item["status"] in ("APPROVED", "CORRECTED"):
            continue
        db.execute("UPDATE tickets SET status=?, queue=?, priority=?, gate=?, tags=? WHERE id=?",
                   (route["status"], route["queue"], route["priority"], route["gate"],
                    json.dumps(route["tags"]), item["id"]))
    db.commit()
    db.close()
    if args.csv.exists():
        with args.csv.open(newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            fields = reader.fieldnames
            exported = list(reader)
        for item in exported:
            route = routes.get(item["ticket_id"])
            if route:
                for key in ("status", "queue", "priority"):
                    item[key] = route[key]
        with args.csv.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(exported)
    print(f"Reapplied policy to {len(rows)} stored Laya predictions")


if __name__ == "__main__":
    main()
