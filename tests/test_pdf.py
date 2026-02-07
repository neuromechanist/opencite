"""Tests for PDF retrieval module."""

from __future__ import annotations

import pytest

from opencite.models import Author, IDSet, Paper, PDFLocation
from opencite.pdf import PDFRetriever


class TestCollectUrls:
    def test_pdf_locations_first(self):
        paper = Paper(
            title="Test",
            ids=IDSet(doi="10.1234/test"),
            pdf_locations=[
                PDFLocation(url="https://example.com/paper.pdf", source="s2"),
            ],
        )
        retriever = PDFRetriever.__new__(PDFRetriever)
        urls = retriever._collect_urls(paper, "10.1234/test")
        assert urls[0] == "https://example.com/paper.pdf"

    def test_pmc_url_added(self):
        paper = Paper(
            title="Test",
            ids=IDSet(pmcid="PMC12345"),
        )
        retriever = PDFRetriever.__new__(PDFRetriever)
        urls = retriever._collect_urls(paper, "PMC12345")
        assert any("PMC12345" in u for u in urls)

    def test_doi_url_added(self):
        paper = Paper(
            title="Test",
            ids=IDSet(doi="10.1234/test"),
        )
        retriever = PDFRetriever.__new__(PDFRetriever)
        urls = retriever._collect_urls(paper, "10.1234/test")
        assert "https://doi.org/10.1234/test" in urls

    def test_no_paper_doi_fallback(self):
        retriever = PDFRetriever.__new__(PDFRetriever)
        urls = retriever._collect_urls(None, "10.1234/test")
        assert "https://doi.org/10.1234/test" in urls

    def test_no_paper_non_doi(self):
        retriever = PDFRetriever.__new__(PDFRetriever)
        urls = retriever._collect_urls(None, "some_invalid_id")
        assert urls == []

    def test_no_duplicate_urls(self):
        paper = Paper(
            title="Test",
            ids=IDSet(doi="10.1234/test"),
            pdf_locations=[
                PDFLocation(url="https://doi.org/10.1234/test", source="doi"),
            ],
        )
        retriever = PDFRetriever.__new__(PDFRetriever)
        urls = retriever._collect_urls(paper, "10.1234/test")
        assert urls.count("https://doi.org/10.1234/test") == 1


class TestMakeFilename:
    def test_with_paper(self):
        paper = Paper(
            title="Attention Is All You Need",
            authors=[Author(name="Vaswani", family_name="Vaswani")],
            year=2017,
        )
        retriever = PDFRetriever.__new__(PDFRetriever)
        name = retriever._make_filename(paper, "10.xxx")
        assert "Vaswani" in name
        assert "2017" in name
        assert "Attention" in name

    def test_no_paper(self):
        retriever = PDFRetriever.__new__(PDFRetriever)
        name = retriever._make_filename(None, "10.1234/test.123")
        assert name == "10.1234_test.123"

    def test_no_authors(self):
        paper = Paper(title="Some Title", year=2020)
        retriever = PDFRetriever.__new__(PDFRetriever)
        name = retriever._make_filename(paper, "id")
        assert "2020" in name
        assert "Some" in name


class TestConvertPdf:
    def test_missing_file_raises(self):
        from opencite.convert import convert_pdf

        with pytest.raises(FileNotFoundError):
            convert_pdf("/nonexistent/file.pdf")

    def test_auto_picks_markitdown(self, monkeypatch):
        from opencite.convert import _pick_converter

        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        assert _pick_converter() == "markitdown"

    def test_auto_picks_mistral(self, monkeypatch):
        from opencite.convert import _pick_converter

        monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
        assert _pick_converter() == "mistral"
