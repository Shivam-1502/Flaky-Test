"""
Unit tests for the independent FIM Engine (fim_engine v1.1).
Tests classifications, evidence levels, sub-categorization, sequence anomaly validation,
metrics, evidence-stratified prioritization, adapters, and dual recovery reporting.
"""

import os
import json
import sqlite3
import tempfile
import pytest
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from fim_engine.models import (
    NormalizedExecution,
    TestClassification,
    EvidenceLevel,
    CandidateReport,
)
from fim_engine.config import EngineConfig
from fim_engine.detectors.classifier import TestClassifier
from fim_engine.metrics.calculator import MetricCalculator
from fim_engine.impact import ImpactAnalyzer
from fim_engine.prioritizer import Prioritizer
from fim_engine.reporting import ReportExporter
from fim_engine.ingestion import load_dataset
from fim_engine.ingestion.parquet_reader import ParquetReader
from fim_engine.ingestion.csv_reader import CSVReader
from fim_engine.ingestion.json_reader import JSONReader
from fim_engine.ingestion.sqlite_reader import SQLiteReader


# -------------------------------------------------------------------------
# Fixtures & Helpers
# -------------------------------------------------------------------------

def create_exec(
    name: str = "test_login",
    env: str = "linux-x64",
    pipeline: str = "p1",
    job: str = "j1",
    retry: int = 0,
    status: str = "PASS",
    duration: float = 1.5,
    symptoms: str = None,
) -> NormalizedExecution:
    return NormalizedExecution(
        test_case_name=name,
        test_case_environment=env,
        pipeline_id=pipeline,
        job_id=job,
        retry_count=retry,
        status=status,
        original_result="passed" if status == "PASS" else "failed",
        duration=duration,
        failure_symptoms=symptoms,
    )


# -------------------------------------------------------------------------
# 1. Classification & Sub-Categorization Tests
# -------------------------------------------------------------------------

def test_classify_consistently_passing():
    classifier = TestClassifier()
    records = [create_exec(pipeline=f"p{i}", status="PASS") for i in range(10)]
    result = classifier.classify_test("test_login", records)

    assert result["classification"] == TestClassification.CONSISTENTLY_PASSING.value
    assert result["total_executions"] == 10
    assert result["total_passes"] == 10
    assert result["total_failures"] == 0
    assert result["empirical_failure_rate"] == 0.0


def test_classify_consistently_failing():
    classifier = TestClassifier()
    records = [create_exec(pipeline=f"p{i}", status="FAIL", symptoms="AssertionError") for i in range(5)]
    result = classifier.classify_test("test_failing", records)

    assert result["classification"] == TestClassification.CONSISTENTLY_FAILING.value
    assert result["total_executions"] == 5
    assert result["total_failures"] == 5
    assert result["empirical_failure_rate"] == 1.0


def test_classify_insufficient_evidence():
    classifier = TestClassifier(config=EngineConfig(min_executions_evidence=3))
    records = [create_exec(pipeline="p1", status="FAIL")]
    result = classifier.classify_test("test_sparse", records)

    assert result["classification"] == TestClassification.INSUFFICIENT_EVIDENCE.value
    assert result["total_executions"] == 1
    assert "Insufficient sample size" in result["evidence_explanation"]


def test_classify_in_batch_retry_verified():
    classifier = TestClassifier()
    # Pipeline 1: attempt 0 fails, retry 1 passes (verified in-batch fail-to-pass)
    records = [
        create_exec(pipeline="p1", retry=0, status="FAIL", symptoms="Timeout"),
        create_exec(pipeline="p1", retry=1, status="PASS"),
        create_exec(pipeline="p2", retry=0, status="PASS"),
    ]
    result = classifier.classify_test("test_flaky_retry", records)

    assert result["classification"] == TestClassification.FLAKY_CANDIDATE_IN_BATCH_VERIFIED.value
    assert result["mixed_batch_count"] == 1
    assert result["retry_recoveries"] == 1
    assert result["total_retried_failures"] == 1
    assert "verified in-batch fail-to-pass" in result["evidence_explanation"]


