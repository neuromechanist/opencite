"""Tests for the OpenAlex API client."""

from __future__ import annotations

import pytest

from opencite.clients.openalex import (
    OpenAlexClient,
    _extract_pdf_locations,
)
from opencite.config import Config
from tests.conftest import skip_without_openalex_key


@pytest.fixture
def config() -> Config:
    return Config.from_env()


# -- Unit tests for _parse_work (no API needed) --

SAMPLE_WORK = {
    "id": "https://openalex.org/W2741809807",
    "doi": "https://doi.org/10.1038/s41586-021-03819-2",
    "ids": {
        "openalex": "https://openalex.org/W2741809807",
        "doi": "https://doi.org/10.1038/s41586-021-03819-2",
        "pmid": "https://pubmed.ncbi.nlm.nih.gov/34265844/",
        "pmcid": "PMC8371605",
    },
    "title": "Highly accurate protein structure prediction with AlphaFold",
    "publication_date": "2021-07-15",
    "type": "journal-article",
    "abstract_inverted_index": {
        "Proteins": [0],
        "are": [1],
        "essential.": [2],
    },
    "authorships": [
        {
            "author": {
                "id": "https://openalex.org/A1234",
                "display_name": "John Jumper",
                "orcid": "https://orcid.org/0000-0001-2345-6789",
            },
        },
        {
            "author": {
                "id": "https://openalex.org/A5678",
                "display_name": "Richard Evans",
                "orcid": None,
            },
        },
    ],
    "primary_location": {
        "source": {
            "id": "https://openalex.org/S123",
            "display_name": "Nature",
            "issn_l": "0028-0836",
            "host_organization_name": "Springer Nature",
            "is_oa": False,
        },
        "pdf_url": "https://example.com/published.pdf",
        "is_oa": True,
        "version": "publishedVersion",
        "license": "cc-by",
    },
    "best_oa_location": {
        "pdf_url": "https://example.com/best_oa.pdf",
        "is_oa": True,
        "version": "publishedVersion",
        "license": "cc-by",
    },
    "locations": [
        {
            "pdf_url": "https://example.com/published.pdf",
            "is_oa": True,
            "version": "publishedVersion",
        },
        {
            "pdf_url": "https://example.com/preprint.pdf",
            "is_oa": True,
            "version": "submittedVersion",
        },
    ],
    "cited_by_count": 15000,
    "is_retracted": False,
    "open_access": {"is_oa": True},
    "topics": [
        {"display_name": "Protein Structure"},
        {"display_name": "Machine Learning"},
    ],
    "mesh": [
        {"descriptor_name": "Protein Folding"},
        {"descriptor_name": "Computational Biology"},
    ],
    "funders": [
        {
            "display_name": "DeepMind",
            "award_ids": ["GRANT-001"],
        },
    ],
}


def _make_client():
    """Create an OpenAlexClient without connecting to the API."""
    client = OpenAlexClient.__new__(OpenAlexClient)
    client.config = Config()
    return client


