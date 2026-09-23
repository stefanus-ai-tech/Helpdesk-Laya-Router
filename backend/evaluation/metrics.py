from __future__ import annotations

from collections import Counter


def _binary_metrics(pairs: list[tuple[bool, bool]]) -> dict:
    tp = sum(pred and truth for pred, truth in pairs)
    fp = sum(pred and not truth for pred, truth in pairs)
    fn = sum(not pred and truth for pred, truth in pairs)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3), "support": sum(t for _, t in pairs)}


def calculate(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"evaluated": 0, "message": "Classify labeled tickets to see evaluation metrics."}
    def accuracy(field):
        return round(sum(r[f"pred_{field}"] == r[f"actual_{field}"] for r in rows) / n, 3)
    departments = sorted({r["actual_department"] for r in rows} | {r["pred_department"] for r in rows})
    matrix = {a: {p: 0 for p in departments} for a in departments}
    for r in rows:
        matrix[r["actual_department"]][r["pred_department"]] += 1
    auto = [r for r in rows if r["status"] == "AUTO_ROUTED"]
    wrong_auto = sum(r["pred_department"] != r["actual_department"] for r in auto)
    return {
        "evaluated": n,
        "department_accuracy": accuracy("department"),
        "intent_accuracy": accuracy("intent"),
        "urgency_accuracy": accuracy("urgency"),
        "refund": _binary_metrics([(r["refund_probability"] >= .80, bool(r["actual_refund"])) for r in rows]),
        "churn": _binary_metrics([(r["churn_probability"] >= .80, bool(r["actual_churn"])) for r in rows]),
        "escalation_accuracy": round(sum((r["escalation_probability"] >= .85) == bool(r["actual_escalation"]) for r in rows) / n, 3),
        "auto_route_rate": round(len(auto) / n, 3),
        "human_review_rate": round((n - len(auto)) / n, 3),
        "wrong_auto_route_rate": round(wrong_auto / len(auto), 3) if auto else 0.0,
        "average_department_confidence": round(sum(r["department_confidence"] for r in rows) / n, 3),
        "confusion_matrix": matrix,
        "truth_origins": dict(Counter(r["origin"] for r in rows)),
        "prediction_sources": dict(Counter(r["source"] for r in rows)),
    }
