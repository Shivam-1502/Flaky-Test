"""
FIM - Real-World Dataset Importer & Quality Metrics Engine
Imports the Home Assistant Empirical Quality Pilot from the real-world flaky-test-dataset.
Strictly isolates data into data/real_flaky.db and calculates empirical metrics without ML.
"""

import os
import json
import sqlite3
import re
import statistics
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REAL_DB_PATH = PROJECT_ROOT / "data" / "real_flaky.db"
WSL_DATASET_PATH = Path(r"\\wsl.localhost\Ubuntu\home\Lakshay\flaky-test-dataset")
LOCAL_DATASET_PATH = PROJECT_ROOT / "flaky-test-dataset"

# The verified 6 Home Assistant Pilot test cases
SELECTED_TEST_CASES = [
    {
        "test_id": "tests/components/assist_pipeline/test_init.py::test_pipeline_saved_audio_empty_queue",
        "source_file": "dev-new",
        "run_id": 27582828496,
        "classification": "VERIFIED_FLAKY_REPRODUCED",
        "notes": "Verified mixed outcome: 999 passes, 1 failure in 1000 repetitions. Isolated single-test process duration.",
    },
    {
        "test_id": "tests/components/concord232/test_alarm_control_panel.py::test_update_connection_error",
        "source_file": "dev-new",
        "run_id": 27531635653,
        "classification": "VERIFIED_FLAKY_REPRODUCED",
        "notes": "Verified mixed outcome: 998 passes, 2 failures in 1000 repetitions. Isolated single-test process duration.",
    },
    {
        "test_id": "tests/components/history/test_websocket_api.py::test_overflow_queue",
        "source_file": "dev",
        "run_id": 26516507327,
        "classification": "VERIFIED_FLAKY_REPRODUCED",
        "notes": "Verified mixed outcome: 69 passes, 1 failure in 70 pilot repetitions. No duration samples in dataset.",
    },
    {
        "test_id": "tests/components/switchbot/test_init.py::test_exception_handling_for_device_initialization",
        "source_file": "dev",
        "run_id": 26488153913,
        "classification": "VERIFIED_FLAKY_REPRODUCED",
        "notes": "Verified mixed outcome: 4 passes, 1 failure in 5 pilot repetitions. No duration samples in dataset.",
    },
    {
        "test_id": "tests/components/camera/test_img_util.py::test_turbojpeg_load_success",
        "source_file": "dev-new",
        "run_id": 27722050498,
        "classification": "DEFECTIVE_REPRO_CONTROL",
        "notes": "Consistently failing control: 0 passes, 1000 failures (deterministic libjpeg dependency defect).",
    },
    {
        "test_id": "tests/components/yoto/test_diagnostics.py::test_entry_diagnostics",
        "source_file": "dev-new",
        "run_id": 27784594858,
        "classification": "PASSING_REPRO_CONTROL",
        "notes": "Consistently passing control: 1000 passes, 0 failures on target branch reproduction commit.",
    },
]

SCHEMA = """
-- 1. Original CI workflow execution records (GitHub Actions PR builds)
-- Uses composite primary key (run_id, run_attempt) to preserve repeated attempts
CREATE TABLE IF NOT EXISTS ci_workflow_runs (
    run_id INTEGER NOT NULL,
    run_attempt INTEGER NOT NULL DEFAULT 1,
    project_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    pr_number INTEGER,
    pr_title TEXT,
    merge_sha TEXT,
    source_sha TEXT,
    target_sha TEXT,
    environment TEXT NOT NULL DEFAULT 'github-actions-linux',
    ci_status TEXT NOT NULL DEFAULT 'FAIL',
    failed_test_count INTEGER NOT NULL,
    PRIMARY KEY (run_id, run_attempt)
);

-- 2. Docker flakiness reproduction records (repeated runs on base commit)
CREATE TABLE IF NOT EXISTS docker_reproductions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    run_attempt INTEGER NOT NULL DEFAULT 1,
    test_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    tested_commit_sha TEXT NOT NULL,
    commit_type TEXT NOT NULL DEFAULT 'target_sha (base branch commit)',
    introduced_in_sha TEXT,
    introduction_date TEXT,
    environment TEXT NOT NULL DEFAULT 'docker-linux (python:3.13-bookworm)',
    passes INTEGER NOT NULL,
    failures INTEGER NOT NULL,
    total_runs INTEGER NOT NULL,
    empirical_failure_rate REAL NOT NULL,
    empirical_pass_rate REAL NOT NULL,
    is_isolated INTEGER NOT NULL DEFAULT 1,
    timing_sample_count INTEGER NOT NULL DEFAULT 0,
    mean_duration_seconds REAL,
    duration_stddev_seconds REAL,
    duration_cv REAL,
    min_duration_seconds REAL,
    max_duration_seconds REAL,
    error_type TEXT,
    error_message TEXT,
    failure_logs_sample TEXT,
    github_log_excerpt TEXT,
    evidence_strength TEXT NOT NULL,
    flakiness_classification TEXT NOT NULL,
    priority_level TEXT NOT NULL,
    priority_score REAL NOT NULL,
    priority_reason TEXT NOT NULL,
    UNIQUE(run_id, run_attempt, test_id),
    FOREIGN KEY(run_id, run_attempt) REFERENCES ci_workflow_runs(run_id, run_attempt)
);

CREATE INDEX IF NOT EXISTS idx_repro_test_id ON docker_reproductions(test_id);
CREATE INDEX IF NOT EXISTS idx_repro_run_key ON docker_reproductions(run_id, run_attempt);
"""

