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
    def test_fulltext_route_none_when_no_preprint_signal(self, cls):
        """Without an arXiv ID or a 10.1101/* DOI, no preprint route applies."""
        from opencite.models import IDSet, Paper

        client = cls(Config())
        empty_paper = Paper(title="x", ids=IDSet(doi="10.1038/nature12373"))
        assert client.fulltext_route(empty_paper) == FulltextRoute.NONE

    @pytest.mark.parametrize(
        "cls",
        [ArXivClient, BioRxivClient, MedRxivClient],
    )
    @pytest.mark.asyncio
    async def test_fetch_fulltext_none_when_no_preprint_signal(self, cls):
        """`fetch_fulltext` short-circuits to None before opening any session."""
        from opencite.models import IDSet, Paper

        client = cls(Config())
        empty_paper = Paper(title="x", ids=IDSet(doi="10.1038/nature12373"))
        # No `async with`: short-circuit must fire before any network use.
        assert await client.fetch_fulltext(empty_paper) is None


class TestPreprintClientSubclassEnforcement:
    """`__init_subclass__` rejects subclasses missing required class attrs."""

    def test_missing_name_raises(self):
        with pytest.raises(TypeError, match="must declare a `name`"):

            class BadConcreteClient(PreprintClient):  # type: ignore[misc]
                async def search(self, query, max_results=20, **kwargs):  # noqa: ARG002
                    return []

                async def lookup_doi(self, doi):  # noqa: ARG002
                    return None

                def _default_headers(self):
                    return {}

    def test_missing_server_raises_for_biorxiv_like(self):
        from opencite.clients._biorxiv_like import _BiorxivLikePreprintClient

        with pytest.raises(TypeError, match="must declare a `server`"):

            class BadConcreteServerClient(_BiorxivLikePreprintClient):  # type: ignore[misc]
                name = "bad-without-server"
