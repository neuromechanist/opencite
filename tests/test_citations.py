"""Tests for opencite.citations (unit tests, no API)."""

from __future__ import annotations

from opencite.citations import _gather_papers, _make_ids, _sort_papers
from opencite.models import IDSet, IDType, Paper


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
