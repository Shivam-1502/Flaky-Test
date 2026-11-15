"""
FIM Engine - Base Ingestion Reader
Abstract base class for all dataset ingestion adapters.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from fim_engine.models import NormalizedExecution


class BaseReader(ABC):
    """Abstract base class for dataset readers."""

    @abstractmethod
    def read(self, source: str, max_records: Optional[int] = None) -> List[NormalizedExecution]:
        """
        Read test execution records from source and return a list of NormalizedExecution objects.
        
        Args:
            source: File path, directory, or connection URI.
            max_records: Maximum number of records to ingest (None for all).
            
        Returns:
            List of NormalizedExecution instances.
        """
        pass

