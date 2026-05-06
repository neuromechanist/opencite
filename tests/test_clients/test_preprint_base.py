"""Tests for the PreprintClient ABC and FulltextRoute enum."""

from __future__ import annotations

import pytest

from opencite.clients.arxiv import ArXivClient
from opencite.clients.biorxiv import BioRxivClient
from opencite.clients.medrxiv import MedRxivClient
from opencite.clients.preprint_base import FulltextRoute, PreprintClient
from opencite.config import Config


class TestFulltextRoute:
    def test_enum_values(self):
        assert FulltextRoute.HTML.value == "html"
        assert FulltextRoute.JATS.value == "jats"
        assert FulltextRoute.PDF.value == "pdf"
        assert FulltextRoute.NONE.value == "none"


class TestPreprintClientABC:
    def test_cannot_instantiate_abc_directly(self):
        """PreprintClient is abstract; instantiation must fail."""
        with pytest.raises(TypeError):
            PreprintClient(Config())  # type: ignore[abstract]

    @pytest.mark.parametrize(
        "cls",
        [ArXivClient, BioRxivClient, MedRxivClient],
    )
    def test_subclass_is_preprint_client(self, cls):
        assert issubclass(cls, PreprintClient)

    @pytest.mark.parametrize(
        "cls,expected_name",
        [
            (ArXivClient, "arxiv"),
            (BioRxivClient, "biorxiv"),
            (MedRxivClient, "medrxiv"),
        ],
    )
    def test_subclass_declares_name(self, cls, expected_name):
        assert cls.name == expected_name

    @pytest.mark.parametrize(
        "cls",
        [ArXivClient, BioRxivClient, MedRxivClient],
    )
    def test_default_fulltext_route_is_none(self, cls):
        """Phase 1 ships no preprint-native full-text routes; Phase 2 adds them."""
        client = cls(Config())
        # ``Paper`` argument is unused in the default impl; pass None.
        assert client.fulltext_route(None) == FulltextRoute.NONE  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "cls",
        [ArXivClient, BioRxivClient, MedRxivClient],
    )
    @pytest.mark.asyncio
    async def test_default_fetch_fulltext_returns_none(self, cls):
        client = cls(Config())
        assert await client.fetch_fulltext(None) is None  # type: ignore[arg-type]
