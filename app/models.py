from dataclasses import dataclass
from typing import Optional

@dataclass
class TestExecution:
    test_id: str
    run_id: str
    project_id: str
    commit_id: str
    environment: str
    pipeline_id: str
    result: str
    duration_seconds: float
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    is_rerun: bool = False
    parent_run_id: Optional[str] = None
