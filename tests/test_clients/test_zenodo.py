"""Tests for the Zenodo REST API client."""

from __future__ import annotations

import httpx
import pytest
import respx

from opencite.clients.preprint_base import FulltextRoute
from opencite.clients.zenodo import ZenodoClient
from opencite.config import Config
from opencite.models import IDSet, Paper

_BASE = "https://zenodo.org"

_ZENODO_RECORD = {
    "id": 123456,
    "doi": "10.5281/zenodo.123456",
    "metadata": {
        "title": "A Zenodo preprint",
        "description": "<p>Methods and results.</p>",
        "publication_date": "2024-09-01",
        "creators": [
            {"name": "Smith, Jane"},
            {"name": "Roe, John"},
        ],
        "keywords": ["preprint", "methodology"],
    },
    "files": [
        {
            "key": "manuscript.pdf",
            "links": {
                "self": "https://zenodo.org/api/records/123456/files/manuscript.pdf/content"
            },
        },
        {"key": "data.csv", "links": {"self": "ignored"}},
    ],
    "links": {"html": "https://zenodo.org/records/123456"},
}


class TestZenodoParse:
    def _client(self) -> ZenodoClient:
        return ZenodoClient(Config())

    def test_parse_record_basic(self):
        paper = self._client()._parse_record(_ZENODO_RECORD)
        assert paper is not None
        assert paper.title == "A Zenodo preprint"
        assert paper.ids.doi == "10.5281/zenodo.123456"
        assert paper.year == 2024

    def test_parse_record_strips_html_in_abstract(self):
        paper = self._client()._parse_record(_ZENODO_RECORD)
        assert paper is not None
        assert "<p>" not in paper.abstract
        assert "Methods" in paper.abstract

    def test_parse_record_only_pdf_files_kept(self):
        paper = self._client()._parse_record(_ZENODO_RECORD)
        assert paper is not None
        urls = [loc.url for loc in paper.pdf_locations]
        assert any(u.endswith(".pdf/content") for u in urls)
        assert not any("data.csv" in u for u in urls)

    def test_parse_record_authors(self):
        paper = self._client()._parse_record(_ZENODO_RECORD)
        assert paper is not None
        assert len(paper.authors) == 2
        assert paper.authors[0].family_name == "Smith"
        assert paper.authors[0].given_name == "Jane"

    def test_fulltext_route_is_none(self):
        client = self._client()
        paper = Paper(title="x", ids=IDSet(doi="10.5281/zenodo.123456"))
        assert client.fulltext_route(paper) == FulltextRoute.NONE


class TestZenodoNetwork:
    @pytest.mark.asyncio
    @respx.mock
    async def test_search_returns_papers(self):
        respx.get(f"{_BASE}/api/records").mock(
            return_value=httpx.Response(200, json={"hits": {"hits": [_ZENODO_RECORD]}})
        )
        async with ZenodoClient(Config()) as client:
            papers = await client.search("methodology")
        assert len(papers) == 1
        assert "zenodo" in papers[0].data_sources

    @pytest.mark.asyncio
    @respx.mock
    async def test_lookup_doi_extracts_record_id(self):
        respx.get(f"{_BASE}/api/records/123456").mock(
            return_value=httpx.Response(200, json=_ZENODO_RECORD)
        )
        async with ZenodoClient(Config()) as client:
            paper = await client.lookup_doi("10.5281/zenodo.123456")
        assert paper is not None
        assert paper.ids.doi == "10.5281/zenodo.123456"

    @pytest.mark.asyncio
    async def test_lookup_doi_non_zenodo_short_circuits(self):
        async with ZenodoClient(Config()) as client:
            with respx.mock(assert_all_called=False) as mock:
                assert await client.lookup_doi("10.1038/nature12373") is None
                assert not mock.routes

    @pytest.mark.asyncio
    async def test_lookup_doi_non_numeric_record_id_returns_none(self):
        async with ZenodoClient(Config()) as client:
            with respx.mock(assert_all_called=False) as mock:
                assert await client.lookup_doi("10.5281/zenodo.not-a-number") is None
                assert not mock.routes
