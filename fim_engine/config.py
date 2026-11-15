"""
FIM Engine - Configuration and Constants
Defines default weights, thresholds, and evidence criteria for flaky analysis.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineConfig:
    """Configuration parameters for the FIM analysis engine."""
    
    # Prioritization weights (Exploratory baseline)
    # Priority = w_recurrence * pipeline_recurrence + w_batch_frequency * mixed_batch_frequency
    weight_pipeline_recurrence: float = 0.60
    weight_batch_frequency: float = 0.40

    # Minimum executions required before classifying test behavior
    min_executions_evidence: int = 3

    # Evidence level thresholds
    high_evidence_executions: int = 100
    high_evidence_mixed_batches: int = 3
    moderate_evidence_executions: int = 20
    moderate_evidence_mixed_batches: int = 1

    # Batch grouping definition: fields used to identify comparable execution runs
    batch_key_fields: tuple = ("pipeline_id", "test_case_environment")

    def validate(self) -> None:
        """Validate weight configuration."""
        total = self.weight_pipeline_recurrence + self.weight_batch_frequency
        if abs(total - 1.0) > 1e-4:
            raise ValueError(f"Prioritization weights must sum to 1.0 (got {total:.4f})")