def test_classify_cross_pipeline_intermittent():
    classifier = TestClassifier()
    # Runs across different pipelines without in-pipeline retries
    records = [
        create_exec(pipeline="p1", status="PASS"),
        create_exec(pipeline="p2", status="FAIL", symptoms="NetworkError"),
        create_exec(pipeline="p3", status="PASS"),
        create_exec(pipeline="p4", status="PASS"),
    ]
    result = classifier.classify_test("test_intermittent", records)

    assert result["classification"] == TestClassification.INTERMITTENT_CANDIDATE_CROSS_PIPELINE.value
    assert result["total_executions"] == 4
    assert result["total_failures"] == 1
    assert "no verified in-batch retry recoveries" in result["evidence_explanation"]


# -------------------------------------------------------------------------
# 2. Sequence Anomaly Validation (Pipeline 10189692513 reproduction)
# -------------------------------------------------------------------------

def test_sequence_anomaly_duplicate_retries():
    classifier = TestClassifier()
    # Batch with duplicate retry indices: [0, 0, 1, 1] as seen in pipeline 10189692513
    records = [
        create_exec(pipeline="10189692513", job="28188194339", retry=0, status="FAIL", symptoms="PopupError"),
        create_exec(pipeline="10189692513", job="28188194339", retry=0, status="FAIL", symptoms="PopupError"),
        create_exec(pipeline="10189692513", job="28188194339", retry=1, status="PASS"),
        create_exec(pipeline="10189692513", job="28188194339", retry=1, status="PASS"),
        create_exec(pipeline="p2", job="j2", retry=0, status="PASS"),
    ]
    result = classifier.classify_test("test_anomalous_batch", records)

    # Anomaly detected and excluded from verified recoveries
    assert result["sequence_anomalies_count"] == 1
    assert result["excluded_anomaly_recoveries"] == 1
    assert result["retry_recoveries"] == 0
    # Because there are no valid in-batch recoveries, classified as cross-pipeline intermittent
    assert result["classification"] == TestClassification.INTERMITTENT_CANDIDATE_CROSS_PIPELINE.value
    assert "sequence anomaly batch excluded" in result["evidence_explanation"]


# -------------------------------------------------------------------------
# 3. Evidence Levels & Evidence-Stratified Ranking Tests
# -------------------------------------------------------------------------

def test_evidence_levels():
    classifier = TestClassifier(
        EngineConfig(high_evidence_executions=100, moderate_evidence_executions=20)
    )

    # Low evidence (< 20 runs, no mixed batches)
    records_low = [create_exec(pipeline=f"p{i}", status="PASS") for i in range(10)]
    res_low = classifier.classify_test("test_low", records_low)
    assert res_low["evidence_level"] == EvidenceLevel.LOW.value

    # Moderate evidence (25 runs)
    records_mod = [create_exec(pipeline=f"p{i}", status="PASS") for i in range(25)]
    res_mod = classifier.classify_test("test_mod", records_mod)
    assert res_mod["evidence_level"] == EvidenceLevel.MODERATE.value

    # High evidence (105 runs)
    records_high = [create_exec(pipeline=f"p{i}", status="PASS") for i in range(105)]
    res_high = classifier.classify_test("test_high", records_high)
    assert res_high["evidence_level"] == EvidenceLevel.HIGH.value


