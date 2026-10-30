"""
FIM - Controlled Comparative Experiment (Research Experiment 2)
Tests the central research hypothesis:
"Tests with comparable failure frequencies can have different quality impacts,
and multidimensional metrics can reveal those differences."

Executes four controlled scenarios (A, B, C, D) with identical base failure frequencies (3.3333%),
storing results in data/comparison_fim.db and scenario-specific databases.
"""

import argparse
import csv
import json
import os
import sys
import time
import uuid
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import (
    initialize_database, clear_database, insert_execution, insert_pipeline
)
from app.models import TestExecution
from app.metrics import (
    compute_test_metrics, all_test_metrics, suite_metrics,
    pipeline_metrics, systemic_metrics, environment_metrics
)

ENVIRONMENTS = ["local", "linux", "windows", "docker"]
TEST_SUITE = ["test_1", "test_2", "test_3", "test_4", "test_5", "test_6"]

DATA_DIR = PROJECT_ROOT / "data"
COMPARISON_DB_PATH = DATA_DIR / "comparison_fim.db"

SCENARIO_CONFIGS = {
    "scenario_a": {
        "name": "Scenario A — Recoverable intermittent failures",
        "description": "Flaky test with 40 base failures evenly distributed across environments and high rerun recovery (90%).",
        "db_path": DATA_DIR / "comparison_scenario_a.db",
        "error_type": "RuntimeError",
        "error_message": "Intermittent network timeout",
    },
    "scenario_b": {
        "name": "Scenario B — Persistent intermittent failures",
        "description": "Flaky test with 40 base failures evenly distributed across environments and low rerun recovery (20%).",
        "db_path": DATA_DIR / "comparison_scenario_b.db",
        "error_type": "RuntimeError",
        "error_message": "Persistent flaky resource exhaustion",
    },
    "scenario_c": {
        "name": "Scenario C — Environment-concentrated failures",
        "description": "Environment-sensitive test with 40 base failures concentrated exclusively in Windows (80% env failure rate).",
        "db_path": DATA_DIR / "comparison_scenario_c.db",
        "error_type": "RuntimeError",
        "error_message": "Windows OS path separator and registry permission error",
    },
    "scenario_d": {
        "name": "Scenario D — Systemic failures affecting multiple tests",
        "description": "Two tests failing simultaneously in 20 shared pipelines with identical failure signature.",
        "db_path": DATA_DIR / "comparison_scenario_d.db",
        "error_type": "RuntimeError",
        "error_message": "Shared database connection pool depleted",
    },
}

