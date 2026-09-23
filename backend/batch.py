"""CSV batch validation and CUDA Laya classification."""
from __future__ import annotations

import csv
from io import StringIO
from typing import Callable

from backend.classifier.service import LayaClassifier
from backend.routing.engine import decide

REQUIRED = {"ticket_id", "subject", "body"}
LABEL_FIELDS = {"department", "intent", "urgency", "refund", "churn", "escalation"}


class BatchInputError(ValueError):
    pass


def parse_tickets_csv(content: bytes, max_rows: int = 500) -> list[dict[str, str]]:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BatchInputError("CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(StringIO(decoded, newline=""))
    if not reader.fieldnames:
        raise BatchInputError("CSV is empty")
    missing = REQUIRED - set(reader.fieldnames)
    if missing:
        raise BatchInputError("Missing required columns: " + ", ".join(sorted(missing)))
    if len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise BatchInputError("CSV has duplicate column names")
    rows = []
    seen = set()
    for row_number, original in enumerate(reader, 2):
        if None in original:
            raise BatchInputError(f"Row {row_number} has more fields than the header")
        if not any((v or "").strip() for v in original.values()):
            continue
        row = {key: (value or "").strip() for key, value in original.items()}
        for key in REQUIRED:
            if not row[key]:
                raise BatchInputError(f"Row {row_number} has no {key}")
        if row["ticket_id"] in seen:
            raise BatchInputError(f"Duplicate ticket ID: {row['ticket_id']}")
        if len(row["subject"]) < 3 or len(row["body"]) < 8:
            raise BatchInputError(f"Row {row_number} needs a subject (3+ chars) and body (8+ chars)")
        if len(row["body"]) > 5000:
            raise BatchInputError(f"Row {row_number} body exceeds 5000 characters")
        seen.add(row["ticket_id"])
        rows.append(row)
        if len(rows) > max_rows:
            raise BatchInputError(f"CSV exceeds {max_rows} tickets")
    if not rows:
        raise BatchInputError("CSV has no ticket rows")
    return rows


def classify_rows(
    rows: list[dict[str, str]],
    classifier: LayaClassifier | None = None,
    progress: Callable[[int, int, dict], None] | None = None,
) -> list[dict]:
    classifier = classifier or LayaClassifier()
    results = []
    for index, row in enumerate(rows, 1):
        ticket = {
            "subject": row["subject"],
            "body": row["body"],
            "customer_tier": row.get("customer_tier") or "Standard",
            "product": row.get("product") or "LayaDesk",
        }
        prediction = classifier.predict(ticket)
        if prediction.get("source") != "laya":
            raise RuntimeError("Batch classification requires real Laya inference")
        route = decide(prediction, ticket["customer_tier"], row["subject"] + " " + row["body"])
        item = {"input": row, "prediction": prediction, "route": route}
        results.append(item)
        if progress:
            progress(index, len(rows), item)
    return results
