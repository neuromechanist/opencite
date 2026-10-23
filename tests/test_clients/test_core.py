"""Tests for the CORE API client."""

from __future__ import annotations

import httpx
import pytest
import respx

from opencite.clients.core import COREClient, _parse_work
from opencite.config import Config
from opencite.exceptions import APIKeyError

_BASE = "https://api.core.ac.uk"

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


# -- Regression: CORE 301s the un-slashed search path --


class TestCoreSearchRedirect:
    """CORE moved /v3/search/works to /v3/search/works/ and 301s the old path.

    The shared client in `clients.base` did not set ``follow_redirects``, which
    httpx defaults to False, so the 301 was raised as an APIError and the source
    returned zero results with a valid API key.
    """

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_hits_the_canonical_slashed_path(self):
        route = respx.get(f"{_BASE}/v3/search/works/").mock(
            return_value=httpx.Response(200, json={"results": [SAMPLE_WORK]})
        )
        async with COREClient(Config(core_api_key="k")) as client:
            papers = await client.search("brain computer interface")
        assert route.called
        assert len(papers) == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_follows_a_301_instead_of_erroring(self):
        respx.get(f"{_BASE}/v3/search/works").mock(
            return_value=httpx.Response(
                301, headers={"Location": f"{_BASE}/v3/search/works/"}
            )
        )
        respx.get(f"{_BASE}/v3/search/works/").mock(
            return_value=httpx.Response(200, json={"results": [SAMPLE_WORK]})
        )
        async with COREClient(Config(core_api_key="k")) as client:
            resp = await client.get("/v3/search/works", params={"q": "x"})
        assert resp.status_code == 200


async def test_search_without_key_raises():
    async with COREClient(Config(core_api_key="")) as client:
        with pytest.raises(APIKeyError):
            await client.search("memory")
