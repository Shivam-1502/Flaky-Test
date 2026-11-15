"""
Targeted integration tests for FIM Engine v1.1 Web API Endpoints.
Tests upload, engine analysis, summary retrieval, split candidate lists, and report downloads.
Executes completely synchronously without network/socket binding.
"""

import io
import json
import base64
import zlib
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from fastapi import HTTPException

from app.engine_api import (
    upload_dataset,
    run_analysis,
    get_analysis_summary,
    get_candidates,
    download_candidate_report,
    download_pdf_report,
    AnalysisRequest,
    PROJECT_ROOT,
)


def extract_pdf_streams_text(pdf_path: Path) -> str:
    """Helper to decompress and extract ASCII text from ReportLab PDF streams."""
    data = pdf_path.read_bytes()
    idx = 0
    all_text = []
    while True:
        s = data.find(b"stream", idx)
        if s == -1:
            break
        e = data.find(b"endstream", s)
        if e == -1:
            break
        chunk = data[s + 6 : e].strip()
        if not chunk.endswith(b"~>"):
            chunk = chunk + b"~>"
        try:
            raw = base64.a85decode(chunk, adobe=True)
            dec = zlib.decompress(raw).decode("latin1", errors="ignore")
            all_text.append(dec)
        except Exception:
            pass
        idx = e + 9
    return "\n".join(all_text)


def test_preset_summary_and_candidates():
    # 1. Summary
    summary = get_analysis_summary("playwright_v1_1")
    assert summary["metadata"]["total_records_ingested"] == 2056823
    assert summary["metadata"]["total_unique_tests"] == 4042

    cb = summary["classification_breakdown"]
    assert cb["Flaky candidate (In-batch retry verified)"]["count"] == 36
    assert cb["Intermittent candidate (Cross-pipeline observational)"]["count"] == 43
    assert cb["Consistently failing"]["count"] == 1
    assert cb["Consistently passing"]["count"] == 3962

    # 2. Split candidate lists
    candidates = get_candidates("playwright_v1_1")
    assert len(candidates["verified_flaky_candidates"]) == 36
    assert len(candidates["cross_pipeline_intermittent_candidates"]) == 43
    assert candidates["consistently_failing_count"] == 1
    assert candidates["consistently_passing_count"] == 3962

    # Top verified candidate verification
    top_verified = candidates["verified_flaky_candidates"][0]
    assert "browsercontext-fetch-happy-eyeballs" in top_verified["test_case_name"]
    assert top_verified["priority_score"] == 0.3413
    assert top_verified["evidence_level"] == "High evidence"