class TestParseWork:
    def test_basic_fields(self):
        client = _make_client()
        paper = client._parse_work(SAMPLE_WORK)
        assert (
            paper.title == "Highly accurate protein structure prediction with AlphaFold"
        )
        assert paper.year == 2021
        assert paper.publication_date == "2021-07-15"
        assert paper.pub_type == "journal-article"
        assert paper.citation_count == 15000
        assert paper.is_oa is True
        assert paper.is_retracted is False
        assert "openalex" in paper.data_sources

    def test_ids_parsed(self):
        client = _make_client()
        paper = client._parse_work(SAMPLE_WORK)
        assert paper.ids.doi == "10.1038/s41586-021-03819-2"
        assert paper.ids.openalex_id == "W2741809807"
        assert paper.ids.pmid == "34265844"
        assert paper.ids.pmcid == "PMC8371605"

    def test_authors_parsed(self):
        client = _make_client()
        paper = client._parse_work(SAMPLE_WORK)
        assert len(paper.authors) == 2
        a1 = paper.authors[0]
        assert a1.name == "John Jumper"
        assert a1.family_name == "Jumper"
        assert a1.given_name == "John"
        assert a1.orcid == "0000-0001-2345-6789"
        assert a1.openalex_id == "A1234"

    def test_abstract_reconstructed(self):
        client = _make_client()
        paper = client._parse_work(SAMPLE_WORK)
        assert "Proteins" in paper.abstract
        assert "essential" in paper.abstract

    def test_source_venue(self):
        client = _make_client()
        paper = client._parse_work(SAMPLE_WORK)
        assert paper.source_venue is not None
        assert paper.source_venue.name == "Nature"
        assert paper.source_venue.issn == "0028-0836"
        assert paper.source_venue.publisher == "Springer Nature"
        assert paper.source_venue.openalex_id == "S123"

    def test_pdf_locations(self):
        client = _make_client()
        paper = client._parse_work(SAMPLE_WORK)
        assert len(paper.pdf_locations) >= 2
        urls = [loc.url for loc in paper.pdf_locations]
        assert "https://example.com/best_oa.pdf" in urls
        assert "https://example.com/published.pdf" in urls

    def test_topics_and_mesh(self):
        client = _make_client()
        paper = client._parse_work(SAMPLE_WORK)
        assert "Protein Structure" in paper.topics
        assert "Machine Learning" in paper.topics
        assert "Protein Folding" in paper.mesh_terms
        assert "Computational Biology" in paper.mesh_terms

    def test_grants(self):
        client = _make_client()
        paper = client._parse_work(SAMPLE_WORK)
        assert len(paper.grants) == 1
        assert paper.grants[0]["funder"] == "DeepMind"
        assert paper.grants[0]["award_id"] == "GRANT-001"

    def test_url_uses_doi_raw(self):
        client = _make_client()
        paper = client._parse_work(SAMPLE_WORK)
        assert paper.url == "https://doi.org/10.1038/s41586-021-03819-2"

    def test_minimal_work(self):
        """Parse a work with minimal fields."""
        client = _make_client()
        work = {"title": "Minimal Paper", "id": "https://openalex.org/W999"}
        paper = client._parse_work(work)
        assert paper.title == "Minimal Paper"
        assert paper.ids.openalex_id == "W999"
        assert paper.year is None
        assert paper.authors == []

    def test_no_doi_url_fallback(self):
        """When no DOI, URL falls back to OpenAlex ID."""
        client = _make_client()
        work = {"title": "No DOI Paper", "id": "https://openalex.org/W111"}
        paper = client._parse_work(work)
        assert paper.url == "https://openalex.org/W111"

    def test_author_without_name_skipped(self):
        client = _make_client()
        work = {
            "title": "Test",
            "authorships": [
                {"author": {"display_name": ""}},
                {"author": {"display_name": "Bob Smith"}},
            ],
        }
        paper = client._parse_work(work)
        assert len(paper.authors) == 1
        assert paper.authors[0].name == "Bob Smith"

    def test_abstract_truncated_at_1000(self):
        client = _make_client()
        # Build an inverted index that produces a long abstract
        idx = {f"word{i}": [i] for i in range(300)}
        work = {"title": "Long Abstract", "abstract_inverted_index": idx}
        paper = client._parse_work(work)
        assert len(paper.abstract) <= 1000


class TestExtractPdfLocations:
    def test_deduplicates_urls(self):
        work = {
            "best_oa_location": {"pdf_url": "https://a.pdf", "is_oa": True},
            "primary_location": {"pdf_url": "https://a.pdf", "is_oa": True},
            "locations": [{"pdf_url": "https://a.pdf", "is_oa": True}],
        }
        locations = _extract_pdf_locations(work)
        assert len(locations) == 1

    def test_skips_empty_urls(self):
        work = {
            "best_oa_location": {"pdf_url": "", "is_oa": True},
            "primary_location": {"pdf_url": None},
            "locations": [],
        }
        locations = _extract_pdf_locations(work)
        assert len(locations) == 0

    def test_priority_order(self):
        work = {
            "best_oa_location": {"pdf_url": "https://best.pdf", "is_oa": True},
            "primary_location": {"pdf_url": "https://primary.pdf", "is_oa": True},
            "locations": [{"pdf_url": "https://other.pdf", "is_oa": False}],
        }
        locations = _extract_pdf_locations(work)
        assert locations[0].url == "https://best.pdf"
        assert locations[1].url == "https://primary.pdf"
        assert locations[2].url == "https://other.pdf"


