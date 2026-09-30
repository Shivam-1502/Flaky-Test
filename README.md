# FIM — Flakiness Impact Measurement Framework v0.2

**Research project:** A Software Quality Metrics Framework for Measuring the Quality Impact of Flaky Tests in Continuous Integration.

Team:
- Lakshay Chaudhary — 23293910034
- Shivam Kumar — 23293916037
- B.Tech CSE, Section A, University of Delhi

## v0.2 additions
- Pipeline-level records
- Controlled one-rerun intervention
- Rerun overhead and recovery rate
- Pipeline failure rate
- Failure-signature clustering
- Systemic flakiness metrics
- Environment sensitivity
- Baseline test-level SQA metrics

## Run
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m scripts.run_experiment --runs 200
uvicorn app.main:app --reload
```

Open:
http://127.0.0.1:8000/docs

## Research note
All synthetic environments and failure behaviors are controlled simulations. They are not evidence about real operating systems or production CI. Real-world validation will be added later.

No final composite "quality score" is included yet. We will derive and validate the framework experimentally instead of choosing arbitrary weights.
