"""
FIM Engine - CSV Ingestion Reader
Ingests test execution records from CSV files into NormalizedExecution instances.
"""

import os
from typing import List, Optional
import pandas as pd

from fim_engine.ingestion.base import BaseReader
from fim_engine.models import NormalizedExecution


class CSVReader(BaseReader):
    """Ingests CSV files into NormalizedExecution records."""

    def read(self, source: str, max_records: Optional[int] = None) -> List[NormalizedExecution]:
        if not os.path.exists(source):
            raise FileNotFoundError(f"CSV file not found: {source}")

        # Read CSV
        df = pd.read_csv(source, nrows=max_records)
        records: List[NormalizedExecution] = []

        for row in df.itertuples(index=False):
            row_dict = row._asdict() if hasattr(row, "_asdict") else dict(zip(df.columns, row))

            name = str(
                row_dict.get("test_case_name")
                or row_dict.get("test_name")
                or row_dict.get("test_id")
                or "unknown_test"
            )
            env = str(row_dict.get("test_case_environment") or row_dict.get("environment") or "default")
            pipe_id = str(row_dict.get("pipeline_id") or row_dict.get("run_id") or "pipe-0")
            
            raw_job = row_dict.get("job_id")
            job_id = str(raw_job) if raw_job is not None and pd.notna(raw_job) else None

            raw_retry = row_dict.get("retry_count") or row_dict.get("is_rerun") or 0
            try:
                retry_count = int(raw_retry) if pd.notna(raw_retry) else 0
            except (ValueError, TypeError):
                retry_count = 0

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

            raw_dur = row_dict.get("duration") if "duration" in row_dict else row_dict.get("duration_seconds")
            if raw_dur is None or pd.isna(raw_dur):
                raw_dur_ms = row_dict.get("duration_ms")
                duration = float(raw_dur_ms) / 1000.0 if raw_dur_ms is not None and pd.notna(raw_dur_ms) else None
            else:
                try:
                    duration = float(raw_dur)
                except (ValueError, TypeError):
                    duration = None

            symptoms = row_dict.get("failure_symptoms") or row_dict.get("error_message")
            failure_symptoms = str(symptoms) if symptoms is not None and pd.notna(symptoms) else None

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
                source_file=os.path.basename(source),
            )
            records.append(exec_record)

        return records
