"""Tests for full-text retrieval pipeline."""

from __future__ import annotations

from opencite.fulltext import FullTextRetriever
from opencite.models import IDSet, Paper


class TestResolvePmcid:
    def _make_retriever(self):
        retriever = FullTextRetriever.__new__(FullTextRetriever)
        return retriever

    def test_from_paper_pmcid(self):
        retriever = self._make_retriever()
        paper = Paper(title="Test", ids=IDSet(pmcid="PMC12345"))
        assert retriever._resolve_pmcid("10.1234/test", paper) == "PMC12345"

    def test_from_identifier_pmcid(self):
        retriever = self._make_retriever()
        assert retriever._resolve_pmcid("pmc:12345", None) == "PMC12345"

    def test_bare_pmcid(self):
        retriever = self._make_retriever()
        assert retriever._resolve_pmcid("PMC12345", None) == "PMC12345"

    def test_doi_returns_none(self):
        retriever = self._make_retriever()
        assert retriever._resolve_pmcid("10.1234/test", None) is None

    def test_paper_without_pmcid(self):
        retriever = self._make_retriever()
        paper = Paper(title="Test", ids=IDSet(doi="10.1234/test"))
        assert retriever._resolve_pmcid("10.1234/test", paper) is None

    def test_invalid_identifier(self):
        retriever = self._make_retriever()
        assert retriever._resolve_pmcid("not_valid", None) is None


class TestMakeFilename:
    def _make_retriever(self):
        retriever = FullTextRetriever.__new__(FullTextRetriever)
        return retriever

    def test_with_paper_metadata(self):
        from opencite.models import Author

        retriever = self._make_retriever()
        paper = Paper(
            title="Attention Is All You Need",
            authors=[Author(name="Vaswani", family_name="Vaswani")],
            year=2017,
        )
        name = retriever._make_filename(paper, "10.xxx")
        assert "Vaswani" in name
        assert "2017" in name
        assert "Attention" in name

    def test_without_paper(self):
        retriever = self._make_retriever()
        name = retriever._make_filename(None, "10.1234/test")
        assert "10.1234" in name or "10_1234" in name

    def test_sanitizes_special_chars(self):
        retriever = self._make_retriever()
        name = retriever._make_filename(None, "10.1234/some.test/thing")
        assert "/" not in name
