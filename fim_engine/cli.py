"""
FIM Engine - Command Line Interface (Version 1.1)
Executes standalone flaky test analysis on Parquet, CSV, JSON, and SQLite datasets.
Features evidence-stratified ranking, sub-categorization, and retry sequence anomaly accounting.
"""

import sys
import argparse
import time

from fim_engine.config import EngineConfig
from fim_engine.ingestion import load_dataset
from fim_engine.prioritizer import Prioritizer
from fim_engine.reporting import ReportExporter
from fim_engine.models import TestClassification


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fim_engine",
        description="FIM Flakiness Impact Measurement Engine v1.1 - Standalone Analytics",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze test executions dataset")
    analyze_parser.add_argument("source", type=str, help="Path to dataset file or directory")
    analyze_parser.add_argument(
        "--format",
        choices=["parquet", "csv", "json", "sqlite"],
        default=None,
        help="Input format (auto-detected if omitted)",
    )
    analyze_parser.add_argument(
        "--table",
        type=str,
        default="test_executions",
        help="SQLite table name (default: test_executions)",
    )
    analyze_parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Maximum records to process (for sampling/benchmarking)",
    )
    analyze_parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/fim_engine",
        help="Directory to save exported reports (default: reports/fim_engine)",
    )
    analyze_parser.add_argument(
        "--w-recurrence",
        type=float,
        default=0.60,
        help="Weight for Pipeline Recurrence (default: 0.60)",
    )
    analyze_parser.add_argument(
        "--w-batch",
        type=float,
        default=0.40,
        help="Weight for Mixed-Outcome Batch Frequency (default: 0.40)",
    )
    analyze_parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top ranked candidates to print in console summary (default: 10)",
    )

    return parser


