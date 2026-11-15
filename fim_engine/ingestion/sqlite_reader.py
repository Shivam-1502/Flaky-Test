"""
FIM Engine - SQLite Ingestion Reader
Read-only reader for SQLite databases (e.g. data/fim.db, data/comparison_fim.db).
Ensures database integrity by connecting in read-only mode.
"""

import os
import sqlite3
from typing import List, Optional

from fim_engine.ingestion.base import BaseReader
from fim_engine.models import NormalizedExecution


class SQLiteReader(BaseReader):
    """
    Ingests execution records from SQLite tables in read-only mode.
    Guarantees no modifications or locks are created on existing databases.
    """

    def __init__(self, table_name: str = "test_executions"):
        self.table_name = table_name

    def read(self, source: str, max_records: Optional[int] = None) -> List[NormalizedExecution]:
        if not os.path.exists(source):
            raise FileNotFoundError(f"SQLite database file not found: {source}")

        # Connect strictly read-only using URI
        abs_path = os.path.abspath(source).replace("\\", "/")
        uri = f"file:{abs_path}?mode=ro"
        
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        records: List[NormalizedExecution] = []

        try:
            cursor = conn.cursor()
            
            # Check available columns in table
            cursor.execute(f"PRAGMA table_info({self.table_name})")
            columns_info = cursor.fetchall()
            col_names = {row["name"] for row in columns_info}
            
            if not col_names:
                raise ValueError(f"Table '{self.table_name}' does not exist or has no columns in {source}")

            limit_clause = f"LIMIT {int(max_records)}" if max_records else ""
            query = f"SELECT * FROM {self.table_name} {limit_clause}"
            cursor.execute(query)

            for row in cursor.fetchall():
                row_dict = dict(row)

                name = str(
                    row_dict.get("test_case_name")
                    or row_dict.get("test_name")
                    or row_dict.get("test_id")
                    or "unknown_test"
                )
                env = str(row_dict.get("test_case_environment") or row_dict.get("environment") or "default")
                pipe_id = str(row_dict.get("pipeline_id") or row_dict.get("run_id") or "pipe-0")
                
                raw_job = row_dict.get("job_id")
                job_id = str(raw_job) if raw_job is not None else None

                raw_retry = row_dict.get("retry_count") if "retry_count" in row_dict else row_dict.get("is_rerun", 0)
                try:
                    retry_count = int(raw_retry) if raw_retry is not None else 0
                except (ValueError, TypeError):
                    retry_count = 0

                raw_status = row_dict.get("status") or row_dict.get("result") or ""
                status = "PASS" if str(raw_status).upper() in ("PASS", "PASSED", "SUCCESS") else "FAIL"
                orig_result = str(raw_status)

                raw_dur = row_dict.get("duration") if "duration" in row_dict else row_dict.get("duration_seconds")
                if raw_dur is None:
                    raw_dur_ms = row_dict.get("duration_ms")
                    duration = float(raw_dur_ms) / 1000.0 if raw_dur_ms is not None else None
                else:
                    try:
                        duration = float(raw_dur)
                    except (ValueError, TypeError):
                        duration = None

                symptoms = row_dict.get("failure_symptoms") or row_dict.get("error_message")
                failure_symptoms = str(symptoms) if symptoms is not None else None

                commit = row_dict.get("pipeline_commit_sha") or row_dict.get("commit_sha") or row_dict.get("commit_id")
                commit_id = str(commit) if commit is not None else None

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

        finally:
            conn.close()

        return records
