"""Classify a CSV batch with Laya on CUDA and write a styled Excel report."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.batch import BatchInputError, classify_rows, parse_tickets_csv
from backend.classifier.service import LayaClassifier
from backend.reporting.workbook import build_workbook

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "dataset" / "tickets.csv", help="UTF-8 CSV with ticket_id, subject, body")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "LayaDesk_Batch_Report.xlsx", help="Destination .xlsx file")
    args = parser.parse_args()
    try:
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable. LayaDesk batch mode requires a CUDA GPU.")
        rows = parse_tickets_csv(args.input.read_bytes())
        print(f"Classifying {len(rows)} tickets with Laya on {torch.cuda.get_device_name(0)}...", flush=True)

        def progress(index: int, total: int, item: dict) -> None:
            print(f"{index}/{total}  {item['input']['ticket_id']}  {item['prediction']['department']}  {item['route']['status']}", flush=True)

        results = classify_rows(rows, LayaClassifier(), progress)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        build_workbook(results, args.input.name).save(args.output)
        print(f"Excel report: {args.output.resolve()}", flush=True)
        return 0
    except (OSError, BatchInputError, RuntimeError, ValueError) as exc:
        print(f"Batch failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