def run_analyze(args: argparse.Namespace) -> int:
    start_time = time.time()
    print("=" * 76)
    print("  FIM FLAKINESS IMPACT MEASUREMENT ENGINE v1.1 — STANDALONE ANALYTICS")
    print("=" * 76)
    print(f"Dataset source:     {args.source}")
    print(f"Format specifier:   {args.format or 'auto-detect'}")
    print(f"Prioritization:     {args.w_recurrence:.2f} * Recurrence + {args.w_batch:.2f} * Batch Frequency")
    print(f"Ranking Mode:       Evidence-Stratified (High -> Moderate -> Low)")
    print(f"Output directory:   {args.output_dir}")
    print("-" * 76)

    # 1. Configuration
    try:
        config = EngineConfig(
            weight_pipeline_recurrence=args.w_recurrence,
            weight_batch_frequency=args.w_batch,
        )
        config.validate()
    except ValueError as e:
        print(f"Error in configuration: {e}", file=sys.stderr)
        return 1

    # 2. Ingestion
    print(f"[*] Ingesting test execution records...")
    t_ingest = time.time()
    try:
        records = load_dataset(
            source=args.source,
            format=args.format,
            max_records=args.max_records,
            table_name=args.table,
        )
    except Exception as e:
        print(f"Error during dataset ingestion: {e}", file=sys.stderr)
        return 1

    ingest_duration = time.time() - t_ingest
    print(f"    Ingested {len(records):,} records in {ingest_duration:.2f}s.")

    if not records:
        print("Warning: No execution records found.", file=sys.stderr)
        return 0

    # 3. Prioritization & Classification
    print(f"[*] Classifying tests, validating sequences, computing metrics, and ranking candidates...")
    t_proc = time.time()
    prioritizer = Prioritizer(config=config)
    ranked_candidates = prioritizer.prioritize_all(records)
    proc_duration = time.time() - t_proc
    print(f"    Processed {len(ranked_candidates):,} unique test cases in {proc_duration:.2f}s.")

    # 4. Reporting
    print(f"[*] Exporting CSV and JSON reports to '{args.output_dir}'...")
    exporter = ReportExporter()
    exported_files = exporter.export(
        candidates=ranked_candidates,
        output_dir=args.output_dir,
        dataset_source=args.source,
        total_records=len(records),
        config_info={
            "formula": f"Priority = {config.weight_pipeline_recurrence:.2f} * Pipeline_Recurrence + {config.weight_batch_frequency:.2f} * Mixed_Batch_Frequency",
            "ranking_architecture": "Evidence-Stratified (High Evidence -> Moderate Evidence -> Low Evidence)",
            "weight_pipeline_recurrence": config.weight_pipeline_recurrence,
            "weight_batch_frequency": config.weight_batch_frequency,
        },
    )

    total_duration = time.time() - start_time

    # 5. Summary Display
    verified_list = [
        c for c in ranked_candidates
        if c.classification == TestClassification.FLAKY_CANDIDATE_IN_BATCH_VERIFIED.value
    ]
    intermittent_list = [
        c for c in ranked_candidates
        if c.classification == TestClassification.INTERMITTENT_CANDIDATE_CROSS_PIPELINE.value
    ]
    failing_list = [
        c for c in ranked_candidates
        if c.classification == TestClassification.CONSISTENTLY_FAILING.value
    ]
    passing_list = [
        c for c in ranked_candidates
        if c.classification == TestClassification.CONSISTENTLY_PASSING.value
    ]
    insufficient_list = [
        c for c in ranked_candidates
        if c.classification == TestClassification.INSUFFICIENT_EVIDENCE.value
    ]

    total_tests = len(ranked_candidates)
    active_candidates = verified_list + intermittent_list

    # Anomaly counts
    total_anomalies = sum(c.sequence_anomalies_count for c in ranked_candidates)
    total_excluded = sum(c.excluded_anomaly_recoveries for c in ranked_candidates)

    print("\n" + "=" * 76)
    print("  ANALYSIS SUMMARY (v1.1)")
    print("=" * 76)
    print(f"Total Records Ingested:             {len(records):,}")
    print(f"Unique Test Cases:                  {total_tests:,}")
    print(f"In-Batch Retry Verified Flaky:      {len(verified_list):,} ({(len(verified_list) / total_tests * 100):.1f}%)")
    print(f"Cross-Pipeline Intermittent:        {len(intermittent_list):,} ({(len(intermittent_list) / total_tests * 100):.1f}%)")
    print(f"Consistently Failing:               {len(failing_list):,} ({(len(failing_list) / total_tests * 100):.1f}%)")
    print(f"Consistently Passing:               {len(passing_list):,} ({(len(passing_list) / total_tests * 100):.1f}%)")
    print(f"Insufficient Evidence:              {len(insufficient_list):,} ({(len(insufficient_list) / total_tests * 100):.1f}%)")
    print(f"Sequence Anomaly Batches Detected:  {total_anomalies:,} ({total_excluded} recoveries excluded)")
    print("-" * 76)

    top_n = min(args.top, len(active_candidates))
    if top_n > 0:
        print(f"TOP {top_n} CANDIDATES (Evidence-Stratified Ranking):")
        print(f"{'Rank':<5} {'Score':<7} {'Recurr':<7} {'BatchFreq':<10} {'Execs':<6} {'Pipes':<6} {'Evidence':<18} {'Test Case Name'}")
        print("-" * 76)
        for i, c in enumerate(active_candidates[:top_n], start=1):
            short_name = c.test_case_name if len(c.test_case_name) <= 32 else (c.test_case_name[:29] + "...")
            print(
                f"{i:<5} {c.priority_score:<7.4f} {c.metrics.pipeline_recurrence:<7.4f} "
                f"{c.metrics.mixed_outcome_batch_frequency:<10.4f} {c.total_executions:<6} "
                f"{c.total_pipelines:<6} {c.evidence_level:<18} {short_name}"
            )
    else:
        print("No candidates identified.")

    print("\n" + "-" * 76)
    print("Generated Artifacts:")
    print(f"  CSV:     {exported_files['csv']}")
    print(f"  JSON:    {exported_files['json']}")
    print(f"  Summary: {exported_files['summary']}")
    print(f"\nCompleted in {total_duration:.2f} seconds.")
    print("=" * 76)
    return 0


def main() -> int:
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "analyze":
        return run_analyze(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
