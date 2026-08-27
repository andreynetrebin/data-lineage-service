"""Абстрактный базовый класс Sink."""
from abc import ABC, abstractmethod
from typing import List

from ..model import Edge, Node, Snapshot


class Sink(ABC):
    """Интерфейс приёмника снапшота графа."""

    @abstractmethod
    def write(self, snapshot: Snapshot, nodes: List[Node], edges: List[Edge]) -> None:
        """Сохранить снапшот; реализация обновляет snapshot.status и snapshot.stats."""