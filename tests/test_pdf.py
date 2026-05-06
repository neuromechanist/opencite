"""Tests for PDF retrieval module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from opencite.config import Config
from opencite.models import Author, IDSet, Paper, PDFLocation
from opencite.pdf import _PUBLISHER_MAP, PDFRetriever


def _make_retriever(**config_kwargs):
    retriever = PDFRetriever.__new__(PDFRetriever)
    retriever.config = Config(**config_kwargs)
    # Mock the unpaywall client to avoid real API calls
    retriever._unpaywall = MagicMock()
    retriever._unpaywall.lookup_doi = AsyncMock(return_value=[])
    return retriever


class TestCollectUrls:
    @pytest.mark.asyncio
    async def test_pdf_locations_first(self):
        paper = Paper(
            title="Test",
            ids=IDSet(doi="10.1234/test"),
            pdf_locations=[
                PDFLocation(url="https://example.com/paper.pdf", source="s2"),
            ],
        )
        retriever = _make_retriever()
        urls = await retriever._collect_urls(paper, "10.1234/test")
        assert urls[0] == "https://example.com/paper.pdf"

    @pytest.mark.asyncio
    async def test_pmc_url_added(self):
        paper = Paper(
            title="Test",
            ids=IDSet(pmcid="PMC12345"),
        )
        retriever = _make_retriever()
        urls = await retriever._collect_urls(paper, "PMC12345")
        assert any("PMC12345" in u for u in urls)

    @pytest.mark.asyncio
    async def test_doi_url_added(self):
        paper = Paper(
            title="Test",
            ids=IDSet(doi="10.1234/test"),
        )
        retriever = _make_retriever()
        urls = await retriever._collect_urls(paper, "10.1234/test")
        assert "https://doi.org/10.1234/test" in urls

    @pytest.mark.asyncio
    async def test_no_paper_doi_fallback(self):
        retriever = _make_retriever()
        urls = await retriever._collect_urls(None, "10.1234/test")
        assert "https://doi.org/10.1234/test" in urls

    @pytest.mark.asyncio
    async def test_no_paper_non_doi(self):
        retriever = _make_retriever()
        urls = await retriever._collect_urls(None, "some_invalid_id")
        assert urls == []

    @pytest.mark.asyncio
    async def test_no_duplicate_urls(self):
        paper = Paper(
            title="Test",
            ids=IDSet(doi="10.1234/test"),
            pdf_locations=[
                PDFLocation(url="https://doi.org/10.1234/test", source="doi"),
            ],
        )
        retriever = _make_retriever()
        urls = await retriever._collect_urls(paper, "10.1234/test")
        assert urls.count("https://doi.org/10.1234/test") == 1


class TestPublisherUrls:
    @pytest.mark.asyncio
    async def test_elsevier_url_added_with_key(self):
        retriever = _make_retriever(elsevier_api_key="els_test")
        paper = Paper(title="Test", ids=IDSet(doi="10.1016/j.test.2024"))
        urls = await retriever._collect_urls(paper, "10.1016/j.test.2024")
        assert any("api.elsevier.com" in u for u in urls)
        # Publisher URL should be first (highest priority)
        assert "api.elsevier.com" in urls[0]

    @pytest.mark.asyncio
    async def test_elsevier_url_not_added_without_key(self):
        retriever = _make_retriever()
        paper = Paper(title="Test", ids=IDSet(doi="10.1016/j.test.2024"))
        urls = await retriever._collect_urls(paper, "10.1016/j.test.2024")
        assert not any("api.elsevier.com" in u for u in urls)

    @pytest.mark.asyncio
    async def test_wiley_url_added_with_key(self):
        retriever = _make_retriever(wiley_tdm_token="wiley_test")
        paper = Paper(title="Test", ids=IDSet(doi="10.1002/test.123"))
        urls = await retriever._collect_urls(paper, "10.1002/test.123")
        assert any("api.wiley.com" in u for u in urls)

    @pytest.mark.asyncio
    async def test_springer_url_added_with_key(self):
        retriever = _make_retriever(springer_api_key="springer_test")
        paper = Paper(title="Test", ids=IDSet(doi="10.1007/s123-test"))
        urls = await retriever._collect_urls(paper, "10.1007/s123-test")
        assert any("api.springernature.com" in u for u in urls)

    @pytest.mark.asyncio
    async def test_springer_nature_prefix(self):
        retriever = _make_retriever(springer_api_key="springer_test")
        paper = Paper(title="Test", ids=IDSet(doi="10.1038/nature12345"))
        urls = await retriever._collect_urls(paper, "10.1038/nature12345")
        assert any("api.springernature.com" in u for u in urls)

    @pytest.mark.asyncio
    async def test_unknown_publisher_no_extra_urls(self):
        retriever = _make_retriever(elsevier_api_key="test")
        paper = Paper(title="Test", ids=IDSet(doi="10.9999/unknown"))
        urls = await retriever._collect_urls(paper, "10.9999/unknown")
        assert not any("api.elsevier.com" in u for u in urls)
        assert not any("api.wiley.com" in u for u in urls)


class TestArXivBioRxivURLs:
    """Tests for direct preprint download URL injection."""

    @pytest.mark.asyncio
    async def test_arxiv_pdf_url_added_from_arxiv_id(self):
        paper = Paper(title="Test", ids=IDSet(arxiv_id="1706.03762"))
        retriever = _make_retriever()
        urls = await retriever._collect_urls(paper, "1706.03762")
        assert "https://arxiv.org/pdf/1706.03762" in urls

    @pytest.mark.asyncio
    async def test_arxiv_pdf_url_not_duplicated(self):
        paper = Paper(
            title="Test",
            ids=IDSet(arxiv_id="1706.03762"),
            pdf_locations=[
                PDFLocation(url="https://arxiv.org/pdf/1706.03762", source="arxiv"),
            ],
        )
        retriever = _make_retriever()
        urls = await retriever._collect_urls(paper, "1706.03762")
        assert urls.count("https://arxiv.org/pdf/1706.03762") == 1

    @pytest.mark.asyncio
    async def test_biorxiv_pdf_url_added_for_10_1101_doi(self):
        paper = Paper(title="Test", ids=IDSet(doi="10.1101/837021"))
        retriever = _make_retriever()
        urls = await retriever._collect_urls(paper, "10.1101/837021")
        biorxiv_urls = [u for u in urls if "biorxiv.org" in u]
        assert len(biorxiv_urls) == 1
        assert "10.1101/837021" in biorxiv_urls[0]

    @pytest.mark.asyncio
    async def test_biorxiv_pdf_url_before_doi_negotiation(self):
        """Direct bioRxiv URL should appear before generic DOI URL."""
        paper = Paper(title="Test", ids=IDSet(doi="10.1101/837021"))
        retriever = _make_retriever()
        urls = await retriever._collect_urls(paper, "10.1101/837021")
        biorxiv_idx = next(i for i, u in enumerate(urls) if "biorxiv.org" in u)
        doi_idx = next(i for i, u in enumerate(urls) if "doi.org" in u)
        assert biorxiv_idx < doi_idx

    @pytest.mark.asyncio
    async def test_non_biorxiv_doi_has_no_biorxiv_url(self):
        paper = Paper(title="Test", ids=IDSet(doi="10.1038/nature12345"))
        retriever = _make_retriever()
        urls = await retriever._collect_urls(paper, "10.1038/nature12345")
        assert not any("biorxiv.org" in u for u in urls)

    @pytest.mark.asyncio
    async def test_medrxiv_url_used_when_data_source_is_medrxiv(self):
        """Papers with medrxiv in data_sources get medrxiv.org URL, not biorxiv.org."""
        from opencite.models import Source

        paper = Paper(
            title="Test",
            ids=IDSet(doi="10.1101/2021.01.01.12345"),
            data_sources={"medrxiv"},
            source_venue=Source(name="medRxiv", is_oa=True),
        )
        retriever = _make_retriever()
        urls = await retriever._collect_urls(paper, "10.1101/2021.01.01.12345")
        medrxiv_urls = [u for u in urls if "medrxiv.org" in u]
        assert len(medrxiv_urls) == 1
        assert not any("biorxiv.org" in u for u in urls)


class TestPublisherMap:
    def test_elsevier_prefix(self):
        assert "10.1016" in _PUBLISHER_MAP

    def test_wiley_prefix(self):
        assert "10.1002" in _PUBLISHER_MAP

    def test_springer_prefix(self):
        assert "10.1007" in _PUBLISHER_MAP


class TestReportFailures:
    def _make_retriever(self):
        retriever = PDFRetriever.__new__(PDFRetriever)
        retriever.config = Config()
        return retriever

    def test_empty_failures(self, capsys):
        retriever = self._make_retriever()
        retriever._report_failures("10.1234/test", [], None)
        captured = capsys.readouterr()
        assert "no sources attempted" in captured.err

    def test_failures_with_reasons(self, capsys):
        retriever = self._make_retriever()
        failures = [
            ("https://example.com/paper.pdf", "403 Forbidden/Unauthorized"),
            ("https://doi.org/10.1234/test", "timeout"),
        ]
        retriever._report_failures("10.1234/test", failures, None)
        captured = capsys.readouterr()
        assert "Tried 2 source(s)" in captured.err
        assert "403 Forbidden" in captured.err
        assert "timeout" in captured.err

    def test_suggests_institutional_access(self, capsys):
        retriever = self._make_retriever()
        paper = Paper(title="Test", ids=IDSet(doi="10.1234/test"))
        failures = [("https://example.com", "404 Not Found")]
        retriever._report_failures("10.1234/test", failures, paper)
        captured = capsys.readouterr()
        assert "Institutional access" in captured.err


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


class TestMakeFilenameEdgeCases:
    def test_author_name_only(self):
        """When author has no family_name, uses name field."""
        paper = Paper(
            title="Some Title",
            authors=[Author(name="J. Smith")],
            year=2020,
        )
        retriever = PDFRetriever.__new__(PDFRetriever)
        name = retriever._make_filename(paper, "id")
        # Should split on comma and use first part
        assert "J" in name or "Smith" in name

    def test_title_only(self):
        """Paper with title but no authors or year."""
        paper = Paper(title="Test Title Here")
        retriever = PDFRetriever.__new__(PDFRetriever)
        name = retriever._make_filename(paper, "id")
        assert "Test" in name

    def test_special_chars_in_identifier(self):
        retriever = PDFRetriever.__new__(PDFRetriever)
        name = retriever._make_filename(None, "10.1016/j.neuroimage.2024.001")
        # Slashes and dots should be replaced
        assert "/" not in name


class TestReportFailuresEdgeCases:
    def _make_retriever(self):
        retriever = PDFRetriever.__new__(PDFRetriever)
        retriever.config = Config()
        return retriever

    def test_institutional_access_from_identifier(self, capsys):
        """When paper has no DOI but identifier is a DOI, suggest access."""
        retriever = self._make_retriever()
        failures = [("https://example.com", "404")]
        retriever._report_failures("10.1234/test", failures, None)
        captured = capsys.readouterr()
        assert "Institutional access" in captured.err

    def test_no_institutional_suggestion_for_non_doi(self, capsys):
        """When identifier is not a DOI, no institutional suggestion."""
        retriever = self._make_retriever()
        failures = [("https://example.com", "404")]
        retriever._report_failures("some_random_id", failures, None)
        captured = capsys.readouterr()
        assert "Institutional access" not in captured.err


class TestCollectUrlsEdgeCases:
    @pytest.mark.asyncio
    async def test_multiple_pdf_locations(self):
        paper = Paper(
            title="Test",
            ids=IDSet(doi="10.1234/test"),
            pdf_locations=[
                PDFLocation(url="https://a.pdf", source="s2"),
                PDFLocation(url="https://b.pdf", source="openalex"),
            ],
        )
        retriever = _make_retriever()
        urls = await retriever._collect_urls(paper, "10.1234/test")
        assert "https://a.pdf" in urls
        assert "https://b.pdf" in urls

    @pytest.mark.asyncio
    async def test_identifier_parsed_when_no_paper(self):
        """When paper is None, DOI is extracted from identifier."""
        retriever = _make_retriever()
        urls = await retriever._collect_urls(None, "10.1234/test")
        assert "https://doi.org/10.1234/test" in urls

    @pytest.mark.asyncio
    async def test_identifier_pmid_no_urls(self):
        """A PMID with no paper produces no URLs (no DOI to negotiate)."""
        retriever = _make_retriever()
        urls = await retriever._collect_urls(None, "pmid:12345")
        assert urls == []


class TestUnpaywallIntegration:
    """Test that Unpaywall URLs are included in the PDF pipeline."""

    @pytest.mark.asyncio
    async def test_unpaywall_urls_added(self):
        """Unpaywall locations should appear in the URL list."""
        retriever = _make_retriever()
        # Mock unpaywall returning OA locations
        retriever._unpaywall.lookup_doi = AsyncMock(
            return_value=[
                PDFLocation(
                    url="https://europepmc.org/articles/pmc123?pdf=render",
                    source="unpaywall",
                    is_oa=True,
                ),
            ]
        )
        paper = Paper(title="Test", ids=IDSet(doi="10.1234/test"))
        urls = await retriever._collect_urls(paper, "10.1234/test")
        assert "https://europepmc.org/articles/pmc123?pdf=render" in urls

    @pytest.mark.asyncio
    async def test_unpaywall_failure_doesnt_break_pipeline(self):
        """If Unpaywall fails, other sources still work."""
        retriever = _make_retriever()
        retriever._unpaywall.lookup_doi = AsyncMock(side_effect=Exception("timeout"))
        paper = Paper(title="Test", ids=IDSet(doi="10.1234/test"))
        urls = await retriever._collect_urls(paper, "10.1234/test")
        # Should still have DOI URL at minimum
        assert "https://doi.org/10.1234/test" in urls


class TestRetrieveAsMarkdownChainOrder:
    """`PDFRetriever.retrieve_as_markdown` chains PMC -> preprint HTML -> PDF.

    Stub the two retrievers to assert ordering and the early-exit semantics:
    a successful tier short-circuits the rest of the chain.
    """

    @staticmethod
    def _stub_paper() -> Paper:
        return Paper(title="x", ids=IDSet(doi="10.48550/arXiv.1706.03762"))

    @pytest.mark.asyncio
    async def test_pmc_wins_over_preprint(self, tmp_path, monkeypatch):
        retriever = _make_retriever()
        retriever._quick_lookup = AsyncMock(return_value=self._stub_paper())

        pmc_path = tmp_path / "pmc.md"
        pmc_path.write_text("from pmc")

        ft_instance = MagicMock()
        ft_instance.__aenter__ = AsyncMock(return_value=ft_instance)
        ft_instance.__aexit__ = AsyncMock(return_value=None)
        ft_instance.retrieve = AsyncMock(return_value=pmc_path)

        pre_called = MagicMock()

        import opencite.fulltext as ft_mod
        import opencite.preprint_fulltext as pre_mod

        monkeypatch.setattr(ft_mod, "FullTextRetriever", lambda _c: ft_instance)
        monkeypatch.setattr(pre_mod, "PreprintFullTextRetriever", pre_called)

        result = await retriever.retrieve_as_markdown(
            "10.48550/arXiv.1706.03762", output_dir=str(tmp_path)
        )
        assert result == pmc_path
        pre_called.assert_not_called()

    @pytest.mark.asyncio
    async def test_preprint_wins_over_pdf_when_pmc_misses(self, tmp_path, monkeypatch):
        retriever = _make_retriever()
        retriever._quick_lookup = AsyncMock(return_value=self._stub_paper())

        ft_instance = MagicMock()
        ft_instance.__aenter__ = AsyncMock(return_value=ft_instance)
        ft_instance.__aexit__ = AsyncMock(return_value=None)
        ft_instance.retrieve = AsyncMock(return_value=None)  # PMC miss

        pre_path = tmp_path / "preprint.md"
        pre_path.write_text("from preprint")
        pre_instance = MagicMock()
        pre_instance.__aenter__ = AsyncMock(return_value=pre_instance)
        pre_instance.__aexit__ = AsyncMock(return_value=None)
        pre_instance.retrieve = AsyncMock(return_value=pre_path)

        retriever.download = AsyncMock()

        import opencite.fulltext as ft_mod
        import opencite.preprint_fulltext as pre_mod

        monkeypatch.setattr(ft_mod, "FullTextRetriever", lambda _c: ft_instance)
        monkeypatch.setattr(
            pre_mod, "PreprintFullTextRetriever", lambda _c: pre_instance
        )

        result = await retriever.retrieve_as_markdown(
            "10.48550/arXiv.1706.03762", output_dir=str(tmp_path)
        )
        assert result == pre_path
        retriever.download.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_preprint_html_skips_preprint_tier(self, tmp_path, monkeypatch):
        """`prefer_preprint_html=False` must skip the preprint tier entirely."""
        retriever = _make_retriever()
        retriever._quick_lookup = AsyncMock(return_value=self._stub_paper())

        ft_instance = MagicMock()
        ft_instance.__aenter__ = AsyncMock(return_value=ft_instance)
        ft_instance.__aexit__ = AsyncMock(return_value=None)
        ft_instance.retrieve = AsyncMock(return_value=None)  # PMC miss

        pre_called = MagicMock()
        retriever.download = AsyncMock(return_value=None)  # PDF miss too

        import opencite.fulltext as ft_mod
        import opencite.preprint_fulltext as pre_mod

        monkeypatch.setattr(ft_mod, "FullTextRetriever", lambda _c: ft_instance)
        monkeypatch.setattr(pre_mod, "PreprintFullTextRetriever", pre_called)

        await retriever.retrieve_as_markdown(
            "10.48550/arXiv.1706.03762",
            output_dir=str(tmp_path),
            prefer_preprint_html=False,
        )
        pre_called.assert_not_called()
        retriever.download.assert_called_once()
