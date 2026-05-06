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

from opencite.clients.biorxiv import BioRxivClient
from opencite.clients.medrxiv import MedRxivClient
from opencite.config import Config

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
