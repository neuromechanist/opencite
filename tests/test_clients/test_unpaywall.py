"""Tests for the Unpaywall API client."""

from __future__ import annotations

from opencite.clients.unpaywall import (
    _extract_locations,
    _parse_location,
)

# -- Unit tests for response parsing (no API needed) --

SAMPLE_RESPONSE = {
    "doi": "10.1523/jneurosci.3300-07.2008",
    "is_oa": True,
    "best_oa_location": {
        "url_for_pdf": "https://europepmc.org/articles/pmc6671580?pdf=render",
        "url_for_landing_page": "https://europepmc.org/articles/pmc6671580",
        "version": "publishedVersion",
        "license": "cc-by",
    },
    "oa_locations": [
        {
            "url_for_pdf": "https://europepmc.org/articles/pmc6671580?pdf=render",
            "url_for_landing_page": "https://europepmc.org/articles/pmc6671580",
            "version": "publishedVersion",
            "license": "cc-by",
        },
        {
            "url_for_pdf": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6671580/pdf/",
            "version": "publishedVersion",
            "license": None,
        },
        {
            "url_for_pdf": None,
            "url_for_landing_page": "https://doi.org/10.1523/jneurosci.3300-07.2008",
            "version": "publishedVersion",
        },
    ],
}


def test_extract_locations_deduplicates():
    """Best OA location should be first, duplicates removed."""
    locs = _extract_locations(SAMPLE_RESPONSE)
    urls = [loc.url for loc in locs]

    # 3rd location falls back to landing page URL, 1st is deduped with best_oa
    assert len(locs) == 3
    assert urls[0] == "https://europepmc.org/articles/pmc6671580?pdf=render"
    assert urls[1] == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6671580/pdf/"
    assert urls[2] == "https://doi.org/10.1523/jneurosci.3300-07.2008"


def test_extract_locations_all_oa():
    """All extracted locations should be marked as OA."""
    locs = _extract_locations(SAMPLE_RESPONSE)
    assert all(loc.is_oa for loc in locs)
    assert all(loc.source == "unpaywall" for loc in locs)


def test_parse_location_with_pdf_url():
    loc = _parse_location(
        {
            "url_for_pdf": "https://example.com/paper.pdf",
            "version": "acceptedVersion",
            "license": "cc-by-nc",
        }
    )
    assert loc is not None
    assert loc.url == "https://example.com/paper.pdf"
    assert loc.version == "acceptedVersion"
    assert loc.license == "cc-by-nc"


def test_parse_location_no_pdf_url_falls_back_to_landing():
    """Locations without pdf URL should fall back to landing page."""
    loc = _parse_location(
        {
            "url_for_pdf": None,
            "url_for_landing_page": "https://example.com/",
        }
    )
    assert loc is not None
    assert loc.url == "https://example.com/"


def test_parse_location_no_urls_at_all():
    """Locations with neither pdf URL nor landing page return None."""
    loc = _parse_location({"url_for_pdf": None, "url_for_landing_page": None})
    assert loc is None


def test_extract_locations_empty_response():
    locs = _extract_locations({})
    assert locs == []


def test_extract_locations_no_oa():
    locs = _extract_locations({"is_oa": False, "oa_locations": []})
    assert locs == []
