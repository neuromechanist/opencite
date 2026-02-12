"""Base output formatter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opencite.models import Paper


class OutputFormatter(ABC):
    """Abstract base for all output formatters."""

    @abstractmethod
    def format_papers(self, papers: list[Paper], verbose: bool = False) -> str:
        """Format a list of papers into a string."""
        ...

    @abstractmethod
    def format_single(self, paper: Paper, verbose: bool = False) -> str:
        """Format a single paper into a string."""
        ...
