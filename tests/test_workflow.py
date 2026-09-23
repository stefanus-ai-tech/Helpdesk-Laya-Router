import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.classifier.service import LayaClassifier, normalize_laya
from backend.routing.engine import decide


class RoutingTests(unittest.TestCase):
    def test_confidence_gate_and_critical_override(self):
        base = {"department": "Billing", "department_confidence": .93, "urgency": "Medium",
                "refund_probability": .96, "churn_probability": .04, "escalation_probability": .10}
        self.assertEqual(decide(base)["status"], "AUTO_ROUTED")
        self.assertIn("refund-request", decide(base)["tags"])
        self.assertEqual(decide({**base, "department_confidence": .74})["gate"], "human_confirmation")
        self.assertEqual(decide({**base, "department_confidence": .48})["gate"], "manual_triage")
        self.assertEqual(decide({**base, "urgency": "Critical"}, "Enterprise")["queue"], "Senior Support")

    def test_policy_reviews_model_misses_without_changing_model_score(self):
        base = {"department": "Billing", "department_confidence": .93, "urgency": "High",
                "refund_probability": .84, "churn_probability": .62, "escalation_probability": .20}
        refund = decide(base, text="I don't want a refund. Explain this duplicate charge.")
        self.assertEqual(refund["gate"], "refund_conflict")
        self.assertNotIn("refund-request", refund["tags"])
        churn = decide(base, text="Fix this or we're cancelling our plan.")
        self.assertEqual(churn["gate"], "policy_escalation")
        self.assertIn("cancellation-language-review", churn["tags"])

    def test_policy_catches_explicit_outage_without_rewriting_model_urgency(self):
        prediction = {"department": "Technical Support", "department_confidence": .92,
                      "urgency": "Medium", "refund_probability": .02, "churn_probability": .04,
                      "escalation_probability": .12}
        route = decide(prediction, text="Our production API is down and customers cannot checkout.")
        self.assertEqual(route["priority"], "P1")
        self.assertEqual(route["gate"], "policy_critical")
        self.assertEqual(prediction["urgency"], "Medium")

    def test_laya_normalization(self):
        result = {"routing": {"model": "english"}, "answers": {
            "department": {"choice": "Billing", "confidence": .91},
            "intent": {"choice": "Refund Request", "confidence": .87},
            "urgency": {"score": 2.1, "confidence": .8},
            "frustration": {"score": 2.7, "confidence": .7},
            "refund_requested": {"noul": .98}, "churn_risk": {"noul": .13},
            "human_escalation": {"noul": .28},
        }}
        prediction = normalize_laya(result)
        self.assertEqual(prediction["urgency"], "High")
        self.assertEqual(prediction["frustration"], 3)
        self.assertEqual(prediction["source"], "laya")

    def test_laya_router_requires_cuda(self):
        called = []
        class FakeRouter:
            def __init__(self, **kwargs): called.append(kwargs)
            def predict(self, state, questions):
                raise RuntimeError("test stop before inference")
        previous = sys.modules.get("laya")
        sys.modules["laya"] = types.SimpleNamespace(Router=FakeRouter)
        try:
            with self.assertRaisesRegex(RuntimeError, "test stop"):
                LayaClassifier().predict({"subject": "Hello", "body": "A test body"})
            self.assertEqual(called, [{"device": "cuda"}])
        finally:
            if previous is None: del sys.modules["laya"]
            else: sys.modules["laya"] = previous


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        os.environ["LAYADESK_DB"] = str(Path(self.temp.name) / "test.db")
        os.environ["LAYADESK_MODE"] = "demo"
        import backend.db as db
        db.DB_PATH = Path(os.environ["LAYADESK_DB"])
        import backend.api.main as main
        main.classifier = main.make_classifier()
        self.client_context = TestClient(main.app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.temp.cleanup()

    def test_seed_classify_review_and_metrics(self):
        self.assertEqual(self.client.get("/api/analytics").json()["total"], 100)
        billing = self.client.post("/api/tickets/TCK-0001/classify").json()
        self.assertEqual(billing["department"], "Billing")
        self.assertEqual(billing["status"], "AUTO_ROUTED")
        self.assertEqual(billing["source"], "simulation")
        outage = self.client.post("/api/tickets/TCK-0021/classify").json()
        self.assertEqual(outage["priority"], "P1")
        self.assertEqual(outage["status"], "NEEDS_REVIEW")
        ambiguous = self.client.post("/api/tickets/TCK-0100/classify").json()
        self.assertEqual(ambiguous["gate"], "manual_triage")
        corrected = self.client.post("/api/tickets/TCK-0100/correct", json={
            "department": "General Support", "intent": "Product Question", "urgency": "Low",
            "refund": False, "churn": False, "escalation": False,
        }).json()
        self.assertEqual(corrected["status"], "CORRECTED")
        metrics = self.client.get("/api/evaluation").json()
        self.assertEqual(metrics["evaluated"], 3)
        self.assertEqual(metrics["prediction_sources"], {"simulation": 3})
        self.assertEqual(metrics["critical_support"], 1)
        self.assertEqual(metrics["operational_p1_recall"], 1.0)
        self.assertEqual(self.client.get("/api/dataset.csv").status_code, 200)

    def test_new_ticket_create_then_classify(self):
        response = self.client.post("/api/tickets", json={"subject":"Need a refund", "body":"Please refund the duplicate payment today."})
        self.assertEqual(response.status_code, 201)
        ticket = response.json()
        self.assertEqual(ticket["status"], "INCOMING")
        classified = self.client.post(f"/api/tickets/{ticket['id']}/classify").json()
        self.assertEqual(classified["intent"], "Refund Request")
        self.assertEqual(classified["department"], "Billing")


if __name__ == "__main__":
    unittest.main()
