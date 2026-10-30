from app.metrics import (
    _duration_cv,
    is_recovered_flaky,
    get_flaky_test_ids,
    compute_test_metrics,
    environment_metrics,
    pipeline_metrics,
    suite_metrics,
    systemic_metrics
)
from unittest.mock import patch

def test_duration_cv_zero_for_identical_values():
    assert _duration_cv([1.0, 1.0, 1.0]) == 0.0

def test_duration_cv_positive_for_variable_values():
    assert _duration_cv([1.0, 2.0, 3.0]) > 0

# Test a: PASS/FAIL across different environments must not automatically be flaky
def test_mixed_outcomes_different_environments_not_flaky():
    base_rows = [
        {"test_id": "test1", "commit_id": "c1", "environment": "env1", "result": "PASS", "run_id": "r1"},
        {"test_id": "test1", "commit_id": "c1", "environment": "env2", "result": "FAIL", "run_id": "r2"}
    ]
    rerun_rows = []
    assert get_flaky_test_ids(base_rows, rerun_rows) == set()

# Test b: PASS/FAIL across different commits must not automatically be flaky
def test_mixed_outcomes_different_commits_not_flaky():
    base_rows = [
        {"test_id": "test1", "commit_id": "c1", "environment": "env1", "result": "PASS", "run_id": "r1"},
        {"test_id": "test1", "commit_id": "c2", "environment": "env1", "result": "FAIL", "run_id": "r2"}
    ]
    rerun_rows = []
    assert get_flaky_test_ids(base_rows, rerun_rows) == set()

# Test c: FAIL base + PASS controlled rerun = flaky candidate
def test_fail_base_pass_rerun_is_flaky():
    base_rows = [
        {"test_id": "test1", "commit_id": "c1", "environment": "env1", "result": "FAIL", "run_id": "r1"}
    ]
    rerun_rows = [
        {"test_id": "test1", "commit_id": "c1", "environment": "env1", "result": "PASS", "run_id": "r2", "parent_run_id": "r1"}
    ]
    assert get_flaky_test_ids(base_rows, rerun_rows) == {"test1"}

# Test d: FAIL base + FAIL rerun = not recovered/flaky evidence
def test_fail_base_fail_rerun_not_flaky():
    base_rows = [
        {"test_id": "test1", "commit_id": "c1", "environment": "env1", "result": "FAIL", "run_id": "r1"}
    ]
    rerun_rows = [
        {"test_id": "test1", "commit_id": "c1", "environment": "env1", "result": "FAIL", "run_id": "r2", "parent_run_id": "r1"}
    ]
    assert get_flaky_test_ids(base_rows, rerun_rows) == set()

# Test e: environment sensitivity
@patch("app.metrics.fetch_base_executions")
@patch("app.metrics.fetch_rerun_executions")
def test_environment_sensitivity(mock_rerun, mock_base):
    mock_base.return_value = [
        {"test_id": "test1", "commit_id": "c1", "environment": "env1", "result": "FAIL"},
        {"test_id": "test1", "commit_id": "c1", "environment": "env2", "result": "PASS"}
    ]
    mock_rerun.return_value = []
    
    result = environment_metrics()
    assert result["overall_environment_sensitivity"] == 1.0

# Test f: rerun recovery rate
@patch("app.metrics.fetch_by_test")
def test_rerun_recovery_rate(mock_fetch_test):
    def side_effect(test_id, include_reruns=True):
        base_rows = [
            {"test_id": "t1", "commit_id": "c1", "environment": "env1", "result": "FAIL", "duration_seconds": 1.0, "run_id": "r1", "is_rerun": 0}
        ]
        all_rows = base_rows + [
            {"test_id": "t1", "commit_id": "c1", "environment": "env1", "result": "PASS", "duration_seconds": 2.0, "is_rerun": 1, "parent_run_id": "r1"}
        ]
        return all_rows if include_reruns else base_rows
        
    mock_fetch_test.side_effect = side_effect
    
    result = compute_test_metrics("t1")
    assert result["reruns"] == 1
    assert result["rerun_recovery_rate"] == 1.0

