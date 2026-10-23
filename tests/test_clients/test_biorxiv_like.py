"""Tests for shared bioRxiv/medRxiv `lookup_doi` error paths.

`_BiorxivLikePreprintClient.lookup_doi` has four behaviorally distinct
return paths:

1. Successful response with a populated ``collection`` -> Paper.
2. Successful response with empty ``collection`` -> None (DOI not on this server).
3. Non-JSON response body -> None (logged as WARNING).
4. APIError from the underlying HTTP layer (e.g. 5xx after retries) -> None.

These are covered here at the transport level using respx, matching the
existing pattern in ``test_error_paths.py``. Real-API integration coverage
lives in the network-gated integration tests.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from opencite.clients._biorxiv_like import (
    _crossref_item_server,
    _crossref_search_params,
)
from opencite.clients.base import BaseClient
from opencite.clients.biorxiv import BioRxivClient
from opencite.clients.crossref import CrossRefClient
from opencite.clients.medrxiv import MedRxivClient
from opencite.config import Config
from opencite.utils import is_openrxiv_doi

_CONTENT_API_BASE = "https://api.biorxiv.org"


@pytest.fixture
def _config() -> Config:
    # Make retries cheap so error-path tests don't sleep through backoff.
    return Config(max_retries=2, timeout=2.0)


class TestBiorxivLikeLookupDoi:
    @pytest.mark.asyncio
    @respx.mock
    async def test_lookup_doi_success_returns_paper(self, _config: Config):
        doi = "10.1101/2024.01.01.000001"
        respx.get(f"{_CONTENT_API_BASE}/details/biorxiv/{doi}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "collection": [
                        {
                            "doi": doi,
                            "title": "A bioRxiv paper",
                            "authors": "Smith J",
                            "date": "2024-01-01",
                            "version": "1",
                            "abstract": "Methods.",
                            "category": "neuroscience",
                        }
                    ]
                },
            )
        )
        async with BioRxivClient(_config) as client:
            paper = await client.lookup_doi(doi)
        assert paper is not None
        assert paper.title == "A bioRxiv paper"
        assert "biorxiv" in paper.data_sources

    @pytest.mark.asyncio
    @respx.mock
    async def test_lookup_doi_empty_collection_returns_none(self, _config: Config):
        doi = "10.1101/never-existed"
        respx.get(f"{_CONTENT_API_BASE}/details/biorxiv/{doi}").mock(
            return_value=httpx.Response(200, json={"collection": []})
        )
        async with BioRxivClient(_config) as client:
            assert await client.lookup_doi(doi) is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_lookup_doi_non_json_returns_none(self, _config: Config):
        doi = "10.1101/garbage"
        respx.get(f"{_CONTENT_API_BASE}/details/biorxiv/{doi}").mock(
            return_value=httpx.Response(200, content=b"<html>oops</html>")
        )
        async with BioRxivClient(_config) as client:
            assert await client.lookup_doi(doi) is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_lookup_doi_api_error_returns_none(self, _config: Config):
        # 503 retried then 503 again -> APIError -> caught and returns None.
        doi = "10.1101/server-down"
        respx.get(f"{_CONTENT_API_BASE}/details/biorxiv/{doi}").mock(
            return_value=httpx.Response(503)
        )
        async with BioRxivClient(_config) as client:
            assert await client.lookup_doi(doi) is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_medrxiv_routes_to_medrxiv_path(self, _config: Config):
        """MedRxivClient hits /details/medrxiv/, not /details/biorxiv/."""
        doi = "10.1101/2024.05.01.000999"
        biorxiv_route = respx.get(f"{_CONTENT_API_BASE}/details/biorxiv/{doi}").mock(
            return_value=httpx.Response(200, json={"collection": []})
        )
        medrxiv_route = respx.get(f"{_CONTENT_API_BASE}/details/medrxiv/{doi}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "collection": [
                        {
                            "doi": doi,
                            "title": "A medRxiv paper",
                            "authors": "Jones A",
                            "date": "2024-05-01",
                            "version": "1",
                            "abstract": "Trial.",
                            "category": "infectious diseases",
                        }
                    ]
                },
            )
        )
        async with MedRxivClient(_config) as client:
            paper = await client.lookup_doi(doi)
        assert paper is not None
        assert "medrxiv" in paper.data_sources
        assert medrxiv_route.called
        assert not biorxiv_route.called


class TestBiorxivLikeFulltext:
    """Tests for `.full` HTML full-text route on bioRxiv and medRxiv."""

    def test_fulltext_route_html_for_biorxiv_doi(self, _config: Config):
        from opencite.clients.preprint_base import FulltextRoute
        from opencite.models import IDSet, Paper

        client = BioRxivClient(_config)
        paper = Paper(title="A", ids=IDSet(doi="10.1101/2024.01.01.000001"))
        assert client.fulltext_route(paper) == FulltextRoute.HTML

    def test_fulltext_route_html_for_openrxiv_doi(self, _config: Config):
        from opencite.clients.preprint_base import FulltextRoute
        from opencite.models import IDSet, Paper

        client = MedRxivClient(_config)
        paper = Paper(title="A", ids=IDSet(doi="10.64898/2026.09.06.26362366"))
        assert client.fulltext_route(paper) == FulltextRoute.HTML

    def test_fulltext_route_none_without_biorxiv_doi(self, _config: Config):
        from opencite.clients.preprint_base import FulltextRoute
        from opencite.models import IDSet, Paper

        client = BioRxivClient(_config)
        paper = Paper(title="A", ids=IDSet(doi="10.1038/nature12373"))
        assert client.fulltext_route(paper) == FulltextRoute.NONE

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_fulltext_biorxiv_full_html(self, _config: Config):
        from opencite.models import IDSet, Paper

        doi = "10.1101/2024.01.01.000001"
        respx.get(f"https://www.biorxiv.org/content/{doi}.full").mock(
            return_value=httpx.Response(
                200,
                text=(
                    "<html><body><h1>A bioRxiv paper</h1><p>Methods.</p></body></html>"
                ),
            )
        )
        async with BioRxivClient(_config) as client:
            md = await client.fetch_fulltext(Paper(title="x", ids=IDSet(doi=doi)))
        assert md is not None
        assert "bioRxiv paper" in md

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_fulltext_medrxiv_uses_medrxiv_domain(self, _config: Config):
        from opencite.models import IDSet, Paper

        doi = "10.1101/2024.05.01.000999"
        biorxiv_route = respx.get(f"https://www.biorxiv.org/content/{doi}.full").mock(
            return_value=httpx.Response(404)
        )
        medrxiv_route = respx.get(f"https://www.medrxiv.org/content/{doi}.full").mock(
            return_value=httpx.Response(
                200,
                text="<html><body><h1>A medRxiv paper</h1></body></html>",
            )
        )
        async with MedRxivClient(_config) as client:
            md = await client.fetch_fulltext(Paper(title="x", ids=IDSet(doi=doi)))
        assert md is not None
        assert "medRxiv paper" in md
        assert medrxiv_route.called
        assert not biorxiv_route.called

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_fulltext_404_returns_none(self, _config: Config):
        from opencite.models import IDSet, Paper

        doi = "10.1101/withdrawn"
        respx.get(f"https://www.biorxiv.org/content/{doi}.full").mock(
            return_value=httpx.Response(404)
        )
        async with BioRxivClient(_config) as client:
            md = await client.fetch_fulltext(Paper(title="x", ids=IDSet(doi=doi)))
        assert md is None

    @pytest.mark.asyncio
    async def test_fetch_fulltext_no_doi_returns_none(self, _config: Config):
        from opencite.models import IDSet, Paper

        async with BioRxivClient(_config) as client:
            md = await client.fetch_fulltext(Paper(title="x", ids=IDSet()))
        assert md is None


class TestCrossrefItemServer:
    """Server attribution for CrossRef 10.1101 records."""

    # Shape of a current openRxiv deposit (no container-title), trimmed
    # from a live CrossRef response.
    _OPENRXIV_MEDRXIV_ITEM = {
        "DOI": "10.1101/2021.02.05.21251139",
        "type": "posted-content",
        "subtype": "preprint",
        "publisher": "openRxiv",
        "institution": [{"name": "medRxiv"}],
        "group-title": "Health Informatics",
        "resource": {
            "primary": {
                "URL": "http://medrxiv.org/lookup/doi/10.1101/2021.02.05.21251139"
            }
        },
    }
    _OPENRXIV_BIORXIV_ITEM = {
        "DOI": "10.1101/450023",
        "type": "posted-content",
        "publisher": "openRxiv",
        "group-title": "Neuroscience",
        "resource": {
            "primary": {"URL": "http://biorxiv.org/lookup/doi/10.1101/450023"}
        },
    }

    def test_openrxiv_medrxiv_by_resource_url(self):
        assert _crossref_item_server(self._OPENRXIV_MEDRXIV_ITEM) == "medrxiv"

    def test_openrxiv_biorxiv_by_resource_url(self):
        assert _crossref_item_server(self._OPENRXIV_BIORXIV_ITEM) == "biorxiv"

    def test_legacy_container_title(self):
        assert _crossref_item_server({"container-title": ["medRxiv"]}) == "medrxiv"

    def test_unknown_defaults_to_biorxiv(self):
        assert _crossref_item_server({}) == "biorxiv"


class TestCrossrefSearchParams:
    def test_filter_covers_both_owner_prefixes(self):
        params = _crossref_search_params("memory")
        assert params["filter"] == (
            "prefix:10.1101,prefix:10.64898,type:posted-content"
        )
        assert "resource" in params["select"].split(",")
        assert params["query.bibliographic"] == "memory"


class TestSharedCrossrefSearch:
    """bioRxiv and medRxiv search through one shared CrossRefClient budget."""

    def setup_method(self):
        BaseClient.reset_shared_limiters()
        CrossRefClient._inflight.clear()

    def teardown_method(self):
        BaseClient.reset_shared_limiters()

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_is_retried_and_identical_queries_coalesce(self, _config):
        import asyncio

        items = [
            TestCrossrefItemServer._OPENRXIV_BIORXIV_ITEM | {"title": ["B paper"]},
            TestCrossrefItemServer._OPENRXIV_MEDRXIV_ITEM | {"title": ["M paper"]},
        ]
        route = respx.get("https://api.crossref.org/works").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(200, json={"message": {"items": items}}),
            ]
        )
        async with BioRxivClient(_config) as bio, MedRxivClient(_config) as med:
            bio_papers, med_papers = await asyncio.gather(
                bio.search("memory"), med.search("memory")
            )
        # One 429 plus one successful request serve both servers.
        assert route.call_count == 2
        assert [p.title for p in bio_papers] == ["B paper"]
        assert [p.title for p in med_papers] == ["M paper"]


@pytest.mark.integration
class TestBiorxivLikeSearchLive:
    """Keyword search through CrossRef must find openRxiv-deposited preprints."""

    async def test_biorxiv_search_returns_biorxiv_preprints(self):
        async with BioRxivClient(Config()) as client:
            papers = await client.search("working memory training", max_results=5)
        assert papers
        assert all(is_openrxiv_doi(p.ids.doi) for p in papers)
        assert all("biorxiv" in p.data_sources for p in papers)

    async def test_medrxiv_search_returns_medrxiv_preprints(self):
        async with MedRxivClient(Config()) as client:
            papers = await client.search("covid vaccine effectiveness", max_results=5)
        assert papers
        assert all("medrxiv" in p.data_sources for p in papers)
