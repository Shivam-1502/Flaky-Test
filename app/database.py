import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .config import DB_PATH
from .models import TestExecution

SCHEMA = """
CREATE TABLE IF NOT EXISTS pipelines (
    pipeline_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    commit_id TEXT NOT NULL,
    environment TEXT NOT NULL,
    result TEXT NOT NULL CHECK(result IN ('PASS', 'FAIL')),
    duration_seconds REAL NOT NULL,
    base_failures INTEGER NOT NULL,
    rerun_count INTEGER NOT NULL,
    recovered_count INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS test_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id TEXT NOT NULL,
    run_id TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL,
    commit_id TEXT NOT NULL,
    environment TEXT NOT NULL,
    pipeline_id TEXT NOT NULL,
    result TEXT NOT NULL CHECK(result IN ('PASS', 'FAIL')),
    duration_seconds REAL NOT NULL,
    error_type TEXT,
    error_message TEXT,
    stack_trace TEXT,
    is_rerun INTEGER NOT NULL DEFAULT 0,
    parent_run_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_test_id ON test_executions(test_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_id ON test_executions(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_environment ON test_executions(environment);
CREATE INDEX IF NOT EXISTS idx_parent_run ON test_executions(parent_run_id);
"""

@contextmanager
def connection(db_path=None):
    conn = sqlite3.connect(Path(db_path or DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def initialize_database(db_path=None):
    with connection(db_path) as conn:
        conn.executescript(SCHEMA)

def clear_database(db_path=None):
    with connection(db_path) as conn:
        conn.execute("DELETE FROM test_executions")
        conn.execute("DELETE FROM pipelines")

def insert_execution(execution: TestExecution, db_path=None):
    with connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO test_executions (
                test_id, run_id, project_id, commit_id, environment,
                pipeline_id, result, duration_seconds,
                error_type, error_message, stack_trace,
                is_rerun, parent_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution.test_id, execution.run_id, execution.project_id,
                execution.commit_id, execution.environment, execution.pipeline_id,
                execution.result, execution.duration_seconds,
                execution.error_type, execution.error_message,
                execution.stack_trace, int(execution.is_rerun),
                execution.parent_run_id,
            ),
        )

def insert_pipeline(pipeline_id, project_id, commit_id, environment,
                    result, duration_seconds, base_failures,
                    rerun_count, recovered_count, db_path=None):
    with connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO pipelines (
                pipeline_id, project_id, commit_id, environment, result,
                duration_seconds, base_failures, rerun_count, recovered_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (pipeline_id, project_id, commit_id, environment, result,
             duration_seconds, base_failures, rerun_count, recovered_count),
        )

def fetch_all(db_path=None):
    with connection(db_path) as conn:
        return conn.execute(
            "SELECT * FROM test_executions ORDER BY created_at, id"
        ).fetchall()

def fetch_base_executions(db_path=None):
    with connection(db_path) as conn:
        return conn.execute(
            "SELECT * FROM test_executions WHERE is_rerun = 0 ORDER BY created_at, id"
        ).fetchall()

def fetch_rerun_executions(db_path=None):
    with connection(db_path) as conn:
        return conn.execute(
            "SELECT * FROM test_executions WHERE is_rerun = 1 ORDER BY created_at, id"
        ).fetchall()

def fetch_by_test(test_id, include_reruns=True, db_path=None):
    with connection(db_path) as conn:
        if include_reruns:
            return conn.execute(
                "SELECT * FROM test_executions WHERE test_id = ? ORDER BY created_at, id",
                (test_id,),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM test_executions WHERE test_id = ? AND is_rerun = 0 ORDER BY created_at, id",
            (test_id,),
        ).fetchall()

def fetch_pipelines(db_path=None):
    with connection(db_path) as conn:
        return conn.execute(
            "SELECT * FROM pipelines ORDER BY created_at, rowid"
        ).fetchall()
