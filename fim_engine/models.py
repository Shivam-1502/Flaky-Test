"""
FIM Engine - Normalized Data Models and Type Definitions (Version 1.1)
Defines immutable data structures for test executions, classification results,
SQA metrics, and prioritization reports with sub-categorization and sequence anomaly tracking.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional


class TestClassification(str, Enum):
    __test__ = False
    FLAKY_CANDIDATE_IN_BATCH_VERIFIED = "Flaky candidate (In-batch retry verified)"
    INTERMITTENT_CANDIDATE_CROSS_PIPELINE = "Intermittent candidate (Cross-pipeline observational)"
    CONSISTENTLY_FAILING = "Consistently failing"
    CONSISTENTLY_PASSING = "Consistently passing"
    INSUFFICIENT_EVIDENCE = "Insufficient evidence"

    # Backward compatibility alias
    FLAKY_CANDIDATE = "Flaky candidate (In-batch retry verified)"

    @classmethod
    def is_candidate(cls, classification: str) -> bool:
        """Check if classification represents an active candidate (verified flaky or cross-pipeline intermittent)."""
        return classification in (
            cls.FLAKY_CANDIDATE_IN_BATCH_VERIFIED.value,
            cls.INTERMITTENT_CANDIDATE_CROSS_PIPELINE.value,
            "Flaky candidate",
        )

    @classmethod
    def is_verified_flaky(cls, classification: str) -> bool:
        """Check if classification has verified in-batch fail-to-pass retry evidence."""
        return classification in (
            cls.FLAKY_CANDIDATE_IN_BATCH_VERIFIED.value,
            "Flaky candidate",
        )


class EvidenceLevel(str, Enum):
    HIGH = "High evidence"
    MODERATE = "Moderate evidence"
    LOW = "Low evidence"


@dataclass(frozen=True)
class NormalizedExecution:
    """
    Standard normalized execution record across CSV, Parquet, JSON, and SQLite inputs.
    Preserves original metadata without partial-column deduplication.
    """
    test_case_name: str
    test_case_environment: str
    pipeline_id: str
    job_id: Optional[str] = None
    retry_count: int = 0
    status: str = "PASS"             # Normalized: "PASS" or "FAIL"
    original_result: str = ""        # Original: "passed", "failed", "timedOut", etc.
    duration: Optional[float] = None # Duration in seconds
    failure_symptoms: Optional[str] = None
    commit_id: Optional[str] = None
    source_file: Optional[str] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def is_pass(self) -> bool:
        return self.status == "PASS"

    def is_fail(self) -> bool:
        return self.status == "FAIL"

    def is_retry(self) -> bool:
        return self.retry_count > 0


@dataclass
class MetricReport:
    """
    Metrics computed for a single test case.
    Separates literature-supported metrics from FIM-proposed metrics.
    """
    # Literature-supported metrics
    mixed_outcome_batch_frequency: float  # Proportion of comparable batches with both PASS and FAIL
    retry_recovery_rate: Optional[float]  # Rate at which retried failures recover to PASS (per-test)
    failure_signature_diversity: int      # Count of distinct error messages / failure symptoms

    # FIM-proposed metrics
    pipeline_recurrence: float            # Proportion of pipelines containing at least 1 failure
    environment_concentration: float      # Max share of failures concentrated in a single environment
    rerun_overhead_seconds: Optional[float] # Sum of duration spent on retry attempts


@dataclass
class ImpactAnalysis:
    """
    Empirical CI impact analysis for a test case without speculative business claims.
    """
    total_pipelines_executed: int
    pipelines_with_failure: int
    pipeline_failure_rate: float
    total_retries_triggered: int
    retries_recovered_to_pass: int
    retries_unrecovered: int
    retry_recovery_percentage: Optional[float]
    environment_distribution: Dict[str, Dict[str, int]]  # env -> {executions, passes, failures}
    top_concentrated_environment: Optional[str]
    environment_concentration_ratio: float
    cumulative_retry_duration_seconds: Optional[float]
    cumulative_failed_duration_seconds: Optional[float]


@dataclass
class CandidateReport:
    """
    Consolidated analysis and prioritization report for a test case.
    """
    test_case_name: str
    classification: str
    evidence_level: str
    evidence_explanation: str
    total_executions: int
    total_passes: int
    total_failures: int
    empirical_failure_rate: float
    metrics: MetricReport
    impact: ImpactAnalysis
    priority_score: float
    score_breakdown: Dict[str, float]
    total_pipelines: int = 0
    sequence_anomalies_count: int = 0
    excluded_anomaly_recoveries: int = 0
    primary_failure_signature: Optional[str] = None
    tested_environments: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_case_name": self.test_case_name,
            "classification": self.classification,
            "evidence_level": self.evidence_level,
            "evidence_explanation": self.evidence_explanation,
            "total_executions": self.total_executions,
            "total_pipelines": self.total_pipelines,
            "total_passes": self.total_passes,
            "total_failures": self.total_failures,
            "empirical_failure_rate": round(self.empirical_failure_rate, 4),
            "priority_score": round(self.priority_score, 4),
            "score_breakdown": {k: round(v, 4) for k, v in self.score_breakdown.items()},
            "sequence_anomalies_count": self.sequence_anomalies_count,
            "excluded_anomaly_recoveries": self.excluded_anomaly_recoveries,
            "metrics": {
                "mixed_outcome_batch_frequency": round(self.metrics.mixed_outcome_batch_frequency, 4),
                "pipeline_recurrence": round(self.metrics.pipeline_recurrence, 4),
                "retry_recovery_rate": round(self.metrics.retry_recovery_rate, 4) if self.metrics.retry_recovery_rate is not None else None,
                "environment_concentration": round(self.metrics.environment_concentration, 4),
                "failure_signature_diversity": self.metrics.failure_signature_diversity,
                "rerun_overhead_seconds": round(self.metrics.rerun_overhead_seconds, 3) if self.metrics.rerun_overhead_seconds is not None else None,
            },
            "impact": {
                "total_pipelines_executed": self.impact.total_pipelines_executed,
                "pipelines_with_failure": self.impact.pipelines_with_failure,
                "pipeline_failure_rate": round(self.impact.pipeline_failure_rate, 4),
                "total_retries_triggered": self.impact.total_retries_triggered,
                "retries_recovered_to_pass": self.impact.retries_recovered_to_pass,
                "retries_unrecovered": self.impact.retries_unrecovered,
                "top_concentrated_environment": self.impact.top_concentrated_environment,
                "environment_concentration_ratio": round(self.impact.environment_concentration_ratio, 4),
                "cumulative_retry_duration_seconds": round(self.impact.cumulative_retry_duration_seconds, 3) if self.impact.cumulative_retry_duration_seconds is not None else None,
            },
            "primary_failure_signature": self.primary_failure_signature,
            "tested_environments": self.tested_environments,
        }
