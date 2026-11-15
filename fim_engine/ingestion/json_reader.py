"""
FIM Engine - JSON Ingestion Reader
Ingests test execution records from JSON files (array of objects or JSON lines).
"""

import os
import json
from typing import List, Optional

from fim_engine.ingestion.base import BaseReader
from fim_engine.models import NormalizedExecution


class JSONReader(BaseReader):
    """Ingests JSON array or JSON Lines files into NormalizedExecution records."""

    def read(self, source: str, max_records: Optional[int] = None) -> List[NormalizedExecution]:
        if not os.path.exists(source):
            raise FileNotFoundError(f"JSON file not found: {source}")

        records: List[NormalizedExecution] = []
        raw_rows = []

        with open(source, "r", encoding="utf-8") as f:
            first_char = f.read(1)
            f.seek(0)
            if first_char == "[":
                # JSON array
                raw_rows = json.load(f)
            else:
                # JSON lines
                for line in f:
                    line = line.strip()
                    if line:
                        raw_rows.append(json.loads(line))
                        if max_records and len(raw_rows) >= max_records:
                            break

        for row_dict in raw_rows:
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

            raw_retry = row_dict.get("retry_count") or row_dict.get("is_rerun") or 0
            try:
                retry_count = int(raw_retry)
            except (ValueError, TypeError):
                retry_count = 0

            orig_result = str(row_dict.get("result") or "")
            gen_result = row_dict.get("generic_result")
            raw_status = row_dict.get("status")

            if gen_result is not None:
                status = "PASS" if str(gen_result).lower() == "pass-like" else "FAIL"
            elif raw_status is not None:
                status = "PASS" if str(raw_status).upper() in ("PASS", "PASSED", "SUCCESS") else "FAIL"
            elif orig_result:
                status = "PASS" if orig_result.lower() in ("passed", "pass", "success") else "FAIL"
            else:
                status = "FAIL"

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
            if isinstance(symptoms, (dict, list)):
                failure_symptoms = json.dumps(symptoms)
            else:
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

            if max_records and len(records) >= max_records:
                break

        return records
