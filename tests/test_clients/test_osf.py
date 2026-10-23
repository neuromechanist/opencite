"""Tests for the OSF Preprints API client."""

from __future__ import annotations

import httpx
import pytest
import respx

from opencite.clients.osf import OSFClient, _share_result_ids
from opencite.clients.preprint_base import FulltextRoute
from opencite.config import Config
from opencite.models import IDSet, Paper

_BASE = "https://api.osf.io"

# Trimmed from a real SHARE index-card-search response for
# "working memory training" (resourceType=Preprint, accessService=osf.io).
_SHARE_PAYLOAD = {
    "data": {
        "type": "index-card-search",
        "relationships": {
            "searchResultPage": {
                "data": [
                    {"id": "1792737315630356280-0", "type": "search-result"},
                    {"id": "1792737315630356280-1", "type": "search-result"},
                ]
            }
        },
    },
    "included": [
        # Ranked second, listed first: order must come from searchResultPage.
        {
            "id": "b918a31c-c751-42ef-95bc-b061aa08f319",
            "type": "index-card",
            "attributes": {"resourceMetadata": {"@id": "https://osf.io/9fe8n"}},
        },
        {
            "id": "1792737315630356280-1",
            "type": "search-result",
            "relationships": {
                "indexCard": {
                    "data": {
                        "id": "b918a31c-c751-42ef-95bc-b061aa08f319",
                        "type": "index-card",
                    }
                }
            },
        },
        {
            "id": "1792737315630356280-0",
            "type": "search-result",
            "relationships": {
                "indexCard": {
                    "data": {
                        "id": "653c4e54-d1a0-43f9-b5e0-11faa00c25f4",
                        "type": "index-card",
                    }
                }
            },
        },
        {
            "id": "653c4e54-d1a0-43f9-b5e0-11faa00c25f4",
            "type": "index-card",
            "attributes": {"resourceMetadata": {"@id": "https://osf.io/g6dhv"}},
        },
    ],
}

# Realistic shape based on the public OSF API: ``attributes.doi`` is None
# for many published preprints and the canonical DOI lives in
# ``links.preprint_doi`` as a doi.org URL.
_OSF_ITEM = {
    "id": "abc12",
    "type": "preprints",
    "attributes": {
        "title": "A PsyArXiv preprint on memory",
        "description": "We studied working memory in 30 participants.",
        "date_published": "2024-03-15T00:00:00.000Z",
        "doi": None,
        "tags": ["working memory", "psychology"],
    },
    "relationships": {
        "provider": {"data": {"id": "psyarxiv", "type": "preprint-providers"}},
    },
    "links": {
        "html": "https://osf.io/preprints/psyarxiv/abc12",
        "preprint_doi": "https://doi.org/10.31234/osf.io/abc12",
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

    def test_parse_item_pdf_location_uses_id_redirect(self):
        """OSF preprint downloads use the `osf.io/download/{id}` redirect."""
        paper = self._client()._parse_item(_OSF_ITEM)
        assert paper is not None
        assert paper.best_pdf_url == "https://osf.io/download/abc12"

    def test_parse_item_doi_falls_back_to_preprint_doi_link(self):
        """When `attributes.doi` is None, parse `links.preprint_doi` URL."""
        paper = self._client()._parse_item(_OSF_ITEM)
        assert paper is not None
        assert paper.ids.doi == "10.31234/osf.io/abc12"

    def test_parse_item_no_doi(self):
        """A preprint with no DOI anywhere still parses (title-only Paper)."""
        item = {
            **_OSF_ITEM,
            "attributes": {**_OSF_ITEM["attributes"], "doi": None},
            "links": {"html": "https://osf.io/preprints/psyarxiv/abc12"},
        }
        paper = self._client()._parse_item(item)
        assert paper is not None
        assert paper.ids.doi == ""
        assert paper.title

    def test_is_osf_doi_handles_provider_prefixes(self):
        from opencite.clients.osf import OSFClient

        for doi in (
            "10.31234/osf.io/abc12",  # PsyArXiv
            "10.31219/osf.io/jdkau",  # OSF Preprints
            "10.31222/osf.io/socx1",  # SocArXiv
            "10.31234/OSF.IO/UPPER",  # case insensitive
        ):
            assert OSFClient.is_osf_doi(doi), doi
        assert not OSFClient.is_osf_doi("10.1038/nature12373")

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


class TestShareResultIds:
    def test_extracts_ids_in_rank_order(self):
        assert _share_result_ids(_SHARE_PAYLOAD) == ["g6dhv", "9fe8n"]

    def test_empty_payload(self):
        assert _share_result_ids({"data": {}, "included": []}) == []

    def test_skips_non_osf_resources(self):
        payload = {
            "data": {
                "relationships": {
                    "searchResultPage": {
                        "data": [{"id": "r0", "type": "search-result"}]
                    }
                }
            },
            "included": [
                {
                    "id": "r0",
                    "type": "search-result",
                    "relationships": {
                        "indexCard": {"data": {"id": "c0", "type": "index-card"}}
                    },
                },
                {
                    "id": "c0",
                    "type": "index-card",
                    "attributes": {
                        "resourceMetadata": {"@id": "https://example.org/x"}
                    },
                },
            ],
        }
        assert _share_result_ids(payload) == []


@pytest.mark.integration
class TestOSFSearchLive:
    """Live search through SHARE + the OSF v2 API (no key required)."""

    async def test_search_returns_ranked_osf_preprints(self):
        async with OSFClient(Config()) as client:
            papers = await client.search("working memory training", max_results=5)
        assert 0 < len(papers) <= 5
        assert all(any(s.startswith("osf:") for s in p.data_sources) for p in papers)
        assert any("memory" in p.title.lower() for p in papers)

    async def test_provider_filter_restricts_results(self):
        async with OSFClient(Config()) as client:
            papers = await client.search(
                "inequality", max_results=5, provider="socarxiv"
            )
        assert papers
        assert all("osf:socarxiv" in p.data_sources for p in papers)


class TestOSFNetwork:
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
