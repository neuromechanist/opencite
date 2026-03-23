"""Tests for the CORE API client."""

from __future__ import annotations

from opencite.clients.core import _parse_work

# -- Unit tests for _parse_work (no API needed) --

SAMPLE_WORK = {
    "title": "A Survey of Brain-Computer Interfaces",
    "doi": "https://doi.org/10.1234/test.2024.001",
    "yearPublished": 2024,
    "authors": [
        {"name": "Jane Smith"},
        {"name": "John Doe"},
    ],
    "abstract": "This paper surveys brain-computer interface technologies.",
    "journals": [{"title": "Journal of Neural Engineering"}],
    "downloadUrl": "https://core.ac.uk/download/pdf/12345.pdf",
    "sourceFulltextUrls": [
        "https://repository.example.edu/papers/12345.pdf",
    ],
}


def test_parse_work_basic_fields():
    paper = _parse_work(SAMPLE_WORK)
    assert paper is not None
    assert paper.title == "A Survey of Brain-Computer Interfaces"
    assert paper.doi == "10.1234/test.2024.001"
    assert paper.year == 2024
    assert paper.is_oa is True
    assert "core" in paper.data_sources


def test_parse_work_doi_prefix_stripped():
    """DOI should have https://doi.org/ prefix stripped."""
    paper = _parse_work(SAMPLE_WORK)
    assert paper is not None
    assert not paper.doi.startswith("https://")


def test_parse_work_authors():
    paper = _parse_work(SAMPLE_WORK)
    assert paper is not None
    assert len(paper.authors) == 2
    assert paper.authors[0].name == "Jane Smith"


def test_parse_work_string_authors():
    """CORE sometimes returns authors as plain strings."""
    work = {
        "title": "Test",
        "authors": ["Alice Bob", "Carol Dave"],
    }
    paper = _parse_work(work)
    assert paper is not None
    assert len(paper.authors) == 2
    assert paper.authors[0].name == "Alice Bob"


def test_parse_work_pdf_locations():
    paper = _parse_work(SAMPLE_WORK)
    assert paper is not None
    assert len(paper.pdf_locations) == 2
    assert paper.pdf_locations[0].url == "https://core.ac.uk/download/pdf/12345.pdf"
    assert paper.pdf_locations[0].source == "core"
    assert paper.pdf_locations[0].is_oa is True
    assert (
        paper.pdf_locations[1].url == "https://repository.example.edu/papers/12345.pdf"
    )


def test_parse_work_venue():
    paper = _parse_work(SAMPLE_WORK)
    assert paper is not None
    assert paper.source_venue is not None
    assert paper.source_venue.name == "Journal of Neural Engineering"


def test_parse_work_no_title():
    assert _parse_work({}) is None
    assert _parse_work({"title": ""}) is None


def test_parse_work_minimal():
    paper = _parse_work({"title": "Minimal Paper"})
    assert paper is not None
    assert paper.doi == ""
    assert paper.year is None
    assert paper.authors == []
    assert paper.pdf_locations == []


def test_parse_work_http_doi_prefix():
    """http://doi.org/ prefix should also be stripped."""
    work = {"title": "Test", "doi": "http://doi.org/10.1234/test"}
    paper = _parse_work(work)
    assert paper is not None
    assert paper.doi == "10.1234/test"
