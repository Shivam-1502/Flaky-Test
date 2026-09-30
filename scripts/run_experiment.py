import argparse
import importlib
import os
import random
import time
import traceback
import uuid

from app.database import (
    initialize_database, clear_database, insert_execution, insert_pipeline
)
from app.models import TestExecution

BENCHMARKS = {
    "stable": "benchmark.tests.stable_test",
    "random_flaky": "benchmark.tests.random_flaky_test",
    "timing_flaky": "benchmark.tests.timing_flaky_test",
    "shared_state_flaky_a": "benchmark.tests.shared_state_flaky_a",
    "shared_state_flaky_b": "benchmark.tests.shared_state_flaky_b",
    "environment_flaky": "benchmark.tests.environment_flaky_test",
}

ENVIRONMENTS = ["local", "linux", "windows", "docker"]

def execute(test_id, module_name, run_number, environment,
            pipeline_id, is_rerun=False, parent_run_id=None):
    module = importlib.import_module(module_name)
    os.environ["FIM_ENVIRONMENT"] = environment

    start = time.perf_counter()
    result = "PASS"
    error_type = None
    error_message = None
    stack_trace = None

    try:
        if not module.run():
            # Shared-state tests deliberately use the same signature.
            if test_id.startswith("shared_state_flaky"):
                raise RuntimeError("Shared external resource unavailable")
            if test_id == "environment_flaky":
                raise RuntimeError("Environment-sensitive dependency failure")
            if test_id == "timing_flaky":
                raise RuntimeError("Timing threshold violated")
            raise RuntimeError("Random nondeterministic failure")
    except Exception as exc:
        result = "FAIL"
        error_type = type(exc).__name__
        error_message = str(exc)
        stack_trace = traceback.format_exc()

    duration = time.perf_counter() - start
    run_id = str(uuid.uuid4())

    insert_execution(TestExecution(
        test_id=test_id,
        run_id=run_id,
        project_id="fim-synthetic-benchmark",
        commit_id=f"synthetic-{run_number // 50 + 1}",
        environment=environment,
        pipeline_id=pipeline_id,
        result=result,
        duration_seconds=duration,
        error_type=error_type,
        error_message=error_message,
        stack_trace=stack_trace,
        is_rerun=is_rerun,
        parent_run_id=parent_run_id,
    ))
    return run_id, result, duration

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    initialize_database()
    if not args.keep:
        clear_database()

    random.seed(42)

    total_executions = 0
    total_reruns = 0

    for run_number in range(args.runs):
        environment = ENVIRONMENTS[run_number % len(ENVIRONMENTS)]
        pipeline_id = f"pipeline-{run_number + 1}"
        pipeline_start = time.perf_counter()

        base_results = []
        for test_id, module_name in BENCHMARKS.items():
            run_id, result, _ = execute(
                test_id, module_name, run_number, environment, pipeline_id
            )
            base_results.append((test_id, module_name, run_id, result))
            total_executions += 1

        failed = [x for x in base_results if x[3] == "FAIL"]
        recovered = 0

        # One controlled rerun per base failure.
        for test_id, module_name, parent_run_id, _ in failed:
            _, rerun_result, _ = execute(
                test_id, module_name, run_number, environment,
                pipeline_id, is_rerun=True, parent_run_id=parent_run_id
            )
            total_executions += 1
            total_reruns += 1
            if rerun_result == "PASS":
                recovered += 1

        pipeline_result = "PASS" if not failed else "FAIL"
        pipeline_duration = time.perf_counter() - pipeline_start

        insert_pipeline(
            pipeline_id=pipeline_id,
            project_id="fim-synthetic-benchmark",
            commit_id=f"synthetic-{run_number // 50 + 1}",
            environment=environment,
            result=pipeline_result,
            duration_seconds=pipeline_duration,
            base_failures=len(failed),
            rerun_count=len(failed),
            recovered_count=recovered,
        )

    print(f"Completed {args.runs} pipelines.")
    print(f"Base executions: {args.runs * len(BENCHMARKS)}")
    print(f"Rerun executions: {total_reruns}")
    print(f"Total stored executions: {total_executions}")
    print("Database: data/fim.db")

if __name__ == "__main__":
    main()
