"""
FIM Engine - Empirical Impact Analyzer
Measures CI-level impact (pipeline disruption, retry recovery, environment spread,
and time overhead) strictly based on observed execution data, without speculative business claims.
"""

from collections import defaultdict
from typing import List, Dict, Any, Optional

from fim_engine.models import NormalizedExecution, ImpactAnalysis


class ImpactAnalyzer:
    """
    Analyzes empirical CI impact of test executions.
    """

    def analyze(
        self,
        records: List[NormalizedExecution],
        classification_info: Dict[str, Any]
    ) -> ImpactAnalysis:
        """
        Compute empirical CI impact analysis for a test case.
        """
        # Pipelines
        pipelines_with_runs: Dict[str, List[NormalizedExecution]] = defaultdict(list)
        for r in records:
            pipelines_with_runs[r.pipeline_id].append(r)

        total_pipelines = len(pipelines_with_runs)
        pipelines_with_failure = sum(
            1 for p_records in pipelines_with_runs.values() if any(r.is_fail() for r in p_records)
        )
        pipeline_failure_rate = (pipelines_with_failure / total_pipelines) if total_pipelines > 0 else 0.0

        # Retries
        retry_records = [r for r in records if r.is_retry()]
        total_retries = len(retry_records)
        retries_recovered = classification_info.get("retry_recoveries", 0)
        retries_unrecovered = classification_info.get("total_retried_failures", 0) - retries_recovered
        if retries_unrecovered < 0:
            retries_unrecovered = 0

        retry_pct = (
            (retries_recovered / classification_info["total_retried_failures"] * 100.0)
            if classification_info.get("total_retried_failures", 0) > 0
            else None
        )

        # Environment distribution
        env_dist: Dict[str, Dict[str, int]] = defaultdict(lambda: {"executions": 0, "passes": 0, "failures": 0})
        for r in records:
            env_dist[r.test_case_environment]["executions"] += 1
            if r.is_pass():
                env_dist[r.test_case_environment]["passes"] += 1
            else:
                env_dist[r.test_case_environment]["failures"] += 1

        top_env: Optional[str] = None
        top_env_fails = 0
        total_fails = sum(1 for r in records if r.is_fail())

        for env, counts in env_dist.items():
            if counts["failures"] > top_env_fails:
                top_env_fails = counts["failures"]
                top_env = env

        env_ratio = (top_env_fails / total_fails) if total_fails > 0 else 0.0

        # Timing overhead
        has_durations = any(r.duration is not None for r in records)
        if has_durations:
            retry_dur = sum(r.duration for r in retry_records if r.duration is not None)
            failed_dur = sum(r.duration for r in records if r.is_fail() and r.duration is not None)
        else:
            retry_dur = None
            failed_dur = None

        return ImpactAnalysis(
            total_pipelines_executed=total_pipelines,
            pipelines_with_failure=pipelines_with_failure,
            pipeline_failure_rate=pipeline_failure_rate,
            total_retries_triggered=total_retries,
            retries_recovered_to_pass=retries_recovered,
            retries_unrecovered=retries_unrecovered,
            retry_recovery_percentage=retry_pct,
            environment_distribution=dict(env_dist),
            top_concentrated_environment=top_env,
            environment_concentration_ratio=env_ratio,
            cumulative_retry_duration_seconds=retry_dur,
            cumulative_failed_duration_seconds=failed_dur,
        )

