"""
FIM Engine - Test Classification Detector (Version 1.1)
Classifies test cases into distinct quality states based on empirical outcomes:
- FLAKY_CANDIDATE_IN_BATCH_VERIFIED: verified in-batch fail-to-pass retry evidence.
- INTERMITTENT_CANDIDATE_CROSS_PIPELINE: cross-pipeline variation without verified in-batch recovery.
- CONSISTENTLY_FAILING: deterministic failure across all runs.
- CONSISTENTLY_PASSING: deterministic pass across all runs.
- INSUFFICIENT_EVIDENCE: insufficient sample size.

Detects duplicate retry index anomalies (SEQUENCE_ANOMALY) and excludes them from verified recoveries.
"""

from typing import List, Dict, Any, Tuple
from collections import defaultdict

from fim_engine.models import NormalizedExecution, TestClassification, EvidenceLevel
from fim_engine.config import EngineConfig


class TestClassifier:
    """
    Evaluates execution records for test cases and assigns empirical classifications
    with sequence anomaly validation.
    """
    __test__ = False

    def __init__(self, config: EngineConfig = EngineConfig()):
        self.config = config

    def group_by_test(self, executions: List[NormalizedExecution]) -> Dict[str, List[NormalizedExecution]]:
        """Group normalized executions by test case name."""
        grouped: Dict[str, List[NormalizedExecution]] = defaultdict(list)
        for record in executions:
            grouped[record.test_case_name].append(record)
        return grouped

    def group_by_batches(
        self, test_executions: List[NormalizedExecution]
    ) -> Dict[Tuple[str, str, str], List[NormalizedExecution]]:
        """
        Group executions into comparable batches using (pipeline_id, job_id, environment).
        Within each batch, multiple runs represent in-pipeline retries/repetitions.
        """
        batches: Dict[Tuple[str, str, str], List[NormalizedExecution]] = defaultdict(list)
        for record in test_executions:
            key = (record.pipeline_id, record.job_id or "default_job", record.test_case_environment)
            batches[key].append(record)
        return batches

    def classify_test(
        self, test_name: str, records: List[NormalizedExecution]
    ) -> Dict[str, Any]:
        """
        Classify a single test case based on its execution history.
        Performs retry sequence anomaly validation to exclude corrupted duplicate retries.
        """
        total_executions = len(records)
        total_passes = sum(1 for r in records if r.is_pass())
        total_failures = sum(1 for r in records if r.is_fail())
        failure_rate = (total_failures / total_executions) if total_executions > 0 else 0.0

        batches = self.group_by_batches(records)
        total_batches = len(batches)
        mixed_batch_count = 0
        retry_recoveries = 0
        total_retried_failures = 0
        sequence_anomalies_count = 0
        excluded_anomaly_recoveries = 0

        # Unique pipelines
        pipelines = {r.pipeline_id for r in records}
        total_pipelines = len(pipelines)

        for batch_key, batch_records in batches.items():
            # Check for sequence anomaly: duplicate retry indices in the same job
            retries = [r.retry_count for r in batch_records]
            is_sequence_anomaly = len(retries) != len(set(retries))

            if is_sequence_anomaly:
                sequence_anomalies_count += 1
                has_initial_fail = any(r.is_fail() and r.retry_count == 0 for r in batch_records)
                has_retry_pass = any(r.is_pass() and r.retry_count > 0 for r in batch_records)
                if has_initial_fail and has_retry_pass:
                    excluded_anomaly_recoveries += 1
                # Do not count anomalous batch as verified fail-to-pass recovery
                continue

            passes = [r for r in batch_records if r.is_pass()]
            fails = [r for r in batch_records if r.is_fail()]

            if passes and fails:
                mixed_batch_count += 1

            # Check retry recovery
            # Initial failure (retry_count == 0) and any subsequent retry (retry_count > 0) passed
            has_initial_fail = any(r.is_fail() and r.retry_count == 0 for r in batch_records)
            has_retries = any(r.retry_count > 0 for r in batch_records)
            has_retry_pass = any(r.is_pass() and r.retry_count > 0 for r in batch_records)

            if has_initial_fail and has_retries:
                total_retried_failures += 1
                if has_retry_pass:
                    retry_recoveries += 1

        # Determine Classification
        if total_executions < self.config.min_executions_evidence:
            classification = TestClassification.INSUFFICIENT_EVIDENCE
            explanation = (
                f"Only {total_executions} execution(s) observed across {total_pipelines} pipeline(s) "
                f"(minimum required: {self.config.min_executions_evidence}). "
                f"Insufficient sample size to reliably determine flakiness."
            )
        elif retry_recoveries > 0:
            classification = TestClassification.FLAKY_CANDIDATE_IN_BATCH_VERIFIED
            anomaly_note = (
                f" ({excluded_anomaly_recoveries} sequence anomaly batch(es) excluded)"
                if excluded_anomaly_recoveries > 0
                else ""
            )
            explanation = (
                f"Observed {retry_recoveries} verified in-batch fail-to-pass retry recovery(ies) "
                f"and {mixed_batch_count} mixed-outcome batch(es) across {total_pipelines} pipeline(s){anomaly_note}."
            )
        elif total_failures == total_executions:
            classification = TestClassification.CONSISTENTLY_FAILING
            explanation = (
                f"Consistently failed in all {total_executions} observed executions "
                f"across {total_pipelines} pipeline(s) (failure rate: 100.0%)."
            )
        elif total_passes == total_executions:
            classification = TestClassification.CONSISTENTLY_PASSING
            explanation = (
                f"Consistently passed in all {total_executions} observed executions "
                f"across {total_pipelines} pipeline(s) (pass rate: 100.0%)."
            )
        else:
            # Pass/fail variation across pipelines without verified in-batch retry recoveries
            classification = TestClassification.INTERMITTENT_CANDIDATE_CROSS_PIPELINE
            anomaly_note = (
                f" (1 sequence anomaly batch excluded from verified recoveries)"
                if excluded_anomaly_recoveries > 0
                else ""
            )
            explanation = (
                f"Observed cross-pipeline intermittent outcomes ({total_passes} passes, "
                f"{total_failures} failures across {total_pipelines} pipelines) with no verified in-batch retry recoveries{anomaly_note}. "
                f"Observational candidate requiring commit-level inspection."
            )

        # Determine Evidence Level
        if total_executions >= self.config.high_evidence_executions or mixed_batch_count >= self.config.high_evidence_mixed_batches:
            evidence_level = EvidenceLevel.HIGH
        elif total_executions >= self.config.moderate_evidence_executions or mixed_batch_count >= self.config.moderate_evidence_mixed_batches:
            evidence_level = EvidenceLevel.MODERATE
        else:
            evidence_level = EvidenceLevel.LOW

        return {
            "test_case_name": test_name,
            "classification": classification.value,
            "evidence_level": evidence_level.value,
            "evidence_explanation": explanation,
            "total_executions": total_executions,
            "total_passes": total_passes,
            "total_failures": total_failures,
            "empirical_failure_rate": failure_rate,
            "mixed_batch_count": mixed_batch_count,
            "total_batches": total_batches,
            "retry_recoveries": retry_recoveries,
            "total_retried_failures": total_retried_failures,
            "total_pipelines": total_pipelines,
            "sequence_anomalies_count": sequence_anomalies_count,
            "excluded_anomaly_recoveries": excluded_anomaly_recoveries,
        }