def test_download_reports():
    # 1. CSV download
    csv_resp = download_candidate_report("playwright_v1_1", "csv")
    assert csv_resp.status_code == 200
    assert csv_resp.filename.endswith(".csv")
    assert Path(csv_resp.path).exists()

    # 2. JSON download
    json_resp = download_candidate_report("playwright_v1_1", "json")
    assert json_resp.status_code == 200
    assert json_resp.filename.endswith(".json")
    assert Path(json_resp.path).exists()

    # 3. Summary download
    sum_resp = download_candidate_report("playwright_v1_1", "summary")
    assert sum_resp.status_code == 200
    assert sum_resp.filename.endswith(".json")
    assert Path(sum_resp.path).exists()

    # 4. PDF download via download_candidate_report
    pdf_resp = download_candidate_report("playwright_v1_1", "pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.media_type == "application/pdf"
    assert pdf_resp.filename == "FIM_Research_Report_playwright_v1_1.pdf"
    pdf_path = Path(pdf_resp.path)
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF-")

    # 5. PDF download via dedicated endpoint download_pdf_report
    pdf_direct = download_pdf_report("playwright_v1_1")
    assert pdf_direct.status_code == 200
    assert pdf_direct.filename == "FIM_Research_Report_playwright_v1_1.pdf"

    # 6. Verify PDF internal content streams
    pdf_text = extract_pdf_streams_text(pdf_path)
    assert "playwright_v1_1" in pdf_text
    assert "2,056,823" in pdf_text
    assert "88.72%" in pdf_text
    assert "66.18%" in pdf_text
    assert "browsercontext" in pdf_text
    assert "happy-eye" in pdf_text
    assert "Verified Flaky Candidates" in pdf_text
    assert "Intermittent Candidates" in pdf_text

    # 7. Error handling on missing run ID
    with pytest.raises(HTTPException) as exc_missing:
        download_candidate_report("nonexistent_run_invalid_999", "pdf")
    assert exc_missing.value.status_code == 404


def test_upload_and_analyze_workflow():
    # Synthetic test CSV content with the exact user columns
    csv_content = (
        "test_case_name,test_case_environment,pipeline_id,retry_count,result,duration,failure_symptoms\n"
        "test_integ_flaky,linux,p1,0,failed,1.2,Timeout\n"
        "test_integ_flaky,linux,p1,1,passed,0.8,\n"
        "test_integ_flaky,linux,p2,0,passed,0.7,\n"
        "test_integ_intermittent,linux,p1,0,failed,1.0,AssertionError\n"
        "test_integ_intermittent,linux,p2,0,passed,0.9,\n"
        "test_integ_intermittent,linux,p3,0,passed,0.9,\n"
        "test_integ_stable,linux,p1,0,passed,0.5,\n"
        "test_integ_stable,linux,p2,0,passed,0.5,\n"
        "test_integ_stable,linux,p3,0,passed,0.5,\n"
    ).encode("utf-8")

    # 1. Upload
    mock_file = MagicMock()
    mock_file.filename = "synthetic_run.csv"
    mock_file.file = io.BytesIO(csv_content)

    upload_res = upload_dataset(mock_file)

    assert "upload_id" in upload_res
    assert "source_path" in upload_res
    assert "file_path" in upload_res
    assert upload_res["source_path"] == upload_res["file_path"]
    assert upload_res["detected_format"] == "csv"
    assert Path(upload_res["file_path"]).exists()

    # 2. Analyze using the exact frontend payload (file_path + dataset_name)
    frontend_req = AnalysisRequest(
        file_path=upload_res["file_path"],
        dataset_name=upload_res["filename"],
        format="csv",
    )
    res_frontend = run_analysis(frontend_req)
    assert res_frontend["status"] == "completed"

    # 3. Analyze using upload_id
    upload_id_req = AnalysisRequest(
        upload_id=upload_res["upload_id"],
        format="csv",
        w_recurrence=0.60,
        w_batch=0.40,
    )
    analysis_res = run_analysis(upload_id_req)
    assert analysis_res["status"] == "completed"
    run_id = analysis_res["run_id"]

    # 4. Analyze using source_path
    source_path_req = AnalysisRequest(
        source_path=upload_res["source_path"],
        format="csv",
    )
    res_source_path = run_analysis(source_path_req)
    assert res_source_path["status"] == "completed"

    # 5. Analyze using preset
    preset_req = AnalysisRequest(
        preset="playwright_v1_1",
    )
    res_preset = run_analysis(preset_req)
    assert res_preset["status"] == "completed"
    assert res_preset["run_id"] == "playwright_v1_1"

    # 6. Test missing reference validation (400)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_400:
        run_analysis(AnalysisRequest())
    assert exc_400.value.status_code == 400
    assert "Either 'source_path' or 'upload_id' must be provided" in exc_400.value.detail

    # 7. Test nonexistent upload_id validation (404)
    with pytest.raises(HTTPException) as exc_404:
        run_analysis(AnalysisRequest(upload_id="up_nonexistent999"))
    assert exc_404.value.status_code == 404

    # 8. Summary check
    summary = get_analysis_summary(run_id)
    assert summary["metadata"]["total_unique_tests"] == 3
    cb = summary["classification_breakdown"]
    assert cb["Flaky candidate (In-batch retry verified)"]["count"] == 1
    assert cb["Intermittent candidate (Cross-pipeline observational)"]["count"] == 1
    assert cb["Consistently passing"]["count"] == 1

    # 9. Candidates list check
    cand_lists = get_candidates(run_id)
    assert len(cand_lists["verified_flaky_candidates"]) == 1
    assert cand_lists["verified_flaky_candidates"][0]["test_case_name"] == "test_integ_flaky"
    assert len(cand_lists["cross_pipeline_intermittent_candidates"]) == 1
    assert cand_lists["cross_pipeline_intermittent_candidates"][0]["test_case_name"] == "test_integ_intermittent"

    # 10. Download check (CSV, JSON, and dynamic PDF)
    csv_down = download_candidate_report(run_id, "csv")
    assert csv_down.status_code == 200
    assert Path(csv_down.path).exists()

    json_down = download_candidate_report(run_id, "json")
    assert json_down.status_code == 200
    assert Path(json_down.path).exists()

    pdf_down = download_candidate_report(run_id, "pdf")
    assert pdf_down.status_code == 200
    assert pdf_down.media_type == "application/pdf"
    assert pdf_down.filename == f"FIM_Research_Report_{run_id}.pdf"
    csv_pdf_path = Path(pdf_down.path)
    assert csv_pdf_path.exists()
    assert csv_pdf_path.read_bytes().startswith(b"%PDF-")
    csv_pdf_text = extract_pdf_streams_text(csv_pdf_path)
    assert run_id in csv_pdf_text
    assert "test_integ_flaky" in csv_pdf_text
    assert "test_integ_intermittent" in csv_pdf_text


def test_parquet_upload_and_analyze_workflow():
    import pyarrow as pa
    import pyarrow.parquet as pq

    # Create PyArrow table for synthetic execution records
    data = {
        "test_case_name": ["test_pq_flaky", "test_pq_flaky", "test_pq_flaky", "test_pq_intermittent", "test_pq_intermittent", "test_pq_intermittent"],
        "test_case_environment": ["ubuntu", "ubuntu", "ubuntu", "ubuntu", "ubuntu", "ubuntu"],
        "pipeline_id": ["p1", "p1", "p2", "p1", "p2", "p3"],
        "retry_count": [0, 1, 0, 0, 0, 0],
        "result": ["failed", "passed", "passed", "failed", "passed", "passed"],
        "duration": [1.5, 1.2, 1.1, 0.9, 0.8, 0.85],
        "failure_symptoms": ["AssertionError", None, None, "TimeoutError", None, None],
    }
    table = pa.Table.from_pydict(data)
    sink = io.BytesIO()
    pq.write_table(table, sink)
    parquet_bytes = sink.getvalue()

    # 1. Upload Parquet
    mock_file = MagicMock()
    mock_file.filename = "synthetic_run.parquet"
    mock_file.file = io.BytesIO(parquet_bytes)

    upload_res = upload_dataset(mock_file)
    assert upload_res["detected_format"] == "parquet"
    assert "upload_id" in upload_res
    assert "source_path" in upload_res
    assert "file_path" in upload_res
    assert Path(upload_res["file_path"]).exists()

    # 2. Analyze with frontend combined payload
    req = AnalysisRequest(
        upload_id=upload_res["upload_id"],
        source_path=upload_res["source_path"],
        file_path=upload_res["file_path"],
        format="parquet",
    )
    res = run_analysis(req)
    assert res["status"] == "completed"
    run_id = res["run_id"]

    # 3. Retrieve candidates
    candidates = get_candidates(run_id)
    assert len(candidates["verified_flaky_candidates"]) == 1
    assert candidates["verified_flaky_candidates"][0]["test_case_name"] == "test_pq_flaky"
    assert len(candidates["cross_pipeline_intermittent_candidates"]) == 1
    assert candidates["cross_pipeline_intermittent_candidates"][0]["test_case_name"] == "test_pq_intermittent"

    # 4. Download JSON and dynamic PDF
    json_dl = download_candidate_report(run_id, "json")
    assert json_dl.status_code == 200
    assert Path(json_dl.path).exists()

    pdf_dl = download_candidate_report(run_id, "pdf")
    assert pdf_dl.status_code == 200
    assert pdf_dl.media_type == "application/pdf"
    assert pdf_dl.filename == f"FIM_Research_Report_{run_id}.pdf"
    pq_pdf_path = Path(pdf_dl.path)
    assert pq_pdf_path.exists()
    assert pq_pdf_path.read_bytes().startswith(b"%PDF-")
    pq_pdf_text = extract_pdf_streams_text(pq_pdf_path)
    assert run_id in pq_pdf_text
    assert "test_pq_flaky" in pq_pdf_text
    assert "test_pq_intermittent" in pq_pdf_text


def test_dashboard_engine_tab_rendering():
    from app.main import dashboard
    resp = dashboard()
    assert resp.status_code == 200
    html = resp.body.decode("utf-8")

    # Verify Tab 8 Navigation and Container
    assert 'id="tab-fim_engine"' in html
    assert 'id="view-fim_engine"' in html

    # Verify Controls & Inputs
    assert 'id="engine-file-input"' in html
    assert 'id="btn-engine-upload"' in html
    assert 'id="btn-engine-preset"' in html
    assert 'id="btn-engine-download-csv"' in html
    assert 'id="btn-engine-download-json"' in html
    assert 'id="btn-engine-download-pdf"' in html
    assert 'Research Report PDF' in html

    # Verify Summary Cards & Tables
    assert 'card-engine-total-records' in html
    assert 'card-engine-verified-flaky' in html
    assert 'card-engine-intermittent' in html
    assert 'card-engine-micro-recovery' in html
    assert 'table-verified-flaky-body' in html
    assert 'table-intermittent-body' in html
    assert 'upload_id' in html
    assert 'source_path' in html
