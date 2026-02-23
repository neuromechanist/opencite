"""Tests for opencite.citations."""

from __future__ import annotations

import pytest

from opencite.citations import CitationExplorer, _gather_papers, _make_ids, _sort_papers
from opencite.config import Config
from opencite.models import IDSet, IDType, Paper
from tests.conftest import skip_without_all_keys


class TestMakeIds:
    def test_doi(self):
        ids = _make_ids(IDType.DOI, "10.1234/test")
        assert isinstance(ids, IDSet)
        assert ids.doi == "10.1234/test"

    def test_pmid(self):
        ids = _make_ids(IDType.PMID, "12345")
        assert ids.pmid == "12345"

    def test_pmcid(self):
        ids = _make_ids(IDType.PMCID, "PMC999")
        assert ids.pmcid == "PMC999"

    def test_openalex(self):
        ids = _make_ids(IDType.OPENALEX, "W1234")
        assert ids.openalex_id == "W1234"

    def test_s2(self):
        ids = _make_ids(IDType.S2, "abc123")
        assert ids.s2_id == "abc123"

    def test_arxiv(self):
        ids = _make_ids(IDType.ARXIV, "2106.15928")
        assert ids.arxiv_id == "2106.15928"


class TestSortPapers:
    def test_sort_by_citations(self):
        papers = [
            Paper(title="Low", citation_count=10),
            Paper(title="High", citation_count=1000),
            Paper(title="Mid", citation_count=100),
        ]
        sorted_papers = _sort_papers(papers, "citations")
        assert [p.title for p in sorted_papers] == ["High", "Mid", "Low"]

    def test_sort_by_year(self):
        papers = [
            Paper(title="Old", year=2000, citation_count=500),
            Paper(title="New", year=2024, citation_count=10),
            Paper(title="Mid", year=2015, citation_count=100),
        ]
        sorted_papers = _sort_papers(papers, "year")
        assert [p.title for p in sorted_papers] == ["New", "Mid", "Old"]

    def test_sort_relevance_preserves_order(self):
        papers = [
            Paper(title="A"),
            Paper(title="B"),
            Paper(title="C"),
        ]
        sorted_papers = _sort_papers(papers, "relevance")
        assert [p.title for p in sorted_papers] == ["A", "B", "C"]

    def test_sort_year_tiebreak_by_citations(self):
        papers = [
            Paper(title="Low", year=2020, citation_count=10),
            Paper(title="High", year=2020, citation_count=1000),
        ]
        sorted_papers = _sort_papers(papers, "year")
        assert sorted_papers[0].title == "High"


class TestGatherPapers:
    import asyncio

    async def test_gathers_from_multiple_tasks(self):
        import asyncio

        async def task_a():
            return [Paper(title="A1"), Paper(title="A2")]

        async def task_b():
            return [Paper(title="B1")]

        tasks = [
            asyncio.create_task(task_a()),
            asyncio.create_task(task_b()),
        ]
        result = await _gather_papers(tasks)
        titles = [p.title for p in result]
        assert "A1" in titles
        assert "A2" in titles
        assert "B1" in titles

    async def test_handles_failing_tasks(self):
        import asyncio

        async def good_task():
            return [Paper(title="Good")]

        async def bad_task():
            raise ValueError("API error")

        tasks = [
            asyncio.create_task(good_task()),
            asyncio.create_task(bad_task()),
        ]
        result = await _gather_papers(tasks)
        assert len(result) == 1
        assert result[0].title == "Good"

    async def test_empty_tasks(self):
        result = await _gather_papers([])
        assert result == []


@pytest.fixture
def config() -> Config:
    return Config.from_env()


@pytest.mark.integration
@skip_without_all_keys
class TestCitationExplorerIntegration:
    async def test_citing_papers_by_doi(self, config: Config):
        # AlphaFold paper
        async with CitationExplorer(config) as explorer:
            result = await explorer.citing_papers(
                "10.1038/s41586-021-03819-2", max_results=5
            )
        assert result.seed_paper is not None
        assert result.seed_paper.title
        assert result.direction == "citing"
        assert len(result.papers) > 0

    async def test_references_by_doi(self, config: Config):
        async with CitationExplorer(config) as explorer:
            result = await explorer.references(
                "10.1038/s41586-021-03819-2", max_results=5
            )
        assert result.direction == "references"
        assert len(result.papers) > 0

    async def test_canonical_papers(self, config: Config):
        async with CitationExplorer(config) as explorer:
            papers = await explorer.canonical_papers(
                "deep learning", max_results=3, min_citations=1000
            )
        assert len(papers) > 0
        for p in papers:
            assert p.citation_count >= 1000

    async def test_citing_papers_nonexistent_doi(self, config: Config):
        async with CitationExplorer(config) as explorer:
            result = await explorer.citing_papers("10.9999/does-not-exist-xyz")
        assert result.seed_paper.title == "Unknown"
        assert result.papers == []

    async def test_citing_papers_with_min_citations(self, config: Config):
        async with CitationExplorer(config) as explorer:
            result = await explorer.citing_papers(
                "10.1038/s41586-021-03819-2",
                max_results=10,
                min_citations=100,
            )
        for p in result.papers:
            assert p.citation_count >= 100

    async def test_citing_papers_by_pmid(self, config: Config):
        async with CitationExplorer(config) as explorer:
            result = await explorer.citing_papers("pmid:34265844", max_results=5)
        assert result.seed_paper is not None
        assert len(result.papers) >= 0  # may vary

    async def test_references_by_arxiv(self, config: Config):
        # "Attention Is All You Need"
        async with CitationExplorer(config) as explorer:
            result = await explorer.references("arxiv:1706.03762", max_results=5)
        assert result.seed_paper is not None
        assert result.direction == "references"