def test_evidence_stratified_ranking_low_sample_penalty():
    prioritizer = Prioritizer()

    # Candidate A: High Evidence, verified in-batch flakiness (105 executions, score 0.25)
    records_a = []
    for i in range(105):
        if i < 20:
            records_a.append(create_exec("test_systemic_high", pipeline=f"p{i}", retry=0, status="FAIL"))
            records_a.append(create_exec("test_systemic_high", pipeline=f"p{i}", retry=1, status="PASS"))
        else:
            records_a.append(create_exec("test_systemic_high", pipeline=f"p{i}", retry=0, status="PASS"))

    # Candidate B: Low Evidence, small sample (12 executions, score 0.30 due to 1/2 pipelines failing)
    records_b = [
        create_exec("test_low_sample", pipeline="p1", retry=0, status="FAIL"),
        create_exec("test_low_sample", pipeline="p2", retry=0, status="PASS"),
    ] + [create_exec("test_low_sample", pipeline="p2", retry=0, status="PASS") for _ in range(10)]

    all_records = records_a + records_b
    ranked = prioritizer.prioritize_all(all_records)

    # Candidate A (High Evidence, Verified) must outrank Candidate B (Low Evidence),
    # preventing low-sample tests from inflating to the top.
    assert ranked[0].test_case_name == "test_systemic_high"
    assert ranked[0].evidence_level == EvidenceLevel.HIGH.value
    assert ranked[1].test_case_name == "test_low_sample"
    assert ranked[1].evidence_level == EvidenceLevel.LOW.value


# -------------------------------------------------------------------------
# 4. SQA Metrics Tests
# -------------------------------------------------------------------------

def test_metrics_literature_and_fim():
    classifier = TestClassifier()
    calculator = MetricCalculator()

    records = [
        create_exec(pipeline="p1", env="linux", retry=0, status="FAIL", duration=2.0, symptoms="SocketTimeout"),
        create_exec(pipeline="p1", env="linux", retry=1, status="PASS", duration=1.0),
        create_exec(pipeline="p2", env="win", retry=0, status="FAIL", duration=2.5, symptoms="NoSuchElement"),
        create_exec(pipeline="p2", env="win", retry=1, status="FAIL", duration=2.5, symptoms="NoSuchElement"),
        create_exec(pipeline="p3", env="linux", retry=0, status="PASS", duration=1.2),
        create_exec(pipeline="p4", env="mac", retry=0, status="PASS", duration=1.1),
    ]

    classif = classifier.classify_test("test_complex", records)
    metrics, primary_sig = calculator.compute_metrics(records, classif)

    assert metrics.mixed_outcome_batch_frequency == pytest.approx(1 / 4, rel=1e-3)
    assert metrics.retry_recovery_rate == pytest.approx(0.50, rel=1e-3)
    assert metrics.failure_signature_diversity == 2
    assert primary_sig in ("NoSuchElement", "SocketTimeout")
    assert metrics.pipeline_recurrence == pytest.approx(0.50, rel=1e-3)
    assert metrics.environment_concentration == pytest.approx(2 / 3, rel=1e-3)
    assert metrics.rerun_overhead_seconds == pytest.approx(3.5, rel=1e-3)


# -------------------------------------------------------------------------
# 5. Dual Recovery Reporting (Macro vs Micro Average)
# -------------------------------------------------------------------------

def test_dual_recovery_rate_reporting():
    with tempfile.TemporaryDirectory() as out_dir:
        prioritizer = Prioritizer()
        # Test 1: 3 executions, 1 retry, 1 recovery (rate = 1.0)
        rec1 = [
            create_exec("t1", pipeline="p1", retry=0, status="FAIL"),
            create_exec("t1", pipeline="p1", retry=1, status="PASS"),
            create_exec("t1", pipeline="p2", retry=0, status="PASS"),
        ]
        # Test 2: 10 executions (9 retried failures that failed, plus 1 pass in p10) -> (rate = 0.0)
        rec2 = [create_exec("t2", pipeline="p10", retry=0, status="PASS")]
        for i in range(9):
            rec2.append(create_exec("t2", pipeline=f"p{i}", retry=0, status="FAIL"))
            rec2.append(create_exec("t2", pipeline=f"p{i}", retry=1, status="FAIL"))

        candidates = prioritizer.prioritize_all(rec1 + rec2)
        exporter = ReportExporter()
        paths = exporter.export(candidates, out_dir, "synthetic", len(rec1 + rec2))

        with open(paths["summary"], "r", encoding="utf-8") as f:
            summary = json.load(f)

        lit = summary["flaky_metrics_aggregates"]["literature_supported"]
        # Macro-average = (1.0 + 0.0) / 2 = 0.50
        assert lit["macro_average_retry_recovery_rate"] == 0.50
        # Pooled Micro-average = 1 recovery / 10 retried failures = 0.10
        assert lit["pooled_micro_average_retry_recovery_rate"] == 0.10