def build_scenario_schedules():
    """
    Constructs deterministic failure and rerun outcome schedules for 200 pipelines
    and 6 benchmark tests.
    """
    # 200 pipelines: 50 pipelines per environment
    env_pipelines = {env: [] for env in ENVIRONMENTS}
    for run_num in range(200):
        env = ENVIRONMENTS[run_num % len(ENVIRONMENTS)]
        env_pipelines[env].append(run_num)

    schedules = {}

    # ---------------------------------------------------------
    # Scenario A: 40 base failures (test_1), 10 per env. Reruns: 36 pass, 4 fail.
    # ---------------------------------------------------------
    scen_a_failures = set()
    scen_a_rerun_fails = set()
    for env in ENVIRONMENTS:
        # Every 5th pipeline in this environment (10 out of 50)
        selected = [env_pipelines[env][5 * k] for k in range(10)]
        for p in selected:
            scen_a_failures.add((p, "test_1"))
        # 1 rerun failure per environment (first of the 10)
        scen_a_rerun_fails.add((selected[0], "test_1"))

    schedules["scenario_a"] = {
        "base_failures": scen_a_failures,
        "rerun_failures": scen_a_rerun_fails,
    }

    # ---------------------------------------------------------
    # Scenario B: 40 base failures (test_1), 10 per env. Reruns: 8 pass, 32 fail.
    # ---------------------------------------------------------
    scen_b_failures = set()
    scen_b_rerun_passes = set()
    for env in ENVIRONMENTS:
        selected = [env_pipelines[env][5 * k] for k in range(10)]
        for p in selected:
            scen_b_failures.add((p, "test_1"))
        # 2 rerun passes per environment (first 2 of the 10) -> 8 pass total
        scen_b_rerun_passes.add((selected[0], "test_1"))
        scen_b_rerun_passes.add((selected[1], "test_1"))

    # Any failure not in rerun_passes is a rerun failure (32 total)
    scen_b_rerun_fails = scen_b_failures - scen_b_rerun_passes
    schedules["scenario_b"] = {
        "base_failures": scen_b_failures,
        "rerun_failures": scen_b_rerun_fails,
    }

    # ---------------------------------------------------------
    # Scenario C: 40 base failures (test_1), ALL 40 in Windows. Reruns: 36 pass, 4 fail.
    # ---------------------------------------------------------
    scen_c_failures = set()
    scen_c_rerun_fails = set()
    windows_pipes = env_pipelines["windows"]  # 50 pipelines
    selected_windows = windows_pipes[:40]     # first 40 pipelines
    for p in selected_windows:
        scen_c_failures.add((p, "test_1"))
    # Exactly 4 rerun failures in windows
    for p in selected_windows[:4]:
        scen_c_rerun_fails.add((p, "test_1"))

    schedules["scenario_c"] = {
        "base_failures": scen_c_failures,
        "rerun_failures": scen_c_rerun_fails,
    }

    # ---------------------------------------------------------
    # Scenario D: 2 tests (test_1, test_2) failing in SAME 20 pipelines (5 per env).
    # 40 base failures total (20 test_1 + 20 test_2). Reruns: 36 pass, 4 fail.
    # ---------------------------------------------------------
    scen_d_failures = set()
    scen_d_rerun_fails = set()
    scen_d_pipes = []
    for env in ENVIRONMENTS:
        # Every 10th pipeline in this environment (5 out of 50)
        selected = [env_pipelines[env][10 * k] for k in range(5)]
        scen_d_pipes.extend(selected)
        for p in selected:
            scen_d_failures.add((p, "test_1"))
            scen_d_failures.add((p, "test_2"))

    # Exactly 4 rerun failures total: 2 for test_1, 2 for test_2
    fail_p1 = scen_d_pipes[0]
    fail_p2 = scen_d_pipes[1]
    scen_d_rerun_fails.add((fail_p1, "test_1"))
    scen_d_rerun_fails.add((fail_p2, "test_1"))
    scen_d_rerun_fails.add((fail_p1, "test_2"))
    scen_d_rerun_fails.add((fail_p2, "test_2"))

    schedules["scenario_d"] = {
        "base_failures": scen_d_failures,
        "rerun_failures": scen_d_rerun_fails,
    }

    return schedules

