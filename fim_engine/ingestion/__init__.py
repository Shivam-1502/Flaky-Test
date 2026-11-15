"""
FIM Engine - Ingestion Package
Provides unified factory function to ingest test execution data from Parquet, CSV, JSON, and SQLite.
"""

import os
from typing import List, Optional

from fim_engine.models import NormalizedExecution
from fim_engine.ingestion.base import BaseReader
from fim_engine.ingestion.parquet_reader import ParquetReader
from fim_engine.ingestion.csv_reader import CSVReader
from fim_engine.ingestion.json_reader import JSONReader
from fim_engine.ingestion.sqlite_reader import SQLiteReader


def detect_format(source: str) -> str:
    """Auto-detect format from file extension or directory contents."""
    if os.path.isdir(source):
        # Check if contains parquet files
        for f in os.listdir(source):
            if f.endswith(".parquet"):
                return "parquet"
        return "parquet"

    ext = os.path.splitext(source)[1].lower()
    if ext in (".parquet", ".pq"):
        return "parquet"
    elif ext in (".csv", ".tsv"):
        return "csv"
    elif ext in (".json", ".jsonl"):
        return "json"
    elif ext in (".db", ".sqlite", ".sqlite3"):
        return "sqlite"
    else:
        raise ValueError(f"Cannot auto-detect format for source: {source}. Specify --format explicitly.")


def load_dataset(
    source: str,
    format: Optional[str] = None,
    max_records: Optional[int] = None,
    table_name: str = "test_executions"
) -> List[NormalizedExecution]:
    """
    Load test execution records from source into a list of NormalizedExecution objects.

    Args:
        source: File path, directory path, or SQLite path.
        format: Format specifier ('parquet', 'csv', 'json', 'sqlite'). Auto-detected if None.
        max_records: Maximum number of records to load.
        table_name: Table name for SQLite sources (default: 'test_executions').

    Returns:
        List of NormalizedExecution instances.
    """
    fmt = (format or detect_format(source)).lower()

    if fmt == "parquet":
        reader: BaseReader = ParquetReader()
    elif fmt == "csv":
        reader = CSVReader()
    elif fmt == "json":
        reader = JSONReader()
    elif fmt == "sqlite":
        reader = SQLiteReader(table_name=table_name)
    else:
        raise ValueError(f"Unsupported dataset format: {fmt}. Must be one of: parquet, csv, json, sqlite")

    return reader.read(source, max_records=max_records)

