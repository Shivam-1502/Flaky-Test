from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from .database import initialize_database, fetch_all
from .metrics import (
    all_test_metrics, compute_test_metrics, suite_metrics,
    pipeline_metrics, systemic_metrics, environment_metrics
)

DASHBOARD_TEMPLATE = Path(__file__).resolve().parent / "templates" / "dashboard.html"

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield

app = FastAPI(
    title="FIM - Flakiness Impact Measurement Framework",
    version="0.2.0",
    description="Research backend for measuring the quality impact of flaky tests.",
    lifespan=lifespan,
)

@app.get("/")
def root():
    return {"project": "FIM", "version": "0.2.0", "status": "running", "dashboard": "/dashboard"}

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    if DASHBOARD_TEMPLATE.exists():
        return HTMLResponse(content=DASHBOARD_TEMPLATE.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Dashboard template not found. Run: python -m scripts.build_dashboard</h1>", status_code=404)

@app.get("/api/runs")
def runs():
    return [dict(row) for row in fetch_all()]

@app.get("/api/metrics/tests")
def test_metrics():
    return all_test_metrics()

@app.get("/api/metrics/tests/{test_id}")
def test_metric(test_id: str):
    result = compute_test_metrics(test_id)
    if result["executions"] == 0:
        raise HTTPException(status_code=404, detail="Test not found")
    return result

@app.get("/api/metrics/suite")
def suite():
    return suite_metrics()

@app.get("/api/metrics/pipelines")
@app.get("/api/metrics/pipeline")
def pipelines():
    return pipeline_metrics()

@app.get("/api/metrics/systemic")
def systemic():
    return systemic_metrics()

@app.get("/api/metrics/environments")
def environments():
    return environment_metrics()

@app.get("/api/metrics/export")
def export_metrics():
    pipe = pipeline_metrics()
    return {
        "suite": suite_metrics(),
        "tests": all_test_metrics(),
        "environments": environment_metrics(),
        "pipeline": pipe,
        "pipelines": pipe,
        "systemic": systemic_metrics()
    }