def execute_scenario(scenario_key, config, schedule, num_runs=200):
    """
    Executes a controlled 200-pipeline scenario and writes to both its
    dedicated database and the shared comparison database.
    """
    db_paths = [config["db_path"], COMPARISON_DB_PATH]
    for db_p in db_paths:
        initialize_database(db_p)

    # Clear dedicated database
    clear_database(config["db_path"])

    base_failures_sched = schedule["base_failures"]
    rerun_failures_sched = schedule["rerun_failures"]

    total_base_execs = 0
    total_base_fails = 0
    total_reruns = 0
    total_recovered = 0

    print(f"\nRunning {config['name']} ({num_runs} pipelines)...")

    for run_number in range(num_runs):
        env = ENVIRONMENTS[run_number % len(ENVIRONMENTS)]
        pipeline_id = f"{scenario_key}-pipeline-{run_number + 1}"
        commit_id = f"synthetic-{run_number // 50 + 1}"

        pipeline_start = time.perf_counter()
        pipeline_base_failed = []

        # Execute 6 base tests
        for test_idx, test_id in enumerate(TEST_SUITE):
            is_failure = (run_number, test_id) in base_failures_sched

            test_start = time.perf_counter()
            # Small simulation workload: 0.0003s - 0.0007s
            time.sleep(0.0004 + (test_idx * 0.00005))
            duration = time.perf_counter() - test_start

            result = "FAIL" if is_failure else "PASS"
            error_type = config["error_type"] if is_failure else None
            error_message = config["error_message"] if is_failure else None
            stack_trace = (
                f"Traceback (most recent call last):\n"
                f"  File 'comparison/{test_id}.py', line 15, in run\n"
                f"{error_type}: {error_message}"
                if is_failure else None
            )

            run_id = str(uuid.uuid4())
            record = TestExecution(
                test_id=test_id,
                run_id=run_id,
                project_id=scenario_key,
                commit_id=commit_id,
                environment=env,
                pipeline_id=pipeline_id,
                result=result,
                duration_seconds=duration,
                error_type=error_type,
                error_message=error_message,
                stack_trace=stack_trace,
                is_rerun=False,
                parent_run_id=None,
            )

            for db_p in db_paths:
                insert_execution(record, db_path=db_p)

            total_base_execs += 1
            if is_failure:
                total_base_fails += 1
                pipeline_base_failed.append((test_id, run_id))

        # Controlled 1-rerun intervention per failed base test
        pipeline_recovered_count = 0
        for failed_test_id, parent_run_id in pipeline_base_failed:
            rerun_fails = (run_number, failed_test_id) in rerun_failures_sched

            rerun_start = time.perf_counter()
            time.sleep(0.0005)
            rerun_duration = time.perf_counter() - rerun_start

            rerun_result = "FAIL" if rerun_fails else "PASS"
            rerun_err_type = config["error_type"] if rerun_fails else None
            rerun_err_msg = config["error_message"] if rerun_fails else None
            rerun_stack = (
                f"Traceback (most recent call last):\n"
                f"  File 'comparison/{failed_test_id}.py', line 15, in rerun\n"
                f"{rerun_err_type}: {rerun_err_msg}"
                if rerun_fails else None
            )

            rerun_record = TestExecution(
                test_id=failed_test_id,
                run_id=str(uuid.uuid4()),
                project_id=scenario_key,
                commit_id=commit_id,
                environment=env,
                pipeline_id=pipeline_id,
                result=rerun_result,
                duration_seconds=rerun_duration,
                error_type=rerun_err_type,
                error_message=rerun_err_msg,
                stack_trace=rerun_stack,
                is_rerun=True,
                parent_run_id=parent_run_id,
            )

            for db_p in db_paths:
                insert_execution(rerun_record, db_path=db_p)

            total_reruns += 1
            if rerun_result == "PASS":
                pipeline_recovered_count += 1
                total_recovered += 1

        pipeline_result = "FAIL" if pipeline_base_failed else "PASS"
        pipeline_duration = time.perf_counter() - pipeline_start

        for db_p in db_paths:
            insert_pipeline(
                pipeline_id=pipeline_id,
                project_id=scenario_key,
                commit_id=commit_id,
                environment=env,
                result=pipeline_result,
                duration_seconds=pipeline_duration,
                base_failures=len(pipeline_base_failed),
                rerun_count=len(pipeline_base_failed),
                recovered_count=pipeline_recovered_count,
                db_path=db_p,
            )

    print(f"  Base Executions: {total_base_execs}")
    print(f"  Base Failures:   {total_base_fails}")
    print(f"  Rerun Executions:{total_reruns}")
    print(f"  Recovered Reruns:{total_recovered}")
    print(f"  Recovery Rate:   {total_recovered / total_reruns * 100:.1f}%")
    print(f"  Database:        {config['db_path']}")

def collect_scenario_metrics(scenario_key, config):
    """
    Computes all test, pipeline, systemic, suite, and environment metrics
    using the dedicated scenario database.
    """
    db_p = config["db_path"]
    suite = suite_metrics(db_path=db_p)
    pipes = pipeline_metrics(db_path=db_p)
    systemic = systemic_metrics(db_path=db_p)
    envs = environment_metrics(db_path=db_p)
    tests = all_test_metrics(db_path=db_p)

    return {
        "scenario_key": scenario_key,
        "name": config["name"],
        "description": config["description"],
        "suite": suite,
        "pipeline": pipes,
        "systemic": systemic,
        "environments": envs,
        "tests": tests,
    }

