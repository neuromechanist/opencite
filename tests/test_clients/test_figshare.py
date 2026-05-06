"""Tests for the Figshare REST API client."""

from __future__ import annotations

import httpx
import pytest
import respx

from opencite.clients.figshare import FigshareClient
from opencite.clients.preprint_base import FulltextRoute
from opencite.config import Config
from opencite.models import IDSet, Paper

_BASE = "https://api.figshare.com"

_FIGSHARE_SUMMARY = {"id": 999, "title": "A Figshare preprint"}

_FIGSHARE_FULL = {
    "id": 999,
    "title": "A Figshare preprint",
    "doi": "10.6084/m9.figshare.999",
    "description": "<div>Some <b>methods</b>.</div>",
    "published_date": "2024-08-15T00:00:00Z",
    "authors": [
        {"full_name": "Jane Smith"},
        {"full_name": "John Doe"},
    ],
    "tags": ["preprint", "physics"],
    "files": [
        {
            "name": "manuscript.pdf",
            "download_url": "https://ndownloader.figshare.com/files/12345",
        },
        {"name": "supplement.zip", "download_url": "ignored"},
    ],
    "figshare_url": "https://figshare.com/articles/preprint/A_Figshare_preprint/999",
}


class TestFigshareParse:
    def _client(self) -> FigshareClient:
        return FigshareClient(Config())

    def test_parse_article_basic(self):
        paper = self._client()._parse_article(_FIGSHARE_FULL)
        assert paper is not None
        assert paper.title == "A Figshare preprint"
        assert paper.ids.doi == "10.6084/m9.figshare.999"
        assert paper.year == 2024
        assert "figshare" in paper.data_sources

    def test_parse_article_strips_html(self):
        paper = self._client()._parse_article(_FIGSHARE_FULL)
        assert paper is not None
        assert "<div>" not in paper.abstract
        assert "methods" in paper.abstract

    def test_parse_article_only_pdf_files_kept(self):
        paper = self._client()._parse_article(_FIGSHARE_FULL)
        assert paper is not None
        urls = [loc.url for loc in paper.pdf_locations]
        assert any("12345" in u for u in urls)
        assert not any("supplement" in u for u in urls)

    def test_parse_article_authors(self):
        paper = self._client()._parse_article(_FIGSHARE_FULL)
        assert paper is not None
        assert len(paper.authors) == 2
        assert paper.authors[0].family_name == "Smith"

    def test_fulltext_route_is_none(self):
        client = self._client()
        paper = Paper(title="x", ids=IDSet(doi="10.6084/m9.figshare.999"))
        assert client.fulltext_route(paper) == FulltextRoute.NONE


class TestFigshareNetwork:
    @pytest.mark.asyncio
    @respx.mock
    async def test_search_fetches_full_records(self):
        respx.post(f"{_BASE}/v2/articles/search").mock(
            return_value=httpx.Response(200, json=[_FIGSHARE_SUMMARY])
        )
        respx.get(f"{_BASE}/v2/articles/999").mock(
            return_value=httpx.Response(200, json=_FIGSHARE_FULL)
        )
        async with FigshareClient(Config()) as client:
            papers = await client.search("preprint")
        assert len(papers) == 1
        assert papers[0].ids.doi == "10.6084/m9.figshare.999"

    @pytest.mark.asyncio
    @respx.mock
    async def test_lookup_doi(self):
        respx.get(f"{_BASE}/v2/articles").mock(
            return_value=httpx.Response(200, json=[_FIGSHARE_SUMMARY])
        )
        respx.get(f"{_BASE}/v2/articles/999").mock(
            return_value=httpx.Response(200, json=_FIGSHARE_FULL)
        )
        async with FigshareClient(Config()) as client:
            paper = await client.lookup_doi("10.6084/m9.figshare.999")
        assert paper is not None

    @pytest.mark.asyncio
    async def test_lookup_doi_non_figshare_short_circuits(self):
        async with FigshareClient(Config()) as client:
            with respx.mock(assert_all_called=False) as mock:
                assert await client.lookup_doi("10.1038/nature12373") is None
                assert not mock.routes
