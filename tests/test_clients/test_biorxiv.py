"""Tests for the bioRxiv/medRxiv API client."""

from __future__ import annotations

import pytest

from opencite.clients.biorxiv import BioRxivClient
from opencite.config import Config


@pytest.fixture
def config() -> Config:
    return Config.from_env()


# ---------------------------------------------------------------------------
# Sample API responses
# ---------------------------------------------------------------------------

_CONTENT_API_ENTRY = {
    "doi": "10.1101/837021",
    "title": "Sex-specific genetic effects across biomarkers",
    "authors": "Smith J; Jones AB; Williams C",
    "date": "2019-11-12",
    "version": "1",
    "abstract": "We investigated sex-specific genetic effects across 35 biomarkers.",
    "category": "genetics",
    "server": "biorxiv",
}

_CROSSREF_ITEM = {
    "DOI": "10.1101/2024.09.12.612645",
    "title": ["Assessing differential cell composition in single-cell studies"],
    "author": [
        {"family": "Smith", "given": "Jane"},
        {"family": "Doe", "given": "John"},
    ],
    "published": {"date-parts": [[2024, 9, 12]]},
    "abstract": "<jats:p>We present a method for differential analysis.</jats:p>",
    "container-title": ["bioRxiv"],
    "URL": "https://www.biorxiv.org/content/10.1101/2024.09.12.612645",
    "is-referenced-by-count": 3,
}


class TestBioRxivClientParsing:
    """Unit tests for parsing (no network required)."""

    def _client(self) -> BioRxivClient:
        return BioRxivClient(Config())

    def test_parse_content_entry_basic(self):
        client = self._client()
        paper = client._parse_content_entry(_CONTENT_API_ENTRY, server="biorxiv")
        assert paper is not None
        assert paper.title == "Sex-specific genetic effects across biomarkers"
        assert paper.ids.doi == "10.1101/837021"
        assert paper.year == 2019
        assert paper.publication_date == "2019-11-12"
        assert paper.is_oa is True
        assert "biorxiv" in paper.data_sources

    def test_parse_content_entry_authors(self):
        client = self._client()
        paper = client._parse_content_entry(_CONTENT_API_ENTRY, server="biorxiv")
        assert paper is not None
        assert len(paper.authors) == 3
        assert paper.authors[0].family_name == "Smith"

    def test_parse_content_entry_pdf_url(self):
        client = self._client()
        paper = client._parse_content_entry(_CONTENT_API_ENTRY, server="biorxiv")
        assert paper is not None
        pdf = paper.best_pdf_url
        assert pdf is not None
        assert "biorxiv.org" in pdf
        assert "10.1101/837021" in pdf
        assert pdf.endswith(".full.pdf")

    def test_parse_content_entry_abstract_truncated(self):
        long_abstract = "word " * 300  # > 1000 chars
        entry = {**_CONTENT_API_ENTRY, "abstract": long_abstract}
        client = self._client()
        paper = client._parse_content_entry(entry, server="biorxiv")
        assert paper is not None
        assert len(paper.abstract) <= 1000

    def test_parse_content_entry_no_title_returns_none(self):
        entry = {**_CONTENT_API_ENTRY, "title": ""}
        client = self._client()
        assert client._parse_content_entry(entry, server="biorxiv") is None

    def test_parse_crossref_item_basic(self):
        client = self._client()
        paper = client._parse_crossref_item(_CROSSREF_ITEM)
        assert paper is not None
        assert "differential cell composition" in paper.title
        assert paper.ids.doi == "10.1101/2024.09.12.612645"
        assert paper.year == 2024
        assert paper.citation_count == 3

    def test_parse_crossref_item_authors(self):
        client = self._client()
        paper = client._parse_crossref_item(_CROSSREF_ITEM)
        assert paper is not None
        assert len(paper.authors) == 2
        assert paper.authors[0].family_name == "Smith"
        assert paper.authors[0].given_name == "Jane"

    def test_parse_crossref_item_jats_stripped(self):
        """JATS XML tags in CrossRef abstracts should be stripped."""
        client = self._client()
        paper = client._parse_crossref_item(_CROSSREF_ITEM)
        assert paper is not None
        assert "<jats:p>" not in paper.abstract
        assert "differential analysis" in paper.abstract

    def test_parse_crossref_item_pdf_url(self):
        client = self._client()
        paper = client._parse_crossref_item(_CROSSREF_ITEM)
        assert paper is not None
        pdf = paper.best_pdf_url
        assert pdf is not None
        assert "biorxiv.org" in pdf or "medrxiv.org" in pdf

    def test_parse_crossref_item_no_title_returns_none(self):
        item = {**_CROSSREF_ITEM, "title": []}
        client = self._client()
        assert client._parse_crossref_item(item) is None