# Test g: empty test metric schema
@patch("app.metrics.fetch_by_test")
def test_empty_test_metric_schema(mock_fetch_test):
    mock_fetch_test.return_value = []
    result = compute_test_metrics("empty_test")
    
    expected_keys = {
        "test_id", "executions", "failures", "failure_rate", "mean_duration_seconds",
        "duration_cv", "outcome_transition_rate", "environment_failure_rates",
        "environment_sensitivity", "reruns", "rerun_overhead_seconds", "rerun_recovery_rate",
        "failed_execution_time_seconds",
        "failed_base_execution_time_seconds", "failed_rerun_execution_time_seconds",
        "total_failed_execution_time_seconds"
    }
    assert set(result.keys()) == expected_keys
    assert result["executions"] == 0

# Test h: failed base/rerun execution time
@patch("app.metrics.fetch_by_test")
def test_failed_execution_time(mock_fetch_test):
    def side_effect(test_id, include_reruns=True):
        base_rows = [
            {"test_id": "t1", "commit_id": "c1", "environment": "env1", "result": "FAIL", "duration_seconds": 3.0, "run_id": "r1", "is_rerun": 0}
        ]
        all_rows = base_rows + [
            {"test_id": "t1", "commit_id": "c1", "environment": "env1", "result": "FAIL", "duration_seconds": 2.0, "is_rerun": 1, "parent_run_id": "r1"}
        ]
        return all_rows if include_reruns else base_rows
        
    mock_fetch_test.side_effect = side_effect
    
    result = compute_test_metrics("t1")
    assert result["failed_execution_time_seconds"] == 3.0
    assert result["failed_base_execution_time_seconds"] == 3.0
    assert result["failed_rerun_execution_time_seconds"] == 2.0
    assert result["total_failed_execution_time_seconds"] == 5.0

# Test i: pipeline rerun overhead uses rerun executions, not pipeline durations
@patch("app.metrics.fetch_pipelines")
@patch("app.metrics.fetch_rerun_executions")
def test_pipeline_metrics_rerun_overhead(mock_rerun, mock_pipelines):
    mock_pipelines.return_value = [
        {"result": "FAIL", "duration_seconds": 45.0, "rerun_count": 2, "recovered_count": 1},
        {"result": "PASS", "duration_seconds": 30.0, "rerun_count": 0, "recovered_count": 0}
    ]
    mock_rerun.return_value = [
        {"duration_seconds": 1.25},
        {"duration_seconds": 0.75}
    ]
    res = pipeline_metrics()
    assert res["pipelines"] == 2
    assert res["failed_pipelines"] == 1
    assert res["pipeline_failure_rate"] == 0.5
    assert res["total_reruns"] == 2
    assert res["recovered_failures"] == 1
    # Must equal sum of rerun executions (1.25 + 0.75 = 2.0), NOT pipeline duration (45.0 + 30.0 = 75.0)
    assert res["rerun_overhead_seconds"] == 2.0

# Test j: systemic clustering counts distinct test IDs
@patch("app.metrics._failure_clusters")
@patch("app.metrics.fetch_base_executions")
@patch("app.metrics.fetch_rerun_executions")
def test_systemic_clustering_distinct_tests(mock_rerun, mock_base, mock_clusters):
    mock_clusters.return_value = {
        ("RuntimeError", "Shared resource"): ["test_a", "test_b", "test_a"],  # duplicate test_a failure
        ("RuntimeError", "Unique error"): ["test_c"]
    }
    mock_base.return_value = [
        {"test_id": "test_a", "commit_id": "c1", "environment": "env1", "result": "FAIL", "run_id": "r1"},
        {"test_id": "test_b", "commit_id": "c1", "environment": "env1", "result": "FAIL", "run_id": "r2"},
        {"test_id": "test_c", "commit_id": "c1", "environment": "env1", "result": "FAIL", "run_id": "r3"}
    ]
    mock_rerun.return_value = [
        {"test_id": "test_a", "commit_id": "c1", "environment": "env1", "result": "PASS", "run_id": "rr1", "parent_run_id": "r1"},
        {"test_id": "test_b", "commit_id": "c1", "environment": "env1", "result": "PASS", "run_id": "rr2", "parent_run_id": "r2"},
        {"test_id": "test_c", "commit_id": "c1", "environment": "env1", "result": "PASS", "run_id": "rr3", "parent_run_id": "r3"}
    ]
    res = systemic_metrics()
    assert res["cluster_count"] == 2
    assert res["systemic_cluster_count"] == 1
    assert res["failure_signature_clusters"]["RuntimeError::Shared resource"] == 2
    assert res["systemically_affected_flaky_tests"] == 2
    assert res["systemic_flakiness_ratio"] == 2 / 3

