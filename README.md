# LayaDesk

LayaDesk is a helpdesk ticket router built around [Laya](https://github.com/NandhaKishorM/laya). It asks seven typed questions in one model call: department, intent, urgency, frustration, explicit refund request, churn risk, and human escalation. A deterministic confidence gate turns the result into a queue recommendation. Humans approve or correct uncertain decisions. The app never issues refunds, cancels subscriptions, or changes accounts.

The repo includes a FastAPI + SQLite backend, a plain HTML/CSS/JavaScript dashboard, and **100 synthetic, labeled tickets** in [dataset/tickets.csv](dataset/tickets.csv), with 20 tickets per department.

## Run the presentation demo

The presentation mode runs without model weights. Its decisions are **simulated from the sample labels** for included tickets and from deterministic rules for newly submitted tickets. The UI and evaluation identify these as simulations; they are not Laya accuracy claims. Demo and CUDA launch scripts use separate SQLite databases.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn
.\run-demo.ps1
```

Open <http://127.0.0.1:8000>. For a vertical, screen-recording-friendly view, open <http://127.0.0.1:8000/?reels=1> or click **Watch the flow**. Use **Next scene** to show duplicate billing, a P1 outage, a negated refund request, a low-confidence ticket, and evaluation. A 9:16 capture at 1080×1920 works well. The demo does not generate a video file.

## Run real Laya inference on CUDA

LayaDesk **requires CUDA in real mode**. It instantiates `Router(device="cuda")`; it never silently switches to CPU. Use Python 3.11 and install a [CUDA-enabled PyTorch build appropriate for your GPU](https://pytorch.org/get-started/locally/) before the rest of the dependencies. For the GTX 960 (Maxwell), the PyTorch CUDA 12.6 wheel is the relevant legacy build. Laya's first model call downloads its checkpoint from Hugging Face.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cu126
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\run-cuda.ps1
```

`run-cuda.ps1` checks that CUDA is available before starting. If the installed PyTorch build does not support the GPU, or the checkpoint does not fit in available VRAM, inference fails visibly with HTTP 503. On the current machine, the detected GPU is a GeForce GTX 960 with 4 GB VRAM, and one real Laya classification completed successfully on CUDA.

## Use the app

1. Create a ticket or open one of the seeded samples.
2. Click **Classify ticket**. Laya answers all seven questions and the decision engine assigns `AUTO_ROUTED` or `NEEDS_REVIEW`.
3. Open **Human review** for uncertain, critical, or escalation cases. Approve or correct the prediction. Corrections are saved as ground truth.
4. Open **Evaluation** after classifying labeled tickets. The page shows accuracy, binary precision/recall/F1, wrong auto-route rate, and a department confusion matrix. It identifies the prediction source.

To route all seeded samples through the running CUDA server and export real predictions:

```powershell
.\.venv\Scripts\python.exe -m scripts.route_samples --limit 100
```

The output is [dataset/laya_predictions.csv](dataset/laya_predictions.csv). The script refuses demo mode.

Confidence gates: department confidence ≥0.85 auto-routes, 0.60–0.84 requires confirmation, and <0.60 goes to manual triage. Critical tickets and escalation probabilities ≥0.85 require human review regardless of department confidence. Explicit widespread outages, cross-tenant data exposure, blocked transactions from server errors, cancellation language, and contradictions such as “I don't want a refund” with a high refund score also go to human review. These safety checks affect the routing decision and tags while preserving raw model probabilities for evaluation.

These are initial policy thresholds, not calibrated production thresholds. Laya's own documentation notes that shipped checkpoint probabilities can be overconfident and recommends calibration on held-out data. See the [Laya README](https://github.com/NandhaKishorM/laya#calibration).

## API

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/tickets` | Submit a ticket |
| GET | `/api/tickets` | List and search tickets |
| GET | `/api/tickets/{id}` | Ticket detail |
| POST | `/api/tickets/{id}/classify` | Run Laya or explicitly selected demo simulation |
| POST | `/api/tickets/{id}/approve` | Approve prediction as reviewed label |
| POST | `/api/tickets/{id}/correct` | Save human correction and ground truth |
| GET | `/api/analytics` | Operational counts |
| GET | `/api/evaluation` | Evaluation on classified, labeled tickets |
| GET | `/api/dataset.csv` | Download the 100 sample tickets |
| GET | `/api/health` | Report mode and CUDA availability |

Interactive API docs: <http://127.0.0.1:8000/docs>.

## Dataset

The CSV columns are `ticket_id`, `subject`, `body`, `customer_id`, `customer_tier`, `previous_ticket_count`, `product`, `source_channel`, `created_at`, `department`, `intent`, `urgency`, `refund`, `churn`, and `escalation`. The first nine are input metadata; the last six are hand-authored synthetic ground truth. `refund`, `churn`, and `escalation` are lowercase `true`/`false`. Regenerate it with `py -3.11 scripts/generate_dataset.py`.

## Test and measured baseline

```powershell
.\.venv\Scripts\python.exe -m pip install httpx
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests cover the confidence gate, critical override, Laya response normalization, CUDA-only construction, the seeded dataset, review/correction, and evaluation. On the included **synthetic** 100-ticket set, actual Laya CUDA predictions achieved 80% department accuracy, 64% intent accuracy, and 30% urgency accuracy. The uncalibrated 0.85 confidence gate and safety rules sent 99% of cases to human review. Refund F1 was 0.60 and churn F1 was 0.40. The model identified 2 of 5 critical tickets as Critical; the deterministic incident safety rules raised all 5 to operational P1. The CSV contains the raw predictions and final routing decisions, and the dashboard evaluates the raw predictions against synthetic labels. These results show where question design, calibration, and real labeled support data are still needed; they are not production performance claims.
