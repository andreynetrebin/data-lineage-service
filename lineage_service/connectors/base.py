"""Базовый класс коннектора источника."""
from abc import ABC, abstractmethod
from typing import Dict, Optional

from ..model import Graph


class SourceConnector(ABC):
    system: str = "unknown"

    def __init__(self, cfg: Optional[Dict] = None):
        self.cfg = cfg or {}

    @abstractmethod
    def collect(self) -> Graph:
        """Собрать свой участок графа и вернуть Graph."""
