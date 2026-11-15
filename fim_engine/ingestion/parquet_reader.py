"""
FIM Engine - Parquet Ingestion Reader
High-performance PyArrow/pandas reader for Parquet datasets, specifically supporting
the Microsoft Playwright Parquet dataset and generic Parquet execution schemas.
"""

import os
import glob
from typing import List, Optional
import pyarrow.parquet as pq
import pandas as pd

from fim_engine.ingestion.base import BaseReader
from fim_engine.models import NormalizedExecution


class ParquetReader(BaseReader):
    """
    Ingests Parquet files or directories containing Parquet files.
    Optimized to read only required columns via PyArrow projection.
    """

    PLAYWRIGHT_COLUMNS = [
        "test_case_name",
        "test_case_environment",
        "pipeline_id",
        "job_id",
        "retry_count",
        "duration",
        "result",
        "generic_result",
        "failure_symptoms",
        "pipeline_commit_sha",
    ]

    def read(self, source: str, max_records: Optional[int] = None) -> List[NormalizedExecution]:
        files_to_read = []
        if os.path.isdir(source):
            files_to_read = sorted(glob.glob(os.path.join(source, "*.parquet")))
            if not files_to_read:
                raise FileNotFoundError(f"No .parquet files found in directory: {source}")
        elif os.path.isfile(source):
            files_to_read = [source]
        else:
            raise FileNotFoundError(f"Parquet source path does not exist: {source}")

        records: List[NormalizedExecution] = []

        for file_path in files_to_read:
            # Check schema of the file
            parquet_file = pq.ParquetFile(file_path)
            file_schema_cols = set(parquet_file.schema.names)

            # Determine columns to project
            available_cols = [c for c in self.PLAYWRIGHT_COLUMNS if c in file_schema_cols]
            if not available_cols:
                # Generic fallback: read all columns
                available_cols = None

            # Read table
            table = pq.read_table(file_path, columns=available_cols)
            df = table.to_pandas()

            for row in df.itertuples(index=False):
                # Map row attributes
                row_dict = row._asdict() if hasattr(row, "_asdict") else dict(zip(df.columns, row))

                # Test case name
                name = str(
                    row_dict.get("test_case_name")
                    or row_dict.get("test_name")
                    or row_dict.get("test_id")
                    or "unknown_test"
                )

                # Environment
                env = str(row_dict.get("test_case_environment") or row_dict.get("environment") or "default")

                # Pipeline ID
                pipe_id = str(row_dict.get("pipeline_id") or row_dict.get("run_id") or "pipe-0")

                # Job ID
                job_id = str(row_dict.get("job_id")) if row_dict.get("job_id") is not None and pd.notna(row_dict.get("job_id")) else None

                # Retry count
                raw_retry = row_dict.get("retry_count") or row_dict.get("is_rerun") or 0
                try:
                    retry_count = int(raw_retry) if pd.notna(raw_retry) else 0
                except (ValueError, TypeError):
                    retry_count = 0

                # Status normalization
                # Playwright generic_result: 'pass-like' or 'fail-like'
                orig_result = str(row_dict.get("result") or "")
                gen_result = row_dict.get("generic_result")
                raw_status = row_dict.get("status")

                if gen_result is not None and pd.notna(gen_result):
                    status = "PASS" if str(gen_result).lower() == "pass-like" else "FAIL"
                elif raw_status is not None and pd.notna(raw_status):
                    status = "PASS" if str(raw_status).upper() in ("PASS", "PASSED", "SUCCESS") else "FAIL"
                elif orig_result:
                    status = "PASS" if orig_result.lower() in ("passed", "pass", "success") else "FAIL"
                else:
                    status = "FAIL"

                # Duration in seconds
                raw_dur = row_dict.get("duration") if "duration" in row_dict else row_dict.get("duration_seconds")
                if raw_dur is None or pd.isna(raw_dur):
                    raw_dur_ms = row_dict.get("duration_ms")
                    duration = float(raw_dur_ms) / 1000.0 if raw_dur_ms is not None and pd.notna(raw_dur_ms) else None
                else:
                    try:
                        duration = float(raw_dur)
                    except (ValueError, TypeError):
                        duration = None

                # Failure symptoms
                symptoms = row_dict.get("failure_symptoms") or row_dict.get("error_message")
                failure_symptoms = str(symptoms) if symptoms is not None and pd.notna(symptoms) else None

                # Commit SHA
                commit = row_dict.get("pipeline_commit_sha") or row_dict.get("commit_sha") or row_dict.get("commit_id")
                commit_id = str(commit) if commit is not None and pd.notna(commit) else None

                exec_record = NormalizedExecution(
                    test_case_name=name,
                    test_case_environment=env,
                    pipeline_id=pipe_id,
                    job_id=job_id,
                    retry_count=retry_count,
                    status=status,
                    original_result=orig_result,
                    duration=duration,
                    failure_symptoms=failure_symptoms,
                    commit_id=commit_id,
                    source_file=os.path.basename(file_path),
                )
                records.append(exec_record)

                if max_records and len(records) >= max_records:
                    return records

        return records