def extract_signature_from_trace(log_text: str) -> Tuple[str, str]:
    """
    Parses pytest error traceback to extract (error_type, error_message).
    Handles both multiline logs and inline/space-joined logs.
    """
    if not log_text:
        return ("None", "No failure log recorded (consistently passed)")
    
    # Check for StopIteration in coroutine
    if "coroutine raised StopIteration" in log_text or "StopIteration" in log_text:
        if "RuntimeError" in log_text:
            return ("RuntimeError", "coroutine raised StopIteration")
        return ("StopIteration", "coroutine raised StopIteration")

    # 1. Look for trailing pytest exception: e.g. "pipeline.py:1833: RuntimeError"
    m_end = re.findall(r":\s*([A-Za-z0-9_.]*(?:Error|Exception|StopIteration|AssertionError))\s*$", log_text)
    if m_end:
        err_type = m_end[-1]
        m_msg = re.findall(r"E\s+([A-Za-z0-9_.]*(?:Error|Exception|StopIteration|AssertionError))(?::\s*([^\n\r]+?))?(?:\s+[a-z0-9_/.]+\.py:\d+|homeassistant/|tests/|$)", log_text)
        if m_msg and m_msg[-1][1]:
            return (m_msg[-1][0], m_msg[-1][1].strip()[:200])
        if "assert " in log_text:
            m_ast = re.search(r"assert\s+([^\n\r]+?)(?:tests/|\.py:|$)", log_text)
            if m_ast:
                return (err_type, f"assert {m_ast.group(1).strip()[:180]}")
        return (err_type, "")

    # 2. Look for "E   <ErrorType>: <msg>" anywhere in text
    m_e = re.findall(r"E\s+([A-Za-z0-9_.]*(?:Error|Exception|StopIteration|AssertionError))(?::\s*([^\n\r]+?))?(?:\s+[a-z0-9_/.]+\.py:\d+|homeassistant/|tests/|$)", log_text)
    if m_e:
        return (m_e[-1][0], (m_e[-1][1] or "").strip()[:200])

    # 3. Look for "assert <expr>" or "AssertionError"
    if "assert " in log_text or "AssertionError" in log_text:
        m_assert = re.search(r"assert\s+([^\n\r]+?)(?:tests/|\.py:|$)", log_text)
        return ("AssertionError", f"assert {m_assert.group(1).strip()[:180]}" if m_assert else "Assertion failed")

    return ("PytestFailure", log_text[-120:].strip())

def get_evidence_label(total_runs: int, passes: int, failures: int) -> str:
    """
    Transparent evidence-strength labels without universal statistical claims.
    """
    if failures > 0 and passes > 0:
        if total_runs >= 1000:
            return "Repeated intermittent observation"
        elif total_runs >= 50:
            return "Preliminary intermittent candidate"
        else:
            return "Low-evidence intermittent candidate"
    elif passes == 0 and failures > 0:
        return "Consistently failing under reproduction conditions"
    elif failures == 0 and passes > 0:
        return "Consistently passing under reproduction conditions"
    return "Indeterminate observation"

