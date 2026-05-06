"""Abstract base for preprint-server clients (the "x-arXiv" abstraction).

Concrete subclasses (arXiv, bioRxiv, medRxiv, OSF/PsyArXiv, Zenodo, Figshare)
share the same surface so the search orchestrator and full-text dispatcher
can treat them uniformly.

Phase 1 introduces the surface only; Phase 2 wires up `fulltext_route` /
`fetch_fulltext` for each subclass.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from opencite.clients.base import BaseClient

if TYPE_CHECKING:
    from opencite.models import Paper


class FulltextRoute(StrEnum):
    """Preferred full-text retrieval route declared by a preprint client."""

    HTML = "html"
    JATS = "jats"
    PDF = "pdf"
    NONE = "none"


class PreprintClient(BaseClient, ABC):
    """Abstract base for preprint-server clients.

    Subclasses must declare a `name` class attribute (the short source key
    used by the orchestrator and CLI `--source` flag) and implement
    `search` and `lookup_doi`.

    `fulltext_route` and `fetch_fulltext` ship a no-op default so Phase 1
    refactors don't need to provide full-text logic; Phase 2 overrides them.
    """

    name: ClassVar[str]

    @abstractmethod
    async def search(
        self,
        query: str,
        max_results: int = 20,
        **kwargs: object,
    ) -> list[Paper]:
        """Search the preprint server for *query* and return Papers."""

    @abstractmethod
    async def lookup_doi(self, doi: str) -> Paper | None:
        """Look up a single preprint by DOI."""

    def fulltext_route(self, paper: Paper) -> FulltextRoute:  # noqa: ARG002
        """Preferred full-text retrieval route for *paper*.

        Default is `NONE` (the existing PDF pipeline handles retrieval).
        Phase 2 overrides this in subclasses that expose HTML/JATS endpoints.
        """
        return FulltextRoute.NONE

    async def fetch_fulltext(self, paper: Paper) -> str | None:  # noqa: ARG002
        """Fetch full text for *paper* and return markdown.

        Default returns None (no preprint-native full-text source). Phase 2
        overrides this where HTML or JATS XML is available.
        """
        return None
