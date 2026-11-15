"""
FIM Engine Web API Integration (app/engine_api.py)
Minimal, modular FastAPI endpoints for:
1. Dataset upload (CSV and Parquet).
2. Running FIM Engine v1.1.
3. Returning analysis summary and two candidate lists.
4. Downloading ranked_candidates.csv and ranked_candidates.json.
"""

import os
import json
import time
import uuid
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from fim_engine.config import EngineConfig
from fim_engine.ingestion import load_dataset, detect_format
from fim_engine.prioritizer import Prioritizer
from fim_engine.reporting import ReportExporter
from fim_engine.models import TestClassification

router = APIRouter(prefix="/api/engine", tags=["fim_engine"])

# Isolated Workspace Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
UPLOADS_DIR = WORKSPACE_DIR / "engine_uploads"
RUNS_DIR = WORKSPACE_DIR / "engine_runs"
PRESET_V1_1_DIR = PROJECT_ROOT / "reports" / "playwright_week" / "v1_1"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)


class AnalysisRequest(BaseModel):
    source_path: Optional[str] = None
    file_path: Optional[str] = None
    upload_id: Optional[str] = None
    preset: Optional[str] = None
    dataset_name: Optional[str] = None
    format: Optional[str] = None
    table: str = "test_executions"
    w_recurrence: float = 0.60
    w_batch: float = 0.40
    max_records: Optional[int] = None


@router.post("/upload")
def upload_dataset(file: UploadFile = File(...)):
    """
    Upload a dataset (CSV or Parquet) into the isolated workspace.
    Streams directly to disk via shutil.copyfileobj to avoid memory overhead.
    """
    filename = Path(file.filename).name
    ext = Path(filename).suffix.lower()
    allowed_exts = {".parquet", ".pq", ".csv", ".json", ".jsonl", ".db", ".sqlite", ".sqlite3"}
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{ext}'. Allowed: {', '.join(sorted(allowed_exts))}",
        )

    upload_id = f"up_{uuid.uuid4().hex[:8]}"
    dest_path = UPLOADS_DIR / f"{upload_id}_{filename}"

    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        total_bytes = dest_path.stat().st_size
    except Exception as e:
        if dest_path.exists():
            dest_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {str(e)}")

    try:
        detected_fmt = detect_format(str(dest_path))
    except Exception:
        detected_fmt = "parquet" if ext in (".parquet", ".pq") else "csv"

    return {
        "upload_id": upload_id,
        "filename": filename,
        "source_path": str(dest_path),
        "file_path": str(dest_path),
        "file_size_bytes": total_bytes,
        "detected_format": detected_fmt,
    }


@router.post("/analyze")
def run_analysis(request: AnalysisRequest):
    """
    Run the existing FIM Engine v1.1 on the specified or uploaded dataset.
    Outputs results into an isolated workspace directory.
    """
    source = request.source_path or request.file_path or request.preset
    if not source and request.upload_id:
        matches = list(UPLOADS_DIR.glob(f"{request.upload_id}_*"))
        if matches:
            source = str(matches[0])
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Upload '{request.upload_id}' not found in uploads workspace.",
            )

    # Preset shortcut: if client requests preset playwright_v1_1, return existing validated results
    if source in ("playwright_v1_1", "playwright") or (request.preset in ("playwright_v1_1", "playwright")):
        summary_path = PRESET_V1_1_DIR / "analysis_summary.json"
        if summary_path.exists():
            with open(summary_path, "r", encoding="utf-8") as f:
                summary = json.load(f)
            return {
                "run_id": "playwright_v1_1",
                "status": "completed",
                "summary": summary,
            }

    if not source:
        raise HTTPException(status_code=400, detail="Either 'source_path' or 'upload_id' must be provided.")

    if not os.path.exists(source) and not source.startswith(r"\\"):
        # Check if relative to UPLOADS_DIR or PROJECT_ROOT
        if (UPLOADS_DIR / source).exists():
            source = str(UPLOADS_DIR / source)
        elif (PROJECT_ROOT / source).exists():
            source = str(PROJECT_ROOT / source)
        else:
            raise HTTPException(status_code=404, detail=f"Source path not found: {source}")

    start_time = time.time()
    run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    output_dir = RUNS_DIR / run_id / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    config = EngineConfig(
        weight_pipeline_recurrence=request.w_recurrence,
        weight_batch_frequency=request.w_batch,
    )
    config.validate()

    records = load_dataset(
        source=source,
        format=request.format,
        max_records=request.max_records,
        table_name=request.table,
    )

    if not records:
        raise HTTPException(status_code=400, detail="No test execution records found in dataset source.")

    prioritizer = Prioritizer(config=config)
    ranked_candidates = prioritizer.prioritize_all(records)

    exporter = ReportExporter()
    exported_files = exporter.export(
        candidates=ranked_candidates,
        output_dir=str(output_dir),
        dataset_source=source,
        total_records=len(records),
        config_info={
            "formula": f"Priority = {request.w_recurrence:.2f} * Pipeline_Recurrence + {request.w_batch:.2f} * Mixed_Batch_Frequency",
            "ranking_architecture": "Evidence-Stratified (High Evidence -> Moderate Evidence -> Low Evidence)",
            "weight_pipeline_recurrence": request.w_recurrence,
            "weight_batch_frequency": request.w_batch,
        },
    )

    duration = round(time.time() - start_time, 3)

    with open(exported_files["summary"], "r", encoding="utf-8") as f:
        summary = json.load(f)

    return {
        "run_id": run_id,
        "status": "completed",
        "duration_seconds": duration,
        "total_records": len(records),
        "total_tests": len(ranked_candidates),
        "summary": summary,
    }