def calculate_priority(
    evidence_label: str,
    failure_rate: float,
    total_runs: int
) -> Tuple[str, float, str]:
    """
    Transparent, rule-based prioritization model:
    - Tier 1 (P1 — HIGH EVIDENCE INTERMITTENT):
      Repeated intermittent observation (N >= 1,000 with mixed pass/fail).
      Score = 80.0 + (failure_rate * 1000.0) [e.g. 0.20% -> 82.00, 0.10% -> 81.00]
      Reason: Verified intermittent failure with high sample confidence on base commit.
    - Tier 2 (P2 — CANDIDATE INTERMITTENT):
      Intermittent candidate under preliminary (N=70) or low-evidence (N=5) trials.
      Score = 60.0 + (total_runs / 100.0) [e.g. N=70 -> 60.70, N=5 -> 60.05]
      Reason: Observed mixed outcomes require expanded trials to establish flakiness.
    - Tier 3 (P3 — REPRODUCTION DEFECT):
      Consistently failing under reproduction conditions (100% fail rate).
      Score = 40.00
      Reason: Deterministic environment/dependency defect (missing libjpeg-turbo); requires bug fix, not flaky quarantine.
    - Tier 4 (P4 — PASSING ON BASE):
      Consistently passing under reproduction conditions (100% pass rate).
      Score = 10.00
      Reason: 100% pass rate on base commit; CI failure was PR-specific or runner artifact.
    """
    if evidence_label == "Repeated intermittent observation":
        score = round(80.0 + (failure_rate * 1000.0), 2)
        reason = f"High-Evidence Intermittent: Repeated intermittent failure across {total_runs:,} trials on base commit (Failure Rate: {failure_rate*100:.2f}%)"
        return ("P1 — HIGH EVIDENCE INTERMITTENT", score, reason)
    elif evidence_label in ("Preliminary intermittent candidate", "Low-evidence intermittent candidate"):
        score = round(60.0 + (total_runs / 100.0), 2)
        reason = f"Candidate Intermittent: {evidence_label} ({total_runs} trials, Failure Rate: {failure_rate*100:.2f}%). Requires expanded trials."
        return ("P2 — CANDIDATE INTERMITTENT", score, reason)
    elif evidence_label == "Consistently failing under reproduction conditions":
        score = 40.00
        reason = f"Reproduction Defect: 100% failure rate across {total_runs:,} trials. Deterministic missing dependency defect; file bug ticket."
        return ("P3 — REPRODUCTION DEFECT", score, reason)
    else:  # Consistently passing
        score = 10.00
        reason = f"Passing on Base: 100% pass rate across {total_runs:,} trials on base commit. Failure was PR-introduced or CI runner artifact."
        return ("P4 — PASSING ON BASE", score, reason)

def locate_dataset_dir() -> Path:
    if WSL_DATASET_PATH.exists():
        return WSL_DATASET_PATH
    if LOCAL_DATASET_PATH.exists():
        return LOCAL_DATASET_PATH
    raw_path = PROJECT_ROOT / "data" / "real_raw"
    if raw_path.exists():
        return raw_path
    raise FileNotFoundError("Could not find flaky-test-dataset directory in WSL, local workspace, or data/real_raw.")

