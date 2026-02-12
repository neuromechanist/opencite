"""Tests for the OpenAlex API client."""

from __future__ import annotations

import pytest

from opencite.clients.openalex import OpenAlexClient
from opencite.config import Config
from tests.conftest import skip_without_openalex_key


@pytest.fixture
def config() -> Config:
    return Config.from_env()


@pytest.mark.integration
@skip_without_openalex_key
class TestOpenAlexClient:
    """Integration tests for OpenAlexClient (requires OPENALEX_API_KEY)."""

    async def test_search_returns_papers(self, config: Config):
        async with OpenAlexClient(config) as client:
            papers = await client.search(
                "transformer attention mechanism", max_results=5
            )
        assert len(papers) > 0
        paper = papers[0]
        assert paper.title
        assert "openalex" in paper.data_sources

    async def test_search_with_year_filter(self, config: Config):
        async with OpenAlexClient(config) as client:
            papers = await client.search(
                "deep learning",
                max_results=5,
                year_from=2020,
                year_to=2022,
            )
        assert len(papers) > 0
        for p in papers:
            if p.year:
                assert 2020 <= p.year <= 2022

    async def test_search_oa_only(self, config: Config):
        async with OpenAlexClient(config) as client:
            papers = await client.search(
                "machine learning", max_results=5, oa_only=True
            )
        assert len(papers) > 0
        for p in papers:
            assert p.is_oa

    async def test_lookup_doi(self, config: Config):
        async with OpenAlexClient(config) as client:
            paper = await client.lookup_doi("10.1038/s41586-021-03819-2")
        assert paper is not None
        assert paper.title
        assert paper.ids.doi == "10.1038/s41586-021-03819-2"

    async def test_lookup_doi_not_found(self, config: Config):
        async with OpenAlexClient(config) as client:
            paper = await client.lookup_doi("10.9999/does-not-exist-xyz")
        assert paper is None

    async def test_lookup_pmid(self, config: Config):
        # PMID 34265844 = "Highly accurate protein structure prediction with AlphaFold"
        async with OpenAlexClient(config) as client:
            paper = await client.lookup_pmid("34265844")
        assert paper is not None
        assert paper.title
        assert paper.ids.pmid == "34265844"

    async def test_citing_papers(self, config: Config):
        async with OpenAlexClient(config) as client:
            # First look up a well-cited paper to get OpenAlex ID
            paper = await client.lookup_doi("10.1038/s41586-021-03819-2")
            assert paper is not None
            oa_id = paper.ids.openalex_id
            assert oa_id

            citing = await client.citing_papers(oa_id, max_results=5)
        assert len(citing) > 0

    async def test_references(self, config: Config):
        async with OpenAlexClient(config) as client:
            paper = await client.lookup_doi("10.1038/s41586-021-03819-2")
            assert paper is not None
            oa_id = paper.ids.openalex_id

            refs = await client.references(oa_id, max_results=5)
        assert len(refs) > 0

    async def test_canonical_search(self, config: Config):
        async with OpenAlexClient(config) as client:
            papers = await client.canonical_search(
                "deep learning",
                max_results=5,
                min_citations=1000,
            )
        assert len(papers) > 0
        for p in papers:
            assert p.citation_count >= 1000

    async def test_batch_lookup_dois(self, config: Config):
        dois = [
            "10.1038/s41586-021-03819-2",
            "10.1126/science.abj8754",
        ]
        async with OpenAlexClient(config) as client:
            papers = await client.batch_lookup_dois(dois)
        assert len(papers) >= 1

    async def test_paper_has_authors(self, config: Config):
        async with OpenAlexClient(config) as client:
            paper = await client.lookup_doi("10.1038/s41586-021-03819-2")
        assert paper is not None
        assert len(paper.authors) > 0
        assert paper.authors[0].name
        assert paper.authors[0].family_name

    async def test_paper_has_source_venue(self, config: Config):
        async with OpenAlexClient(config) as client:
            paper = await client.lookup_doi("10.1038/s41586-021-03819-2")
        assert paper is not None
        assert paper.source_venue is not None
        assert paper.source_venue.name

    async def test_search_sort_by_citations(self, config: Config):
        async with OpenAlexClient(config) as client:
            papers = await client.search(
                "neural network", max_results=5, sort="citations"
            )
        assert len(papers) > 0
        # First result should have high citation count
        assert papers[0].citation_count > 0
