"""Run one real Laya classification on CUDA, downloading the checkpoint if needed."""
from backend.classifier.service import LayaClassifier

ticket = {
    "subject": "Duplicate March charge",
    "body": "I was billed twice for March. Please refund the second charge to my card.",
    "customer_tier": "Standard",
    "product": "LayaDesk",
}

if __name__ == "__main__":
    from scripts.check_cuda import torch  # preflight without a CPU fallback
    print(LayaClassifier().predict(ticket))
