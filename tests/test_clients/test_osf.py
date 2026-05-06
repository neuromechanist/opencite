"""Tests for the OSF Preprints API client."""

from __future__ import annotations

import httpx
import pytest
import respx

from opencite.clients.osf import OSFClient
from opencite.clients.preprint_base import FulltextRoute
from opencite.config import Config
from opencite.models import IDSet, Paper

_BASE = "https://api.osf.io"

_OSF_ITEM = {
    "id": "abc12",
    "type": "preprints",
    "attributes": {
        "title": "A PsyArXiv preprint on memory",
        "description": "We studied working memory in 30 participants.",
        "date_published": "2024-03-15T00:00:00.000Z",
        "doi": "10.31234/osf.io/abc12",
        "tags": ["working memory", "psychology"],
    },
    "relationships": {
        "provider": {"data": {"id": "psyarxiv", "type": "preprint-providers"}},
    },
    "links": {
        "html": "https://osf.io/preprints/psyarxiv/abc12",
        "download": "https://osf.io/abc12/download",
    },
}


class TestOSFParse:
    def _client(self) -> OSFClient:
        return OSFClient(Config())

    def test_parse_item_basic(self):
        client = self._client()
        paper = client._parse_item(_OSF_ITEM)
        assert paper is not None
        assert paper.title == "A PsyArXiv preprint on memory"
        assert paper.ids.doi == "10.31234/osf.io/abc12"
        assert paper.year == 2024
        assert "psyarxiv" in str(paper.data_sources)
        assert paper.is_oa is True

    def test_parse_item_pdf_location(self):
        paper = self._client()._parse_item(_OSF_ITEM)
        assert paper is not None
        assert paper.best_pdf_url == "https://osf.io/abc12/download"

    def test_parse_item_topics(self):
        paper = self._client()._parse_item(_OSF_ITEM)
        assert paper is not None
        assert "working memory" in paper.topics

    def test_parse_item_no_title_returns_none(self):
        item = {**_OSF_ITEM, "attributes": {**_OSF_ITEM["attributes"], "title": ""}}
        assert self._client()._parse_item(item) is None

    def test_fulltext_route_is_none(self):
        client = self._client()
        paper = Paper(title="x", ids=IDSet(doi="10.31234/osf.io/abc12"))
        # Phase 3 defers OSF preprint full text to the PDF pipeline.
        assert client.fulltext_route(paper) == FulltextRoute.NONE


class TestOSFNetwork:
    @pytest.mark.asyncio
    @respx.mock
    async def test_search_returns_papers(self):
        respx.get(f"{_BASE}/v2/preprints/").mock(
            return_value=httpx.Response(200, json={"data": [_OSF_ITEM]})
        )
        async with OSFClient(Config()) as client:
            papers = await client.search("working memory")
        assert len(papers) == 1
        assert papers[0].ids.doi == "10.31234/osf.io/abc12"

    @pytest.mark.asyncio
    @respx.mock
    async def test_lookup_doi_routes_to_filter(self):
        respx.get(f"{_BASE}/v2/preprints/").mock(
            return_value=httpx.Response(200, json={"data": [_OSF_ITEM]})
        )
        async with OSFClient(Config()) as client:
            paper = await client.lookup_doi("10.31234/osf.io/abc12")
        assert paper is not None
        assert paper.ids.doi == "10.31234/osf.io/abc12"

    @pytest.mark.asyncio
    async def test_lookup_doi_non_osf_returns_none_without_network(self):
        # Non-OSF DOI must short-circuit before any HTTP call.
        async with OSFClient(Config()) as client:
            with respx.mock(assert_all_called=False) as mock:
                assert await client.lookup_doi("10.1038/nature12373") is None
                assert not mock.routes
