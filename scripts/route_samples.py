"""Classify the seeded 100 CSV tickets through the running CUDA API."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def get_json(url: str, method: str = "GET") -> dict:
    request = Request(url, method=method, headers={"Accept": "application/json"})
    with urlopen(request, timeout=120) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", type=Path, default=ROOT / "dataset" / "laya_predictions.csv")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    health = get_json(f"{base}/api/health")
    if health["mode"] != "laya" or health["device"] != "cuda" or not health["cuda_available"]:
        parser.error("The API must be running in real Laya CUDA mode, not demo mode.")
    with (ROOT / "dataset" / "tickets.csv").open(newline="", encoding="utf-8") as file:
        sample_ids = [row["ticket_id"] for row in csv.DictReader(file)][:args.limit]
    fields = ["ticket_id", "department", "department_confidence", "intent", "intent_confidence",
              "urgency", "urgency_confidence", "frustration", "frustration_confidence",
              "refund_probability", "churn_probability", "escalation_probability", "status", "queue",
              "priority", "model", "source"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for i, ticket_id in enumerate(sample_ids, 1):
            try:
                result = get_json(f"{base}/api/tickets/{ticket_id}/classify", "POST")
            except HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")
                raise SystemExit(f"Stopped at {ticket_id}: HTTP {error.code} {detail}") from error
            writer.writerow({"ticket_id": ticket_id, **{key: result[key] for key in fields if key != "ticket_id"}})
            file.flush()
            print(f"{i:3d}/{len(sample_ids)}  {ticket_id}  {result['department']}  {result['status']}", flush=True)
    metrics = get_json(f"{base}/api/evaluation")
    print(f"Saved {len(sample_ids)} real CUDA predictions to {args.output}")
    print(f"Evaluation: {metrics.get('evaluated', 0)} labeled predictions; department accuracy {metrics.get('department_accuracy', 'n/a')}")


if __name__ == "__main__":
    main()
