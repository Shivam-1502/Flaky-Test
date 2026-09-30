from collections import defaultdict
from statistics import mean, pstdev
from typing import Any

from .database import (
    fetch_all, fetch_base_executions, fetch_by_test, fetch_pipelines
)

def _duration_cv(durations):
    if len(durations) < 2:
        return 0.0
    avg = mean(durations)
    return pstdev(durations) / avg if avg else 0.0

def _base_metrics_rows(test_id):
    return fetch_by_test(test_id, include_reruns=False)

def compute_test_metrics(test_id: str) -> dict[str, Any]:
    rows = _base_metrics_rows(test_id)
    all_rows = fetch_by_test(test_id, include_reruns=True)
    n = len(rows)

    if n == 0:
        return {"test_id": test_id, "executions": 0}

    failures = sum(row["result"] == "FAIL" for row in rows)
    durations = [row["duration_seconds"] for row in rows]

    transitions = sum(
        a["result"] != b["result"] for a, b in zip(rows, rows[1:])
    )

    environments = defaultdict(lambda: {"executions": 0, "failures": 0})
    for row in rows:
        e = environments[row["environment"]]
        e["executions"] += 1
        e["failures"] += row["result"] == "FAIL"

    env_rates = {
        env: x["failures"] / x["executions"]
        for env, x in environments.items()
    }
    rates = list(env_rates.values())

    reruns = [r for r in all_rows if r["is_rerun"]]
    recovered = 0
    for r in reruns:
        if r["result"] == "PASS":
            recovered += 1

    rerun_time = sum(r["duration_seconds"] for r in reruns)
    failed_base_time = sum(
        r["duration_seconds"] for r in rows if r["result"] == "FAIL"
    )

    return {
        "test_id": test_id,
        "executions": n,
        "failures": failures,
        "failure_rate": failures / n,
        "mean_duration_seconds": mean(durations),
        "duration_cv": _duration_cv(durations),
        "outcome_transition_rate": transitions / max(n - 1, 1),
        "environment_failure_rates": dict(env_rates),
        "environment_sensitivity": max(rates) - min(rates) if len(rates) >= 2 else 0.0,
        "reruns": len(reruns),
        "rerun_overhead_seconds": rerun_time,
        "rerun_recovery_rate": recovered / len(reruns) if reruns else 0.0,
        "failed_execution_time_seconds": failed_base_time,
    }

def all_test_metrics():
    rows = fetch_base_executions()
    test_ids = sorted({r["test_id"] for r in rows})
    return [compute_test_metrics(t) for t in test_ids]

def _failure_clusters():
    rows = [
        r for r in fetch_base_executions()
        if r["result"] == "FAIL"
    ]
    clusters = defaultdict(list)
    for r in rows:
        signature = (r["error_type"], r["error_message"])
        clusters[signature].append(r["test_id"])
    return clusters

def systemic_metrics():
    clusters = _failure_clusters()
    sizes = {
        f"{k[0]}::{k[1]}": len(set(v))
        for k, v in clusters.items()
    }
    clustered_tests = {
        test_id
        for tests in clusters.values()
        if len(set(tests)) >= 2
        for test_id in set(tests)
    }
    total_flaky = {
        m["test_id"] for m in all_test_metrics()
        if 0 < m["failures"] < m["executions"]
    }
    return {
        "failure_signature_clusters": sizes,
        "cluster_count": len(sizes),
        "systemic_cluster_count": sum(v >= 2 for v in sizes.values()),
        "systemically_affected_flaky_tests": len(clustered_tests & total_flaky),
        "systemic_flakiness_ratio": (
            len(clustered_tests & total_flaky) / len(total_flaky)
            if total_flaky else 0.0
        ),
    }

def pipeline_metrics():
    rows = fetch_pipelines()
    if not rows:
        return {
            "pipelines": 0, "failed_pipelines": 0,
            "pipeline_failure_rate": 0.0,
            "total_reruns": 0, "recovered_failures": 0,
            "rerun_overhead_seconds": 0.0,
        }

    return {
        "pipelines": len(rows),
        "failed_pipelines": sum(r["result"] == "FAIL" for r in rows),
        "pipeline_failure_rate": sum(r["result"] == "FAIL" for r in rows) / len(rows),
        "total_reruns": sum(r["rerun_count"] for r in rows),
        "recovered_failures": sum(r["recovered_count"] for r in rows),
        "rerun_overhead_seconds": sum(
            r["duration_seconds"] for r in rows
        ),
    }

def suite_metrics():
    rows = fetch_base_executions()
    if not rows:
        return {
            "tests": 0, "total_executions": 0, "flaky_candidates": 0,
            "flaky_candidate_rate": 0.0, "overall_failure_rate": 0.0
        }

    metrics = all_test_metrics()
    candidates = [
        x for x in metrics if 0 < x["failures"] < x["executions"]
    ]
    return {
        "tests": len(metrics),
        "total_executions": len(rows),
        "flaky_candidates": len(candidates),
        "flaky_candidate_rate": len(candidates) / len(metrics),
        "overall_failure_rate": sum(r["result"] == "FAIL" for r in rows) / len(rows),
    }
