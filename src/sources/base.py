"""Abstract base class for all scraper sources."""
from abc import ABC, abstractmethod
from typing import List
from src.models import RawItem

class BaseSource(ABC):
    """Abstract interface for any ingestion channel."""
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the source channel."""
        pass

    @abstractmethod
    def fetch(self) -> List[RawItem]:
        """Collects raw trend candidates and returns a list of RawItem objects."""
        pass