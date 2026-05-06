"""Abstract base for preprint-server clients (the "x-arXiv" abstraction).

Concrete subclasses (arXiv, bioRxiv, medRxiv, OSF/PsyArXiv, Zenodo, Figshare)
share the same surface so the search orchestrator and full-text dispatcher
can treat them uniformly.

Phase 1 introduces the surface; Phase 2 fills in `fulltext_route` /
`fetch_fulltext` for arXiv (ar5iv HTML5) and bioRxiv/medRxiv (.full HTML).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import StrEnum
from io import BytesIO
from typing import TYPE_CHECKING, ClassVar

from opencite.clients.base import BaseClient

if TYPE_CHECKING:
    from opencite.models import Paper

logger = logging.getLogger(__name__)


def html_to_markdown(html: str) -> str | None:
    """Convert an HTML document to markdown using markitdown.

    markitdown is the same library used by the PDF pipeline (`convert.py`),
    so output style is consistent across full-text routes. Returns None on
    conversion failure.
    """
    try:
        from markitdown import MarkItDown
    except ImportError:
        logger.warning(
            "markitdown is required for HTML-to-markdown conversion but is not installed"
        )
        return None

    try:
        converter = MarkItDown()
        result = converter.convert_stream(
            BytesIO(html.encode("utf-8")),
            file_extension=".html",
        )
        return result.text_content
    except (OSError, ValueError, RuntimeError) as e:
        logger.warning("HTML-to-markdown conversion failed: %s", e)
        return None


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

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Enforce `name` at class-definition time on concrete subclasses.
        # ``ClassVar[str]`` is a static-analysis hint; this guards the runtime
        # contract so a forgotten declaration fails loudly here rather than
        # later when the orchestrator tries to read it.
        # Underscore-prefixed classes are internal abstract bases (e.g.
        # ``_BiorxivLikePreprintClient``) -- they're allowed to defer the
        # `name` declaration to their concrete subclasses.
        if cls.__name__.startswith("_"):
            return
        if not getattr(cls, "__abstractmethods__", None) and not hasattr(cls, "name"):
            raise TypeError(f"{cls.__name__} must declare a `name` class attribute")

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