def _resolve_output_dir(run_id: str) -> Path:
    if run_id == "playwright_v1_1":
        return PRESET_V1_1_DIR
    target = RUNS_DIR / run_id / "reports"
    if target.exists():
        return target
    raise HTTPException(status_code=404, detail=f"Run ID '{run_id}' not found.")


@router.get("/summary/{run_id}")
def get_analysis_summary(run_id: str):
    """Retrieve analysis summary for a run."""
    output_dir = _resolve_output_dir(run_id)
    summary_path = output_dir / "analysis_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="Summary not found.")
    with open(summary_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/candidates/{run_id}")
def get_candidates(run_id: str):
    """
    Retrieve candidate lists split into:
    1. Verified Flaky Candidates (In-batch retry verified)
    2. Cross-Pipeline Intermittent Candidates
    """
    output_dir = _resolve_output_dir(run_id)
    json_path = output_dir / "ranked_candidates.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Ranked candidates not found.")

    with open(json_path, "r", encoding="utf-8") as f:
        candidates = json.load(f)

    verified = [
        c for c in candidates
        if c.get("classification") == TestClassification.FLAKY_CANDIDATE_IN_BATCH_VERIFIED.value
    ]
    intermittent = [
        c for c in candidates
        if c.get("classification") == TestClassification.INTERMITTENT_CANDIDATE_CROSS_PIPELINE.value
    ]
    failing = [
        c for c in candidates
        if c.get("classification") == TestClassification.CONSISTENTLY_FAILING.value
    ]
    passing = [
        c for c in candidates
        if c.get("classification") == TestClassification.CONSISTENTLY_PASSING.value
    ]

    return {
        "run_id": run_id,
        "total_candidates": len(verified) + len(intermittent),
        "verified_flaky_candidates": verified,
        "cross_pipeline_intermittent_candidates": intermittent,
        "consistently_failing_count": len(failing),
        "consistently_passing_count": len(passing),
    }


@router.get("/download/{run_id}/pdf")
def download_pdf_report(run_id: str):
    """
    Download dynamic PDF research report for a run.
    """
    return download_candidate_report(run_id=run_id, file_format="pdf")


@router.get("/download/{run_id}/{file_format}")
def download_candidate_report(run_id: str, file_format: str):
    """
    Download ranked_candidates.csv, ranked_candidates.json, analysis summary, or dynamic PDF report.
    """
    output_dir = _resolve_output_dir(run_id)
    fmt = file_format.lower()

    if fmt == "csv":
        target = output_dir / "ranked_candidates.csv"
        filename = f"ranked_candidates_{run_id}.csv"
        media_type = "text/csv"
    elif fmt == "json":
        target = output_dir / "ranked_candidates.json"
        filename = f"ranked_candidates_{run_id}.json"
        media_type = "application/json"
    elif fmt == "summary":
        target = output_dir / "analysis_summary.json"
        filename = f"analysis_summary_{run_id}.json"
        media_type = "application/json"
    elif fmt == "pdf":
        target = output_dir / f"FIM_Research_Report_{run_id}.pdf"
        filename = f"FIM_Research_Report_{run_id}.pdf"
        media_type = "application/pdf"
        if not target.exists():
            summary_path = output_dir / "analysis_summary.json"
            candidates_path = output_dir / "ranked_candidates.json"
            if not summary_path.exists() or not candidates_path.exists():
                raise HTTPException(status_code=404, detail=f"Analysis results for run ID '{run_id}' not found.")
            with open(summary_path, "r", encoding="utf-8") as f:
                summary_data = json.load(f)
            with open(candidates_path, "r", encoding="utf-8") as f:
                candidates_data = json.load(f)
            from fim_engine.pdf_report import generate_pdf_report
            generate_pdf_report(
                run_id=run_id,
                summary=summary_data,
                candidates=candidates_data,
                output_pdf_path=str(target),
            )
    else:
        raise HTTPException(status_code=400, detail="Invalid format. Allowed: 'csv', 'json', 'summary', 'pdf'")

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"File {filename} not found.")

    return FileResponse(path=str(target), filename=filename, media_type=media_type)