# -------------------------------------------------------------------------
# 6. Ingestion Adapters Tests (CSV, JSON, SQLite, Parquet)
# -------------------------------------------------------------------------

def test_csv_reader():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write("test_case_name,test_case_environment,pipeline_id,retry_count,result,duration,failure_symptoms\n")
        f.write("test_alpha,linux,p100,0,passed,1.25,\n")
        f.write("test_beta,windows,p101,1,failed,0.85,NullReferenceException\n")
        csv_file = f.name

    try:
        reader = CSVReader()
        records = reader.read(csv_file)
        assert len(records) == 2
        assert records[0].test_case_name == "test_alpha"
        assert records[0].status == "PASS"
        assert records[1].test_case_name == "test_beta"
        assert records[1].status == "FAIL"
    finally:
        os.remove(csv_file)


def test_json_reader():
    data = [
        {"test_name": "test_j1", "environment": "docker", "run_id": "r1", "status": "PASS", "duration_ms": 1500},
        {"test_name": "test_j2", "environment": "docker", "run_id": "r2", "status": "FAIL", "error_message": "Err"},
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        json_file = f.name

    try:
        reader = JSONReader()
        records = reader.read(json_file)
        assert len(records) == 2
        assert records[0].test_case_name == "test_j1"
        assert records[0].status == "PASS"
        assert records[1].test_case_name == "test_j2"
        assert records[1].status == "FAIL"
    finally:
        os.remove(json_file)


def test_sqlite_reader():
    with tempfile.NamedTemporaryFile("w", suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE test_executions (
                id INTEGER PRIMARY KEY,
                test_name TEXT,
                environment TEXT,
                run_id TEXT,
                status TEXT,
                duration_ms REAL,
                is_rerun INTEGER,
                error_message TEXT
            )
        """)
        cursor.execute("INSERT INTO test_executions VALUES (1, 't_sql_1', 'env1', 'runA', 'PASS', 2000, 0, NULL)")
        cursor.execute("INSERT INTO test_executions VALUES (2, 't_sql_2', 'env2', 'runB', 'FAIL', 3000, 1, 'Boom')")
        conn.commit()
        conn.close()

        reader = SQLiteReader(table_name="test_executions")
        records = reader.read(db_path)
        assert len(records) == 2
        assert records[0].test_case_name == "t_sql_1"
        assert records[0].status == "PASS"
        assert records[1].test_case_name == "t_sql_2"
        assert records[1].retry_count == 1
    finally:
        os.remove(db_path)


def test_parquet_reader():
    df = pd.DataFrame({
        "test_case_name": ["test_pw_1", "test_pw_2"],
        "test_case_environment": ["linux", "linux"],
        "pipeline_id": ["pipe1", "pipe1"],
        "job_id": ["j1", "j1"],
        "retry_count": [0, 1],
        "duration": [1.1, 2.2],
        "result": ["failed", "passed"],
        "generic_result": ["fail-like", "pass-like"],
        "failure_symptoms": ['{"message": "Timeout"}', None],
        "pipeline_commit_sha": ["abc1234", "abc1234"],
    })

    with tempfile.NamedTemporaryFile("wb", suffix=".parquet", delete=False) as f:
        parquet_file = f.name

    try:
        table = pa.Table.from_pandas(df)
        pq.write_table(table, parquet_file)

        reader = ParquetReader()
        records = reader.read(parquet_file)
        assert len(records) == 2
        assert records[0].test_case_name == "test_pw_1"
        assert records[0].status == "FAIL"
        assert records[1].status == "PASS"
        assert records[1].retry_count == 1
    finally:
        os.remove(parquet_file)