def main():
    parser = argparse.ArgumentParser(description="Run FIM Controlled Comparative Experiment (Experiment 2)")
    parser.add_argument("--runs", type=int, default=200, help="Number of pipelines per scenario (default: 200)")
    args = parser.parse_args()

    # Protect baseline: make sure comparison database path != baseline fim.db path
    assert COMPARISON_DB_PATH.name != "fim.db", "Comparison DB must not overwrite baseline fim.db!"

    # Initialize shared comparison DB
    initialize_database(COMPARISON_DB_PATH)
    clear_database(COMPARISON_DB_PATH)

    schedules = build_scenario_schedules()

    all_results = {}
    for scen_key, config in SCENARIO_CONFIGS.items():
        execute_scenario(scen_key, config, schedules[scen_key], num_runs=args.runs)
        metrics = collect_scenario_metrics(scen_key, config)
        all_results[scen_key] = metrics

    # Save machine-readable JSON
    json_path = DATA_DIR / "comparison_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved comparison JSON results to: {json_path}")

    # Generate Consolidated Summary CSV
    summary_csv_path = DATA_DIR / "comparison_summary.csv"
    with open(summary_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Scenario",
            "Description",
            "Pipelines",
            "Failed Pipelines",
            "Pipeline Failure Rate (%)",
            "Total Base Executions",
            "Total Base Failures",
            "Suite Base Failure Rate (%)",
            "Total Reruns",
            "Recovered Failures",
            "Rerun Recovery Rate (%)",
            "Rerun Overhead (s)",
            "Flaky Candidates",
            "Flaky Candidate Rate (%)",
            "Systemic Clusters",
            "Systemically Affected Tests",
            "Systemic Flakiness Ratio (%)",
            "Overall Env Sensitivity (%)"
        ])
        for key, res in all_results.items():
            s = res["suite"]
            p = res["pipeline"]
            sys_m = res["systemic"]
            e = res["environments"]
            writer.writerow([
                key.upper(),
                res["name"],
                p["pipelines"],
                p["failed_pipelines"],
                f"{p['pipeline_failure_rate'] * 100:.2f}",
                s["base_executions"],
                round(s["overall_failure_rate"] * s["base_executions"]),
                f"{s['overall_failure_rate'] * 100:.4f}",
                p["total_reruns"],
                p["recovered_failures"],
                f"{(p['recovered_failures'] / p['total_reruns'] * 100 if p['total_reruns'] else 0.0):.2f}",
                f"{p['rerun_overhead_seconds']:.6f}",
                s["flaky_candidates"],
                f"{s['flaky_candidate_rate'] * 100:.2f}",
                sys_m["systemic_cluster_count"],
                sys_m["systemically_affected_flaky_tests"],
                f"{sys_m['systemic_flakiness_ratio'] * 100:.2f}",
                f"{e['overall_environment_sensitivity'] * 100:.2f}"
            ])
    print(f"Saved summary CSV to: {summary_csv_path}")

    # Generate Detailed Test-Level Metrics CSV
    test_csv_path = DATA_DIR / "comparison_test_metrics.csv"
    with open(test_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Scenario",
            "Test ID",
            "Executions",
            "Failures",
            "Failure Rate (%)",
            "Mean Duration (s)",
            "Duration CV",
            "Outcome Transition Rate",
            "Reruns",
            "Recovery Rate (%)",
            "Rerun Overhead (s)",
            "Failed Base Time (s)",
            "Failed Rerun Time (s)",
            "Total Failed Time (s)",
            "Env Sensitivity (%)",
            "Env Rate Local (%)",
            "Env Rate Linux (%)",
            "Env Rate Windows (%)",
            "Env Rate Docker (%)"
        ])
        for key, res in all_results.items():
            for t in res["tests"]:
                e_rates = t["environment_failure_rates"]
                writer.writerow([
                    key.upper(),
                    t["test_id"],
                    t["executions"],
                    t["failures"],
                    f"{t['failure_rate'] * 100:.2f}",
                    f"{t['mean_duration_seconds']:.6f}",
                    f"{t['duration_cv']:.4f}",
                    f"{t['outcome_transition_rate']:.4f}",
                    t["reruns"],
                    f"{t['rerun_recovery_rate'] * 100:.2f}",
                    f"{t['rerun_overhead_seconds']:.6f}",
                    f"{t['failed_base_execution_time_seconds']:.6f}",
                    f"{t['failed_rerun_execution_time_seconds']:.6f}",
                    f"{t['total_failed_execution_time_seconds']:.6f}",
                    f"{t['environment_sensitivity'] * 100:.2f}",
                    f"{e_rates.get('local', 0.0) * 100:.2f}",
                    f"{e_rates.get('linux', 0.0) * 100:.2f}",
                    f"{e_rates.get('windows', 0.0) * 100:.2f}",
                    f"{e_rates.get('docker', 0.0) * 100:.2f}",
                ])
    print(f"Saved test metrics CSV to: {test_csv_path}")

if __name__ == "__main__":
    main()

