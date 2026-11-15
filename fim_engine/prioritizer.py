"""
FIM Engine - Test Prioritization Engine (Version 1.1)
Ranks flaky and intermittent candidates using an evidence-stratified ranking architecture:
High Evidence -> Moderate Evidence -> Low Evidence, ordered by priority score within each tier.

Baseline formula:
Priority = w_recurrence * Pipeline Recurrence + w_batch * Mixed Batch Frequency

Provides explicit score breakdowns, confidence level explanations, and exploratory disclaimers.
"""

from typing import List, Dict, Any, Optional

from fim_engine.models import (
    CandidateReport,
    NormalizedExecution,
    TestClassification,
    EvidenceLevel,
    MetricReport,
    ImpactAnalysis,
)
from fim_engine.config import EngineConfig
from fim_engine.detectors.classifier import TestClassifier
from fim_engine.metrics.calculator import MetricCalculator
from fim_engine.impact import ImpactAnalyzer


class Prioritizer:
    """
    Ranks flaky and intermittent candidates using evidence-stratified ordering.
    """

    EXPLORATORY_DISCLAIMER = (
        "Exploratory Baseline Metric: Priority scores are experimental weighted heuristics "
        "combining Pipeline Recurrence (60%) and Mixed-Outcome Batch Frequency (40%) to order "
        "investigation effort. They represent empirical operational signals rather than "
        "deterministic truth. Evidence level indicates statistical sample confidence, not definitive flakiness."
    )

    EVIDENCE_RANK = {
        EvidenceLevel.HIGH.value: 3,
        EvidenceLevel.MODERATE.value: 2,
        EvidenceLevel.LOW.value: 1,
    }

    def __init__(self, config: EngineConfig = EngineConfig()):
        self.config = config
        self.classifier = TestClassifier(config=config)
        self.metric_calculator = MetricCalculator()
        self.impact_analyzer = ImpactAnalyzer()

    def analyze_test(
        self,
        test_name: str,
        records: List[NormalizedExecution]
    ) -> CandidateReport:
        """
        Perform complete classification, metric calculation, impact analysis,
        and prioritization scoring for a single test case.
        """
        # 1. Classification
        classification_info = self.classifier.classify_test(test_name, records)

        # 2. Metrics
        metrics, primary_sig = self.metric_calculator.compute_metrics(records, classification_info)

        # 3. Impact
        impact = self.impact_analyzer.analyze(records, classification_info)

        # 4. Priority Score
        w_rec = self.config.weight_pipeline_recurrence
        w_batch = self.config.weight_batch_frequency

        rec = metrics.pipeline_recurrence
        batch_freq = metrics.mixed_outcome_batch_frequency

        weighted_rec = w_rec * rec
        weighted_batch = w_batch * batch_freq

        if TestClassification.is_candidate(classification_info["classification"]):
            priority_score = weighted_rec + weighted_batch
        else:
            priority_score = 0.0

        score_breakdown: Dict[str, float] = {
            "pipeline_recurrence": rec,
            "weight_pipeline_recurrence": w_rec,
            "weighted_pipeline_recurrence": weighted_rec,
            "mixed_outcome_batch_frequency": batch_freq,
            "weight_batch_frequency": w_batch,
            "weighted_batch_frequency": weighted_batch,
        }

        # Environments
        tested_envs = sorted(list({r.test_case_environment for r in records}))

        return CandidateReport(
            test_case_name=test_name,
            classification=classification_info["classification"],
            evidence_level=classification_info["evidence_level"],
            evidence_explanation=classification_info["evidence_explanation"],
            total_executions=classification_info["total_executions"],
            total_passes=classification_info["total_passes"],
            total_failures=classification_info["total_failures"],
            empirical_failure_rate=classification_info["empirical_failure_rate"],
            metrics=metrics,
            impact=impact,
            priority_score=priority_score,
            score_breakdown=score_breakdown,
            total_pipelines=classification_info.get("total_pipelines", 0),
            sequence_anomalies_count=classification_info.get("sequence_anomalies_count", 0),
            excluded_anomaly_recoveries=classification_info.get("excluded_anomaly_recoveries", 0),
            primary_failure_signature=primary_sig,
            tested_environments=tested_envs,
        )

    def prioritize_all(
        self,
        executions: List[NormalizedExecution]
    ) -> List[CandidateReport]:
        """
        Group executions by test case and produce a sorted list of candidate reports.
        Uses evidence-stratified ranking: High Evidence -> Moderate Evidence -> Low Evidence,
        preventing low-sample tests from outranking systemic flaky candidates.
        """
        grouped = self.classifier.group_by_test(executions)
        reports: List[CandidateReport] = []

        for test_name, records in grouped.items():
            report = self.analyze_test(test_name, records)
            reports.append(report)

        # Evidence-stratified sorting
        def sort_key(c: CandidateReport):
            is_verified = 1 if c.classification == TestClassification.FLAKY_CANDIDATE_IN_BATCH_VERIFIED.value else 0
            is_intermittent = 1 if c.classification == TestClassification.INTERMITTENT_CANDIDATE_CROSS_PIPELINE.value else 0
            is_candidate = 1 if (is_verified or is_intermittent) else 0

            evidence_rank = self.EVIDENCE_RANK.get(c.evidence_level, 0)

            return (
                is_candidate,         # 1. Active candidates first
                is_verified,          # 2. In-batch verified before cross-pipeline observational
                evidence_rank,        # 3. Evidence tier: High (3) -> Moderate (2) -> Low (1)
                c.priority_score,     # 4. Priority score within tier
                c.total_failures,     # 5. Total failures
                c.total_executions,   # 6. Total executions
            )

        reports.sort(key=sort_key, reverse=True)
        return reports
