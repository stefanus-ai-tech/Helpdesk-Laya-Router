from __future__ import annotations

from typing import Any

DEPARTMENTS = ("Billing", "Technical Support", "Account Support", "Sales", "General Support")
INTENTS = (
    "Refund Request", "Payment Problem", "Bug Report", "Login Problem", "Account Change",
    "Cancellation", "Feature Request", "Product Question", "Sales Inquiry", "Other",
)
URGENCIES = ("Low", "Medium", "High", "Critical")


def decide(prediction: dict[str, Any], customer_tier: str = "Standard") -> dict[str, Any]:
    """Advisory routing only. No refund, cancellation, or account mutation."""
    confidence = float(prediction["department_confidence"])
    urgency = prediction["urgency"]
    tags = []
    if prediction["refund_probability"] >= 0.80:
        tags.append("refund-request")
    if prediction["churn_probability"] >= 0.80:
        tags.append("churn-risk")
    if urgency == "Critical":
        tags.append("p1-critical")
    if prediction["escalation_probability"] >= 0.85:
        tags.append("senior-review")

    immediate = urgency == "Critical" and customer_tier.lower() == "enterprise"
    if immediate:
        tags.append("enterprise-escalation")

    if confidence < 0.60:
        status = "NEEDS_REVIEW"
        gate = "manual_triage"
        queue = "Human Triage"
    elif confidence < 0.85:
        status = "NEEDS_REVIEW"
        gate = "human_confirmation"
        queue = prediction["department"] + " · Confirm"
    else:
        status = "AUTO_ROUTED"
        gate = "auto_route"
        queue = prediction["department"]

    # A critical case always needs human attention, even with high model confidence.
    if urgency == "Critical" or immediate:
        status = "NEEDS_REVIEW"
        gate = "critical_escalation"
        queue = "Senior Support"
    elif prediction["escalation_probability"] >= 0.85:
        status = "NEEDS_REVIEW"
        gate = "senior_confirmation"
        queue = prediction["department"] + " · Senior Review"

    return {
        "status": status,
        "gate": gate,
        "queue": queue,
        "priority": {"Critical": "P1", "High": "P2", "Medium": "P3", "Low": "P4"}[urgency],
        "tags": tags,
    }
