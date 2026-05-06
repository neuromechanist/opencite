"""Tests for the medRxiv preprint client.

medRxiv shares the bioRxiv Content API base and CrossRef search path; the
distinction is the ``server`` segment in URLs and the attribution in
``data_sources``. These tests assert that MedRxivClient owns medRxiv
records and ignores bioRxiv records.
"""

from __future__ import annotations

from opencite.clients.medrxiv import MedRxivClient
from opencite.config import Config

# ---------------------------------------------------------------------------
# Sample API responses
# ---------------------------------------------------------------------------

_CONTENT_API_ENTRY = {
    "doi": "10.1101/2021.01.01.12345",
    "title": "A medRxiv preprint on infectious disease",
    "authors": "Smith J; Jones AB; Williams C",
    "date": "2021-01-01",
    "version": "1",
    "abstract": "We investigated transmission dynamics across populations.",
    "category": "infectious diseases",
    "server": "medrxiv",
}

_CROSSREF_MEDRXIV_ITEM = {
    "DOI": "10.1101/2024.05.15.999000",
    "title": ["Population-level effects of vaccination"],
    "author": [
        {"family": "Doe", "given": "Jane"},
        {"family": "Roe", "given": "John"},
    ],
    "published": {"date-parts": [[2024, 5, 15]]},
    "abstract": "<jats:p>We model vaccination effects.</jats:p>",
    "container-title": ["medRxiv"],
    "URL": "https://www.medrxiv.org/content/10.1101/2024.05.15.999000",
    "is-referenced-by-count": 1,
}

_CROSSREF_BIORXIV_ITEM = {
    **_CROSSREF_MEDRXIV_ITEM,
    "DOI": "10.1101/2024.05.15.111111",
    "title": ["Some bioRxiv paper"],
    "container-title": ["bioRxiv"],
}


class TestMedRxivClientParsing:
    """Unit tests for parsing (no network required)."""

    def _client(self) -> MedRxivClient:
        return MedRxivClient(Config())

    def test_class_attributes(self):
        assert MedRxivClient.name == "medrxiv"
        assert MedRxivClient.server == "medrxiv"

    def test_parse_content_entry_basic(self):
        client = self._client()
        paper = client._parse_content_entry(_CONTENT_API_ENTRY)
        assert paper is not None
        assert paper.title == "A medRxiv preprint on infectious disease"
        assert paper.ids.doi == "10.1101/2021.01.01.12345"
        assert paper.year == 2021
        assert paper.publication_date == "2021-01-01"
        assert paper.is_oa is True
        assert "medrxiv" in paper.data_sources
        assert paper.url is not None and "medrxiv.org" in paper.url

    def test_parse_content_entry_pdf_url_uses_medrxiv_domain(self):
        client = self._client()
        paper = client._parse_content_entry(_CONTENT_API_ENTRY)
        assert paper is not None
        pdf = paper.best_pdf_url
        assert pdf is not None
        assert "medrxiv.org" in pdf
        assert pdf.endswith(".full.pdf")

    def test_parse_crossref_item_medrxiv_kept(self):
        """CrossRef items with container-title=medRxiv are claimed."""
        client = self._client()
        paper = client._parse_crossref_item(_CROSSREF_MEDRXIV_ITEM)
        assert paper is not None
        assert "medrxiv" in paper.data_sources
        pdf = paper.best_pdf_url
        assert pdf is not None
        assert "medrxiv.org" in pdf

    def test_parse_crossref_item_biorxiv_filtered_out(self):
        """CrossRef items with container-title=bioRxiv are ignored."""
        client = self._client()
        assert client._parse_crossref_item(_CROSSREF_BIORXIV_ITEM) is None

    def test_parse_crossref_item_jats_stripped(self):
        client = self._client()
        paper = client._parse_crossref_item(_CROSSREF_MEDRXIV_ITEM)
        assert paper is not None
        assert "<jats:p>" not in paper.abstract
        assert "vaccination effects" in paper.abstract

    def test_parse_content_entry_no_title_returns_none(self):
        entry = {**_CONTENT_API_ENTRY, "title": ""}
        client = self._client()
        assert client._parse_content_entry(entry) is None
