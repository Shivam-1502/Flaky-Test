import pytest
import sqlite3
import hashlib
from pathlib import Path
from scripts.import_real_dataset import (
    DEFAULT_REAL_DB_PATH, fetch_real_pilot_metrics,
    calculate_priority, extract_signature_from_trace,
    get_evidence_label
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
FIM_DB_PATH = DATA_DIR / "fim.db"
COMPARISON_DB_PATH = DATA_DIR / "comparison_fim.db"

def test_database_isolation():
    """Verify that existing synthetic databases are untouched and real DB is separate."""
    assert FIM_DB_PATH.exists(), "fim.db must exist"
    assert COMPARISON_DB_PATH.exists(), "comparison_fim.db must exist"
    assert DEFAULT_REAL_DB_PATH.exists(), "real_flaky.db must exist"

    # fim.db should be roughly 114KB (200 pipelines, 1393 executions)
    assert FIM_DB_PATH.stat().st_size > 100000

    # Ensure real_flaky.db is an entirely separate SQLite file
    assert DEFAULT_REAL_DB_PATH.resolve() != FIM_DB_PATH.resolve()
    assert DEFAULT_REAL_DB_PATH.resolve() != COMPARISON_DB_PATH.resolve()

def test_real_dataset_schema():
    """Verify table structures, composite primary keys, and record counts in data/real_flaky.db."""
    conn = sqlite3.connect(DEFAULT_REAL_DB_PATH)
    cur = conn.cursor()
    try:
        # Check tables
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "ci_workflow_runs" in tables
        assert "docker_reproductions" in tables

        # Verify CI runs count
        ci_runs = cur.execute("SELECT * FROM ci_workflow_runs").fetchall()
        assert len(ci_runs) == 6, f"Expected 6 CI workflow runs, got {len(ci_runs)}"

        # Verify Docker reproductions count
        repros = cur.execute("SELECT * FROM docker_reproductions").fetchall()
        assert len(repros) == 6, f"Expected 6 Docker reproductions, got {len(repros)}"

        # Verify composite foreign key reference (run_id, run_attempt)
        mismatched_runs = cur.execute("""
            SELECT r.id, r.run_id, r.run_attempt FROM docker_reproductions r
            LEFT JOIN ci_workflow_runs w ON r.run_id = w.run_id AND r.run_attempt = w.run_attempt
            WHERE w.run_id IS NULL
        """).fetchall()
        assert len(mismatched_runs) == 0, "All reproductions must link to a valid (run_id, run_attempt) in ci_workflow_runs"
    finally:
        conn.close()

def test_real_metrics_math_correctness():
    """Verify mathematical definitions of failure rate, pass rate, and total runs."""
    metrics_data = fetch_real_pilot_metrics(DEFAULT_REAL_DB_PATH)
    tests = metrics_data["tests"]
    assert len(tests) == 6

    for t in tests:
        p = t["passes"]
        f = t["failures"]
        total = t["total_runs"]
        assert total == p + f, f"total_runs must equal passes + failures for {t['test_id']}"
        assert total > 0

        expected_fail_rate = f / total
        expected_pass_rate = p / total
        assert pytest.approx(t["empirical_failure_rate"], rel=1e-5) == expected_fail_rate
        assert pytest.approx(t["empirical_pass_rate"], rel=1e-5) == expected_pass_rate
        assert pytest.approx(t["empirical_failure_rate"] + t["empirical_pass_rate"], rel=1e-5) == 1.0

def test_isolated_timing_metrics():
    """Verify that execution timings are isolated and statistics are calculated only where valid."""
    metrics_data = fetch_real_pilot_metrics(DEFAULT_REAL_DB_PATH)
    test_map = {t["test_id"]: t for t in metrics_data["tests"]}

    # assist_pipeline: 1000 isolated repetitions
    t1 = test_map["tests/components/assist_pipeline/test_init.py::test_pipeline_saved_audio_empty_queue"]
    assert t1["is_isolated"] == 1
    assert t1["timing_sample_count"] == 1000
    assert t1["mean_duration_seconds"] > 5.0
    assert t1["duration_stddev_seconds"] > 0.0
    assert 0.05 < t1["duration_cv"] < 0.15

    # concord232: 1000 isolated repetitions
    t2 = test_map["tests/components/concord232/test_alarm_control_panel.py::test_update_connection_error"]
    assert t2["is_isolated"] == 1
    assert t2["timing_sample_count"] == 1000
    assert t2["mean_duration_seconds"] > 3.9
    assert t2["duration_stddev_seconds"] > 0.0
    assert 0.05 < t2["duration_cv"] < 0.15

    # camera: 1000 isolated repetitions (defect control)
    t5 = test_map["tests/components/camera/test_img_util.py::test_turbojpeg_load_success"]
    assert t5["is_isolated"] == 1
    assert t5["timing_sample_count"] == 1000
    assert t5["mean_duration_seconds"] > 3.9

    # yoto: 1000 isolated repetitions (passing control)
    t6 = test_map["tests/components/yoto/test_diagnostics.py::test_entry_diagnostics"]
    assert t6["is_isolated"] == 1
    assert t6["timing_sample_count"] == 1000
    assert t6["mean_duration_seconds"] > 3.9

    # history & switchbot: pilot count only, no per-trial timing samples recorded in dataset
    t3 = test_map["tests/components/history/test_websocket_api.py::test_overflow_queue"]
    assert t3["timing_sample_count"] == 0
    assert t3["mean_duration_seconds"] is None
    assert t3["duration_cv"] is None

    t4 = test_map["tests/components/switchbot/test_init.py::test_exception_handling_for_device_initialization"]
    assert t4["timing_sample_count"] == 0
    assert t4["mean_duration_seconds"] is None
    assert t4["duration_cv"] is None

def test_priority_tier_classification():
    """Verify transparent rule-based priority assignment and evidence labels for all 6 tests."""
    metrics_data = fetch_real_pilot_metrics(DEFAULT_REAL_DB_PATH)
    test_map = {t["test_id"]: t for t in metrics_data["tests"]}

    # P1 - High Evidence Intermittent (1,000 trials with mixed outcomes)
    t1 = test_map["tests/components/assist_pipeline/test_init.py::test_pipeline_saved_audio_empty_queue"]
    assert t1["priority_level"] == "P1 — HIGH EVIDENCE INTERMITTENT"
    assert t1["priority_score"] == 81.00
    assert t1["evidence_strength"] == "Repeated intermittent observation"

    t2 = test_map["tests/components/concord232/test_alarm_control_panel.py::test_update_connection_error"]
    assert t2["priority_level"] == "P1 — HIGH EVIDENCE INTERMITTENT"
    assert t2["priority_score"] == 82.00
    assert t2["evidence_strength"] == "Repeated intermittent observation"

    # P2 - Candidate Intermittent (preliminary / low-evidence trials)
    t3 = test_map["tests/components/history/test_websocket_api.py::test_overflow_queue"]
    assert t3["priority_level"] == "P2 — CANDIDATE INTERMITTENT"
    assert t3["priority_score"] == 60.70
    assert t3["evidence_strength"] == "Preliminary intermittent candidate"

    t4 = test_map["tests/components/switchbot/test_init.py::test_exception_handling_for_device_initialization"]
    assert t4["priority_level"] == "P2 — CANDIDATE INTERMITTENT"
    assert t4["priority_score"] == 60.05
    assert t4["evidence_strength"] == "Low-evidence intermittent candidate"

    # P3 - Reproduction Defect (100% failure rate)
    t5 = test_map["tests/components/camera/test_img_util.py::test_turbojpeg_load_success"]
    assert t5["priority_level"] == "P3 — REPRODUCTION DEFECT"
    assert t5["priority_score"] == 40.00
    assert t5["evidence_strength"] == "Consistently failing under reproduction conditions"

    # P4 - Passing on Base (100% pass on base commit)
    t6 = test_map["tests/components/yoto/test_diagnostics.py::test_entry_diagnostics"]
    assert t6["priority_level"] == "P4 — PASSING ON BASE"
    assert t6["priority_score"] == 10.00
    assert t6["evidence_strength"] == "Consistently passing under reproduction conditions"

def test_mixed_outcome_proportion_and_disclaimer():
    """Verify that proportion of mixed outcomes is descriptive for selected tests and has explicit disclaimer."""
    metrics_data = fetch_real_pilot_metrics(DEFAULT_REAL_DB_PATH)
    summary = metrics_data["summary"]

    assert summary["mixed_outcome_selected_tests"] == 4
    assert summary["total_selected_tests"] == 6
    assert "4 / 6 (66.7%)" in summary["mixed_outcome_proportion_selected"]
    assert "not an estimate of overall Home Assistant flaky-test prevalence" in summary["mixed_outcome_explanation"]

def test_environment_and_commit_transparency():
    """Verify that environment constraints and tested commit details are accurately preserved."""
    metrics_data = fetch_real_pilot_metrics(DEFAULT_REAL_DB_PATH)
    summary = metrics_data["summary"]

    assert "Monolithic Linux" in summary["environment_scope"]
    assert "N/A" in summary["suite_failure_rate"]
    assert "N/A" in summary["environment_sensitivity"]

    for ci_run in metrics_data["ci_runs"]:
        assert ci_run["environment"] == "github-actions-linux"
        assert ci_run["target_sha"] is not None
        assert ci_run["merge_sha"] is not None
        assert ci_run["run_attempt"] >= 1

    for repro in metrics_data["tests"]:
        assert "docker-linux" in repro["environment"]
        assert repro["commit_type"] == "target_sha (base branch commit)"
        assert len(repro["tested_commit_sha"]) == 40  # Valid 40-char SHA
        assert repro["run_attempt"] >= 1

def test_failure_signature_extraction():
    """Verify traceback parser extracts accurate error types and messages."""
    metrics_data = fetch_real_pilot_metrics(DEFAULT_REAL_DB_PATH)
    test_map = {t["test_id"]: t for t in metrics_data["tests"]}

    # assist_pipeline raised StopIteration wrapped in RuntimeError
    t1 = test_map["tests/components/assist_pipeline/test_init.py::test_pipeline_saved_audio_empty_queue"]
    assert t1["error_type"] == "RuntimeError"
    assert "StopIteration" in t1["error_message"]

    # concord232 failed assertion on connection string
    t2 = test_map["tests/components/concord232/test_alarm_control_panel.py::test_update_connection_error"]
    assert t2["error_type"] == "AssertionError"

    # camera failed TurboJPEG assertion
    t5 = test_map["tests/components/camera/test_img_util.py::test_turbojpeg_load_success"]
    assert t5["error_type"] == "AssertionError"
    assert "TurboJPEG" in t5["error_message"]

    # yoto had 0 failures
    t6 = test_map["tests/components/yoto/test_diagnostics.py::test_entry_diagnostics"]
    assert t6["error_type"] == "None"
