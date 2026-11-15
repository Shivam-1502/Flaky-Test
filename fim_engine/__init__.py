"""
FIM Engine - Independent Metrics-Based Flaky-Test Analysis Engine
Version: 1.0.0
"""

from fim_engine.models import (
    NormalizedExecution,
    TestClassification,
    EvidenceLevel,
    MetricReport,
    ImpactAnalysis,
    CandidateReport,
)
from fim_engine.config import EngineConfig
from fim_engine.ingestion import load_dataset
from fim_engine.detectors.classifier import TestClassifier
from fim_engine.metrics.calculator import MetricCalculator
from fim_engine.impact import ImpactAnalyzer
from fim_engine.prioritizer import Prioritizer
from fim_engine.reporting import ReportExporter

__version__ = "1.0.0"

__all__ = [
    "NormalizedExecution",
    "TestClassification",
    "EvidenceLevel",
    "MetricReport",
    "ImpactAnalysis",
    "CandidateReport",
    "EngineConfig",
    "load_dataset",
    "TestClassifier",
    "MetricCalculator",
    "ImpactAnalyzer",
    "Prioritizer",
    "ReportExporter",
]

