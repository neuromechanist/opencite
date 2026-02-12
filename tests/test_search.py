"""Tests for the search orchestrator."""

from __future__ import annotations

import os

import pytest

from opencite.config import Config
from opencite.search import SearchOrchestrator


@pytest.fixture
def config() -> Config:
    return Config.from_env()


def has_all_keys() -> bool:
    """Check if all API keys are available."""
    return all(
        os.environ.get(k)
        for k in ("SEMANTIC_SCHOLAR_API_KEY", "PUBMED_API_KEY", "OPENALEX_API_KEY")
    )


skip_without_all_keys = pytest.mark.skipif(
    not has_all_keys(),
    reason="Not all API keys set",
)


@pytest.mark.integration
@skip_without_all_keys
class TestSearchOrchestrator:
    async def test_search_all_sources(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            result = await searcher.search("deep learning fMRI", max_results=10)
        assert len(result.papers) > 0
        assert result.deduplicated_count >= 0
        # Should have results from at least 2 sources
        all_sources = set()
        for p in result.papers:
            all_sources.update(p.data_sources)
        assert len(all_sources) >= 2

    async def test_search_single_source(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            result = await searcher.search(
                "CRISPR",
                max_results=5,
                sources=["openalex"],
            )
        assert len(result.papers) > 0
        for p in result.papers:
            assert "openalex" in p.data_sources

    async def test_search_deduplicates(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            result = await searcher.search("attention is all you need", max_results=10)
        # Papers should be deduplicated across sources
        assert result.deduplicated_count >= 0

    async def test_search_sort_by_citations(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            result = await searcher.search(
                "transformer",
                max_results=5,
                sort="citations",
            )
        assert len(result.papers) > 0
        # Check citation counts are in descending order
        counts = [p.citation_count for p in result.papers]
        assert counts == sorted(counts, reverse=True)

    async def test_lookup_doi(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            paper = await searcher.lookup("10.1038/s41586-021-03819-2")
        assert paper is not None
        assert paper.title
        assert paper.ids.doi == "10.1038/s41586-021-03819-2"

    async def test_lookup_pmid(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            paper = await searcher.lookup("pmid:34265844")
        assert paper is not None
        assert paper.ids.pmid == "34265844"

    async def test_lookup_with_enrich(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            paper = await searcher.lookup("10.1038/s41586-021-03819-2", enrich=True)
        assert paper is not None
        # Should have data from multiple sources
        assert len(paper.data_sources) >= 2

    async def test_lookup_not_found(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            paper = await searcher.lookup("10.9999/does-not-exist-xyz-abc")
        assert paper is None

    async def test_batch_lookup(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            papers = await searcher.batch_lookup(
                [
                    "10.1038/s41586-021-03819-2",
                    "pmid:34265844",
                ]
            )
        assert len(papers) >= 1

    async def test_source_counts(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            result = await searcher.search(
                "brain computer interface",
                max_results=5,
            )
        assert "openalex" in result.total_by_source
        assert "s2" in result.total_by_source
        assert "pubmed" in result.total_by_source

    async def test_search_with_year_filter(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            result = await searcher.search(
                "neural network",
                max_results=5,
                year_from=2022,
                year_to=2024,
            )
        assert len(result.papers) > 0