def init_database(db_path: Path = DEFAULT_REAL_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            DROP TABLE IF EXISTS docker_reproductions;
            DROP TABLE IF EXISTS ci_workflow_runs;
        """)
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()

def import_real_dataset(db_path: Path = DEFAULT_REAL_DB_PATH, dataset_base: Optional[Path] = None) -> Dict[str, Any]:
    """
    Imports the 6 selected Home Assistant test cases into data/real_flaky.db.
    Guarantees zero modifications to fim.db.
    """
    if dataset_base is None:
        dataset_base = locate_dataset_dir()

    init_database(db_path)

    # Locate the Home Assistant JSON files
    ha_dir = dataset_base / "data" / "home-assistant" / "core"
    dev_json_path = ha_dir / "dev.json"
    
    # Locate dev-new file (which may contain ':' or Unicode '\uF03A')
    dev_new_candidates = list(ha_dir.glob("dev-new*.json"))
    if not dev_new_candidates:
        raise FileNotFoundError(f"Could not find dev-new*.json in {ha_dir}")
    dev_new_json_path = dev_new_candidates[0]

    with open(dev_json_path, "r", encoding="utf-8") as f:
        dev_data = json.load(f)
    with open(dev_new_json_path, "r", encoding="utf-8") as f:
        dev_new_data = json.load(f)

    # Index by run_id
    dev_runs = {r["run_id"]: r for r in dev_data}
    dev_new_runs = {r["run_id"]: r for r in dev_new_data}

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    imported_tests = []
    seen_test_keys = set()

    try:
        cur.execute("DELETE FROM docker_reproductions")
        cur.execute("DELETE FROM ci_workflow_runs")

        for item in SELECTED_TEST_CASES:
            t_id = item["test_id"]
            r_id = item["run_id"]
            source = item["source_file"]
            classification = item["classification"]

            run_record = dev_new_runs.get(r_id) if source == "dev-new" else dev_runs.get(r_id)
            if not run_record:
                raise ValueError(f"Run ID {r_id} not found in {source} dataset!")

            run_attempt = run_record.get("run_attempt", 1)
            test_key = (r_id, run_attempt, t_id)
            if test_key in seen_test_keys:
                continue
            seen_test_keys.add(test_key)

            pr = run_record.get("pull_request", {})
            failed_tests = run_record.get("failed_tests", {})
            t_info = failed_tests.get(t_id)
            if not t_info:
                raise ValueError(f"Test {t_id} not found in run {r_id}!")

            # 1. Insert CI Workflow Run (composite key run_id, run_attempt)
            cur.execute("""
                INSERT OR REPLACE INTO ci_workflow_runs (
                    run_id, run_attempt, project_id, created_at,
                    pr_number, pr_title, merge_sha, source_sha, target_sha,
                    environment, ci_status, failed_test_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r_id,
                run_attempt,
                "home-assistant/core",
                run_record.get("created_at", ""),
                pr.get("number"),
                pr.get("title"),
                pr.get("merge_sha"),
                pr.get("source_sha"),
                pr.get("target_sha"),
                "github-actions-linux",
                "FAIL",
                len(failed_tests)
            ))

            # 2. Extract reproduction and timing metrics
            passes = t_info.get("passes", 0)
            failures = t_info.get("failures", 0)
            total_runs = passes + failures
            fail_rate = failures / total_runs if total_runs > 0 else 0.0
            pass_rate = passes / total_runs if total_runs > 0 else 0.0

            runtimes = t_info.get("run_time", [])
            is_isolated = (len(failed_tests) == 1)

            mean_dur = None
            sd_dur = None
            cv_dur = None
            min_dur = None
            max_dur = None

            # Only calculate duration statistics where timings are valid and isolated
            if runtimes and is_isolated:
                mean_dur = statistics.mean(runtimes)
                min_dur = min(runtimes)
                max_dur = max(runtimes)
                if len(runtimes) > 1:
                    sd_dur = statistics.pstdev(runtimes)
                    cv_dur = (sd_dur / mean_dur) if mean_dur else 0.0

            # 3. Parse failure signatures
            flogs = t_info.get("failure_logs", [])
            first_log = flogs[0] if flogs else ""
            err_type, err_msg = extract_signature_from_trace(first_log)

            gh_log = t_info.get("github_log", "")

            # 4. Evidence label & Rule-based Priority calculation
            evidence_label = get_evidence_label(total_runs, passes, failures)
            p_level, p_score, p_reason = calculate_priority(evidence_label, fail_rate, total_runs)

            # 5. Insert Docker Reproduction Record
            cur.execute("""
                INSERT INTO docker_reproductions (
                    run_id, run_attempt, test_id, project_id, tested_commit_sha, commit_type,
                    introduced_in_sha, introduction_date, environment,
                    passes, failures, total_runs, empirical_failure_rate, empirical_pass_rate,
                    is_isolated, timing_sample_count, mean_duration_seconds,
                    duration_stddev_seconds, duration_cv, min_duration_seconds, max_duration_seconds,
                    error_type, error_message, failure_logs_sample, github_log_excerpt,
                    evidence_strength, flakiness_classification, priority_level, priority_score, priority_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r_id,
                run_attempt,
                t_id,
                "home-assistant/core",
                pr.get("target_sha", ""),
                "target_sha (base branch commit)",
                t_info.get("introduced_in", ""),
                t_info.get("introduction_date", ""),
                "docker-linux (python:3.13-bookworm)",
                passes,
                failures,
                total_runs,
                fail_rate,
                pass_rate,
                1 if is_isolated else 0,
                len(runtimes) if is_isolated else 0,
                mean_dur,
                sd_dur,
                cv_dur,
                min_dur,
                max_dur,
                err_type,
                err_msg,
                first_log[:1500] if first_log else None,
                gh_log[:1500] if gh_log else None,
                evidence_label,
                classification,
                p_level,
                p_score,
                p_reason
            ))

            imported_tests.append({
                "test_id": t_id,
                "run_id": r_id,
                "run_attempt": run_attempt,
                "classification": classification,
                "evidence_strength": evidence_label,
                "passes": passes,
                "failures": failures,
                "total_runs": total_runs,
                "failure_rate": fail_rate,
                "mean_duration": mean_dur,
                "duration_cv": cv_dur,
                "error_type": err_type,
                "priority_level": p_level,
                "priority_score": p_score,
            })

        conn.commit()
    finally:
        conn.close()

    return {
        "status": "SUCCESS",
        "database": str(db_path),
        "imported_tests_count": len(imported_tests),
        "ci_workflow_runs_count": len(imported_tests),
        "tests": imported_tests
    }

def fetch_real_pilot_metrics(db_path: Path = DEFAULT_REAL_DB_PATH) -> Dict[str, Any]:
    """
    Fetches processed real-data pilot metrics for API and Dashboard presentation.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        runs = [dict(r) for r in cur.execute("SELECT * FROM ci_workflow_runs ORDER BY run_id, run_attempt").fetchall()]
        repros = [dict(r) for r in cur.execute("SELECT * FROM docker_reproductions ORDER BY priority_score DESC, total_runs DESC").fetchall()]
    finally:
        conn.close()

    mixed_outcome_count = sum(r["failures"] > 0 and r["passes"] > 0 for r in repros)
    total_repro_runs = sum(r["total_runs"] for r in repros)
    total_repro_failures = sum(r["failures"] for r in repros)

    return {
        "pilot_name": "Home Assistant Empirical Quality Pilot",
        "project": "home-assistant/core",
        "dataset_source": "test-flare/flaky-test-dataset (GitHub CI Mining + Docker Repetitions)",
        "summary": {
            "total_selected_tests": len(repros),
            "mixed_outcome_selected_tests": mixed_outcome_count,
            "mixed_outcome_proportion_selected": f"{mixed_outcome_count} / {len(repros)} ({mixed_outcome_count / len(repros) * 100:.1f}%)",
            "mixed_outcome_explanation": "Descriptive statistic for the six deliberately selected pilot test cases; not an estimate of overall Home Assistant flaky-test prevalence across the test suite.",
            "repeated_intermittent_observations": sum(r["evidence_strength"] == "Repeated intermittent observation" for r in repros),
            "preliminary_intermittent_candidates": sum(r["evidence_strength"] == "Preliminary intermittent candidate" for r in repros),
            "low_evidence_intermittent_candidates": sum(r["evidence_strength"] == "Low-evidence intermittent candidate" for r in repros),
            "consistently_failing_controls": sum(r["evidence_strength"] == "Consistently failing under reproduction conditions" for r in repros),
            "consistently_passing_controls": sum(r["evidence_strength"] == "Consistently passing under reproduction conditions" for r in repros),
            "total_docker_trials": total_repro_runs,
            "total_docker_failures": total_repro_failures,
            "ci_workflow_runs": len(runs),
            "environment_scope": "Monolithic Linux (GitHub Actions Linux runner & Docker python:3.13-bookworm)",
            "suite_failure_rate": "N/A (Sparse Failure Collection: complete passing test suite not mined)",
            "environment_sensitivity": "N/A (Single operating system represented)",
            "timing_provenance_note": "Timing measurements represent single-test Docker process wall-clock time (includes runner/framework initialization); multi-test or untimed runs are marked N/A.",
        },
        "tests": repros,
        "ci_runs": runs,
    }

if __name__ == "__main__":
    print(f"Importing Home Assistant Pilot into {DEFAULT_REAL_DB_PATH}...")
    res = import_real_dataset()
    print(json.dumps(res, indent=2))