@pytest.mark.integration
@skip_without_openalex_key
class TestOpenAlexClient:
    """Integration tests for OpenAlexClient (requires OPENALEX_API_KEY)."""

    async def test_search_returns_papers(self, config: Config):
        async with OpenAlexClient(config) as client:
            papers = await client.search(
                "transformer attention mechanism", max_results=5
            )
        assert len(papers) > 0
        paper = papers[0]
        assert paper.title
        assert "openalex" in paper.data_sources

    async def test_search_with_year_filter(self, config: Config):
        async with OpenAlexClient(config) as client:
            papers = await client.search(
                "deep learning",
                max_results=5,
                year_from=2020,
                year_to=2022,
            )
        assert len(papers) > 0
        for p in papers:
            if p.year:
                assert 2020 <= p.year <= 2022

    async def test_search_oa_only(self, config: Config):
        async with OpenAlexClient(config) as client:
            papers = await client.search(
                "machine learning", max_results=5, oa_only=True
            )
        assert len(papers) > 0
        for p in papers:
            assert p.is_oa

    async def test_lookup_doi(self, config: Config):
        async with OpenAlexClient(config) as client:
            paper = await client.lookup_doi("10.1038/s41586-021-03819-2")
        assert paper is not None
        assert paper.title
        assert paper.ids.doi == "10.1038/s41586-021-03819-2"

    async def test_lookup_doi_not_found(self, config: Config):
        async with OpenAlexClient(config) as client:
            paper = await client.lookup_doi("10.9999/does-not-exist-xyz")
        assert paper is None

    async def test_lookup_pmid(self, config: Config):
        # PMID 34265844 = "Highly accurate protein structure prediction with AlphaFold"
        async with OpenAlexClient(config) as client:
            paper = await client.lookup_pmid("34265844")
        assert paper is not None
        assert paper.title
        assert paper.ids.pmid == "34265844"

    async def test_citing_papers(self, config: Config):
        async with OpenAlexClient(config) as client:
            # First look up a well-cited paper to get OpenAlex ID
            paper = await client.lookup_doi("10.1038/s41586-021-03819-2")
            assert paper is not None
            oa_id = paper.ids.openalex_id
            assert oa_id

            citing = await client.citing_papers(oa_id, max_results=5)
        assert len(citing) > 0

    async def test_references(self, config: Config):
        async with OpenAlexClient(config) as client:
            paper = await client.lookup_doi("10.1038/s41586-021-03819-2")
            assert paper is not None
            oa_id = paper.ids.openalex_id

            refs = await client.references(oa_id, max_results=5)
        assert len(refs) > 0

    async def test_canonical_search(self, config: Config):
        async with OpenAlexClient(config) as client:
            papers = await client.canonical_search(
                "deep learning",
                max_results=5,
                min_citations=1000,
            )
        assert len(papers) > 0
        for p in papers:
            assert p.citation_count >= 1000

    async def test_batch_lookup_dois(self, config: Config):
        dois = [
            "10.1038/s41586-021-03819-2",
            "10.1126/science.abj8754",
        ]
        async with OpenAlexClient(config) as client:
            papers = await client.batch_lookup_dois(dois)
        assert len(papers) >= 1

    async def test_paper_has_authors(self, config: Config):
        async with OpenAlexClient(config) as client:
            paper = await client.lookup_doi("10.1038/s41586-021-03819-2")
        assert paper is not None
        assert len(paper.authors) > 0
        assert paper.authors[0].name
        assert paper.authors[0].family_name

    async def test_paper_has_source_venue(self, config: Config):
        async with OpenAlexClient(config) as client:
            paper = await client.lookup_doi("10.1038/s41586-021-03819-2")
        assert paper is not None
        assert paper.source_venue is not None
        assert paper.source_venue.name

    async def test_search_sort_by_citations(self, config: Config):
        async with OpenAlexClient(config) as client:
            papers = await client.search(
                "neural network", max_results=5, sort="citations"
            )
        assert len(papers) > 0
        # First result should have high citation count
        assert papers[0].citation_count > 0
