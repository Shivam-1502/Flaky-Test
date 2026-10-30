from collections import defaultdict
from statistics import mean, pstdev
from typing import Any

from .database import (
    fetch_all, fetch_base_executions, fetch_by_test, fetch_pipelines,
    fetch_rerun_executions
)

def _duration_cv(durations):
    if len(durations) < 2:
        return 0.0
    avg = mean(durations)
    return pstdev(durations) / avg if avg else 0.0

def is_recovered_flaky(base_row, reruns):
    for r in reruns:
        if (r["test_id"] == base_row["test_id"] and
            r["commit_id"] == base_row["commit_id"] and
            r["environment"] == base_row["environment"] and
            r["result"] == "PASS"):
            parent_id = r["parent_run_id"] if ("parent_run_id" in r.keys() if hasattr(r, "keys") else "parent_run_id" in r) else None
            if parent_id and parent_id != base_row["run_id"]:
                continue
            return True
    return False

def get_flaky_test_ids(base_rows, rerun_rows):
    flaky = set()
    for b in base_rows:
        if b["result"] == "FAIL":
            if is_recovered_flaky(b, rerun_rows):
                flaky.add(b["test_id"])
    return flaky

def _base_metrics_rows(test_id, db_path=None):
    if db_path is not None:
        return fetch_by_test(test_id, include_reruns=False, db_path=db_path)
    return fetch_by_test(test_id, include_reruns=False)

def compute_test_metrics(test_id: str, db_path=None) -> dict[str, Any]:
    rows = _base_metrics_rows(test_id, db_path=db_path)
    if db_path is not None:
        all_rows = fetch_by_test(test_id, include_reruns=True, db_path=db_path)
    else:
        all_rows = fetch_by_test(test_id, include_reruns=True)
    n = len(rows)

    if n == 0:
        return {
            "test_id": test_id,
            "executions": 0,
            "failures": 0,
            "failure_rate": 0.0,
            "mean_duration_seconds": 0.0,
            "duration_cv": 0.0,
            "outcome_transition_rate": 0.0,
            "environment_failure_rates": {},
            "environment_sensitivity": 0.0,
            "reruns": 0,
            "rerun_overhead_seconds": 0.0,
            "rerun_recovery_rate": 0.0,
            "failed_execution_time_seconds": 0.0,
            "failed_base_execution_time_seconds": 0.0,
            "failed_rerun_execution_time_seconds": 0.0,
            "total_failed_execution_time_seconds": 0.0,
        }

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
    failed_rerun_time = sum(
        r["duration_seconds"] for r in reruns if r["result"] == "FAIL"
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
        "failed_base_execution_time_seconds": failed_base_time,
        "failed_rerun_execution_time_seconds": failed_rerun_time,
        "total_failed_execution_time_seconds": failed_base_time + failed_rerun_time,
    }

def _fetch_base(db_path=None):
    return fetch_base_executions(db_path=db_path) if db_path is not None else fetch_base_executions()

def _fetch_rerun(db_path=None):
    return fetch_rerun_executions(db_path=db_path) if db_path is not None else fetch_rerun_executions()

def _fetch_pipes(db_path=None):
    return fetch_pipelines(db_path=db_path) if db_path is not None else fetch_pipelines()

def all_test_metrics(db_path=None):
    rows = _fetch_base(db_path=db_path)
    test_ids = sorted({r["test_id"] for r in rows})
    return [compute_test_metrics(t, db_path=db_path) for t in test_ids]

def _failure_clusters(db_path=None):
    rows = [
        r for r in _fetch_base(db_path=db_path)
        if r["result"] == "FAIL"
    ]
    clusters = defaultdict(list)
    for r in rows:
        signature = (r["error_type"], r["error_message"])
        clusters[signature].append(r["test_id"])
    return clusters

def systemic_metrics(db_path=None):
    clusters = _failure_clusters(db_path=db_path)
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
    rows = _fetch_base(db_path=db_path)
    reruns = _fetch_rerun(db_path=db_path)
    total_flaky = get_flaky_test_ids(rows, reruns)
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

def pipeline_metrics(db_path=None):
    rows = _fetch_pipes(db_path=db_path)
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
            r["duration_seconds"] for r in _fetch_rerun(db_path=db_path)
        ),
    }

def suite_metrics(db_path=None):
    rows = _fetch_base(db_path=db_path)
    reruns = _fetch_rerun(db_path=db_path)
    if not rows:
        return {
            "tests": 0, "total_executions": 0, "base_executions": 0, "rerun_executions": 0,
            "flaky_candidates": 0, "flaky_candidate_rate": 0.0, "overall_failure_rate": 0.0
        }

    metrics = all_test_metrics(db_path=db_path)
    flaky_test_ids = get_flaky_test_ids(rows, reruns)
    
    return {
        "tests": len(metrics),
        "total_executions": len(rows) + len(reruns),
        "base_executions": len(rows),
        "rerun_executions": len(reruns),
        "flaky_candidates": len(flaky_test_ids),
        "flaky_candidate_rate": len(flaky_test_ids) / len(metrics) if metrics else 0.0,
        "overall_failure_rate": sum(r["result"] == "FAIL" for r in rows) / len(rows) if rows else 0.0,
    }

def environment_metrics(db_path=None):
    rows = _fetch_base(db_path=db_path)
    reruns = _fetch_rerun(db_path=db_path)
    envs = defaultdict(lambda: {"executions": 0, "failures": 0, "flaky_tests": set()})
    
    for r in rows:
        env = r["environment"]
        envs[env]["executions"] += 1
        if r["result"] == "FAIL":
            envs[env]["failures"] += 1
            if is_recovered_flaky(r, reruns):
                envs[env]["flaky_tests"].add(r["test_id"])
                
    result = []
    rates = []
    for env in sorted(envs.keys()):
        data = envs[env]
        rate = data["failures"] / data["executions"] if data["executions"] else 0.0
        rates.append(rate)
        result.append({
            "environment": env,
            "executions": data["executions"],
            "base_executions": data["executions"],
            "failures": data["failures"],
            "failure_count": data["failures"],
            "failure_rate": rate,
            "flaky_test_count": len(data["flaky_tests"]),
            "flaky_candidates": len(data["flaky_tests"]),
        })
        
    sensitivity = max(rates) - min(rates) if len(rates) >= 2 else 0.0
    
    return {
        "environments": result,
        "overall_environment_sensitivity": sensitivity
    }
