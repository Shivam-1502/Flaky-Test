import sqlite3
import json
import sys
import os

sys.path.insert(0, os.getcwd())
from app.metrics import suite_metrics, pipeline_metrics, systemic_metrics, environment_metrics, all_test_metrics

scenarios = {
    "A": ("data/comparison_scenario_a.db", "Scenario A — Recoverable intermittent"),
    "B": ("data/comparison_scenario_b.db", "Scenario B — Persistent intermittent"),
    "C": ("data/comparison_scenario_c.db", "Scenario C — Environment-concentrated"),
    "D": ("data/comparison_scenario_d.db", "Scenario D — Systemic shared failures"),
}

print("=" * 70)
print("COMPARATIVE EXPERIMENT MATHEMATICAL & SQL CROSS-VALIDATION AUDIT")
print("=" * 70)

for tag, (db_path, desc) in scenarios.items():
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # 1. Pipeline count
    sql_pipelines = cur.execute("SELECT COUNT(*) FROM pipelines").fetchone()[0]
    api_pipelines = pipeline_metrics(db_path=db_path)["pipelines"]
    assert sql_pipelines == 200 and api_pipelines == 200

    # 2. Base executions
    sql_base = cur.execute("SELECT COUNT(*) FROM test_executions WHERE is_rerun = 0").fetchone()[0]
    api_base = suite_metrics(db_path=db_path)["base_executions"]
    assert sql_base == 1200 and api_base == 1200

    # 3. Base failures
    sql_base_fails = cur.execute("SELECT COUNT(*) FROM test_executions WHERE is_rerun = 0 AND result = 'FAIL'").fetchone()[0]
    assert sql_base_fails == 40

    # 4. Suite base failure rate
    api_suite_fail_rate = suite_metrics(db_path=db_path)["overall_failure_rate"]
    assert abs(api_suite_fail_rate - (40 / 1200)) < 1e-9

    # 5. Reruns
    sql_reruns = cur.execute("SELECT COUNT(*) FROM test_executions WHERE is_rerun = 1").fetchone()[0]
    api_reruns = pipeline_metrics(db_path=db_path)["total_reruns"]
    assert sql_reruns == 40 and api_reruns == 40

    # 6. Total stored executions
    sql_total_execs = cur.execute("SELECT COUNT(*) FROM test_executions").fetchone()[0]
    api_total_execs = suite_metrics(db_path=db_path)["total_executions"]
    assert sql_total_execs == 1240 and api_total_execs == 1240

    # 7. Recovered reruns
    sql_recovered = cur.execute("SELECT COUNT(*) FROM test_executions WHERE is_rerun = 1 AND result = 'PASS'").fetchone()[0]
    api_recovered = pipeline_metrics(db_path=db_path)["recovered_failures"]
    assert sql_recovered == api_recovered

    # 8. Rerun duration
    sql_rerun_dur = cur.execute("SELECT SUM(duration_seconds) FROM test_executions WHERE is_rerun = 1").fetchone()[0]
    api_rerun_dur = pipeline_metrics(db_path=db_path)["rerun_overhead_seconds"]
    assert abs(sql_rerun_dur - api_rerun_dur) < 1e-9

    # 9. Parent run references
    missing_parent = cur.execute("SELECT COUNT(*) FROM test_executions WHERE is_rerun = 1 AND (parent_run_id IS NULL OR parent_run_id = '')").fetchone()[0]
    assert missing_parent == 0

    invalid_parent = cur.execute("""
        SELECT COUNT(*) FROM test_executions r
        WHERE r.is_rerun = 1 AND NOT EXISTS (
            SELECT 1 FROM test_executions b WHERE b.run_id = r.parent_run_id AND b.is_rerun = 0
        )
    """).fetchone()[0]
    assert invalid_parent == 0

    # 10. Duplicate run IDs
    dup_ids = cur.execute("SELECT COUNT(*) - COUNT(DISTINCT run_id) FROM test_executions").fetchone()[0]
    assert dup_ids == 0

    # 11. Failed pipelines
    sql_failed_pipes = cur.execute("SELECT COUNT(*) FROM pipelines WHERE result = 'FAIL'").fetchone()[0]
    api_failed_pipes = pipeline_metrics(db_path=db_path)["failed_pipelines"]
    assert sql_failed_pipes == api_failed_pipes

    # Specific Scenario Verifications
    if tag == "A":
        assert sql_recovered == 36, f"Expected 36 recovered in A, got {sql_recovered}"
        assert sql_failed_pipes == 40
    elif tag == "B":
        assert sql_recovered == 8, f"Expected 8 recovered in B, got {sql_recovered}"
        assert sql_failed_pipes == 40
    elif tag == "C":
        assert sql_recovered == 36
        assert sql_failed_pipes == 40
        # Verify Windows failure concentration
        win_fails = cur.execute("SELECT COUNT(*) FROM test_executions WHERE is_rerun = 0 AND environment = 'windows' AND result = 'FAIL'").fetchone()[0]
        other_fails = cur.execute("SELECT COUNT(*) FROM test_executions WHERE is_rerun = 0 AND environment != 'windows' AND result = 'FAIL'").fetchone()[0]
        assert win_fails == 40 and other_fails == 0
        t1_metrics = [m for m in all_test_metrics(db_path=db_path) if m["test_id"] == "test_1"][0]
        assert abs(t1_metrics["environment_sensitivity"] - 0.80) < 1e-9
    elif tag == "D":
        assert sql_recovered == 36
        assert sql_failed_pipes == 20, f"Expected 20 failed pipelines in D, got {sql_failed_pipes}"
        # Verify 2 distinct tests in 1 systemic cluster
        sys_m = systemic_metrics(db_path=db_path)
        assert sys_m["cluster_count"] == 1
        assert sys_m["systemic_cluster_count"] == 1
        assert sys_m["systemically_affected_flaky_tests"] == 2
        assert sys_m["systemic_flakiness_ratio"] == 1.0

    print(f"[{tag}] {desc}:")
    print(f"    Pipelines={sql_pipelines}, Failed Pipes={sql_failed_pipes} ({sql_failed_pipes/sql_pipelines*100:.1f}%)")
    print(f"    Base Execs={sql_base}, Base Fails={sql_base_fails} ({sql_base_fails/sql_base*100:.4f}%)")
    print(f"    Reruns={sql_reruns}, Recovered={sql_recovered} ({sql_recovered/sql_reruns*100:.1f}%)")
    print(f"    Rerun Overhead={api_rerun_dur:.6f}s")
    print(f"    SQL vs API: ALL CHECKS PASSED (100% MATCH)\n")

print("=" * 70)

