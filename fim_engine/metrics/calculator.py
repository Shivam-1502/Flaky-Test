"""
FIM Engine - SQA Metrics Calculator
Computes empirical test metrics, strictly separating literature-supported metrics
from FIM-proposed exploratory metrics.
"""

import json
from collections import Counter, defaultdict
from typing import List, Optional, Tuple, Dict, Any

from fim_engine.models import NormalizedExecution, MetricReport


class MetricCalculator:
    """
    Computes SQA metrics for a test case's execution history.
    """

    @staticmethod
    def extract_failure_signature(symptom_str: Optional[str]) -> Optional[str]:
        """
        Extract clean failure message from JSON symptom or raw string.
        """
        if not symptom_str:
            return None
        symptom_str = str(symptom_str).strip()
        if not symptom_str:
            return None

        # Check if JSON
        if symptom_str.startswith("{") and symptom_str.endswith("}"):
            try:
                data = json.loads(symptom_str)
                if isinstance(data, dict):
                    msg = data.get("message") or data.get("error") or data.get("stack")
                    if msg:
                        # Extract first meaningful line
                        clean = str(msg).strip().split("\n")[0]
                        # Remove ANSI color codes if present
                        import re
                        clean = re.sub(r'\x1b\[[0-9;]*m', '', clean)
                        return clean[:200]
            except Exception:
                pass

        # Raw string: clean first line
        first_line = symptom_str.split("\n")[0].strip()
        import re
        first_line = re.sub(r'\x1b\[[0-9;]*m', '', first_line)
        return first_line[:200] if first_line else None

    def compute_metrics(
        self,
        records: List[NormalizedExecution],
        classification_info: Dict[str, Any]
    ) -> Tuple[MetricReport, Optional[str]]:
        """
        Compute literature-supported and FIM-proposed metrics for a test case.

        Returns:
            Tuple of (MetricReport, primary_failure_signature)
        """
        # 1. Literature-supported: Mixed-Outcome Batch Frequency
        total_batches = classification_info.get("total_batches", 0)
        mixed_batches = classification_info.get("mixed_batch_count", 0)
        batch_freq = (mixed_batches / total_batches) if total_batches > 0 else 0.0

        # 2. Literature-supported: Retry Recovery Rate
        total_retried_failures = classification_info.get("total_retried_failures", 0)
        retry_recoveries = classification_info.get("retry_recoveries", 0)
        if total_retried_failures > 0:
            retry_recovery_rate: Optional[float] = retry_recoveries / total_retried_failures
        else:
            retry_recovery_rate = None

        # 3. Literature-supported: Failure Signature Diversity
        fail_records = [r for r in records if r.is_fail()]
        failure_signatures: List[str] = []
        for r in fail_records:
            sig = self.extract_failure_signature(r.failure_symptoms)
            if sig:
                failure_signatures.append(sig)

        unique_signatures = set(failure_signatures)
        failure_sig_diversity = len(unique_signatures)

        # Primary failure signature (most frequent)
        primary_signature: Optional[str] = None
        if failure_signatures:
            counter = Counter(failure_signatures)
            primary_signature = counter.most_common(1)[0][0]

        # 4. FIM-proposed: Pipeline Recurrence
        # Proportion of pipelines where test had at least 1 failure
        pipelines_with_runs: Dict[str, List[NormalizedExecution]] = defaultdict(list)
        for r in records:
            pipelines_with_runs[r.pipeline_id].append(r)

        total_pipelines = len(pipelines_with_runs)
        pipelines_with_failure = sum(
            1 for p_records in pipelines_with_runs.values() if any(r.is_fail() for r in p_records)
        )
        pipeline_recurrence = (pipelines_with_failure / total_pipelines) if total_pipelines > 0 else 0.0

        # 5. FIM-proposed: Environment Concentration
        # Max share of failures concentrated in a single environment
        env_failures: Dict[str, int] = defaultdict(int)
        for r in fail_records:
            env_failures[r.test_case_environment] += 1

        total_failures = len(fail_records)
        if total_failures > 0:
            max_env_fails = max(env_failures.values())
            env_concentration = max_env_fails / total_failures
        else:
            env_concentration = 0.0

        # 6. FIM-proposed: Rerun Overhead Seconds
        # Sum of duration spent on retry executions (retry_count > 0)
        retry_records = [r for r in records if r.is_retry()]
        has_valid_durations = any(r.duration is not None for r in retry_records)

        if retry_records and has_valid_durations:
            rerun_overhead: Optional[float] = sum(r.duration for r in retry_records if r.duration is not None)
        else:
            rerun_overhead = None

        metric_report = MetricReport(
            mixed_outcome_batch_frequency=batch_freq,
            retry_recovery_rate=retry_recovery_rate,
            failure_signature_diversity=failure_sig_diversity,
            pipeline_recurrence=pipeline_recurrence,
            environment_concentration=env_concentration,
            rerun_overhead_seconds=rerun_overhead,
        )

        return metric_report, primary_signature

