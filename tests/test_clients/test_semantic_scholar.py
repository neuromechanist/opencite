"""Tests for the Semantic Scholar API client."""

from __future__ import annotations

import pytest

from opencite.clients.semantic_scholar import SemanticScholarClient
from opencite.config import Config
from tests.conftest import skip_without_s2_key


@pytest.fixture
def config() -> Config:
    return Config.from_env()


# -- Unit tests for _parse_paper (no API needed) --

SAMPLE_S2_PAPER = {
    "paperId": "abc123def456",
    "title": "Attention Is All You Need",
    "abstract": "The dominant sequence transduction models are based on complex recurrent neural networks.",
    "year": 2017,
    "url": "https://www.semanticscholar.org/paper/abc123",
    "openAccessPdf": {
        "url": "https://arxiv.org/pdf/1706.03762",
    },
    "citationCount": 100000,
    "influentialCitationCount": 5000,
    "externalIds": {
        "DOI": "10.48550/arXiv.1706.03762",
        "ArXiv": "1706.03762",
        "PubMed": "12345",
        "PubMedCentral": "PMC99999",
    },
    "authors": [
        {"authorId": "S2A1", "name": "Ashish Vaswani"},
        {"authorId": "S2A2", "name": "Noam Shazeer"},
        {"authorId": "", "name": "Niki Parmar"},
    ],
    "journal": {"name": "Advances in Neural Information Processing Systems"},
    "tldr": {"text": "A new network architecture based on attention mechanisms."},
    "citationStyles": {"bibtex": "@article{vaswani2017, title={Attention}}"},
    "s2FieldsOfStudy": [
        {"category": "Computer Science"},
        {"category": "Mathematics"},
    ],
    "publicationTypes": ["JournalArticle", "Conference"],
    "isOpenAccess": True,
    "publicationDate": "2017-06-12",
}


def _make_s2_client():
    """Create a SemanticScholarClient without connecting."""
    client = SemanticScholarClient.__new__(SemanticScholarClient)
    client.config = Config()
    return client


class TestParsePaper:
    def test_basic_fields(self):
        client = _make_s2_client()
        paper = client._parse_paper(SAMPLE_S2_PAPER)
        assert paper.title == "Attention Is All You Need"
        assert paper.year == 2017
        assert paper.citation_count == 100000
        assert paper.influential_citation_count == 5000
        assert paper.is_oa is True
        assert paper.url == "https://www.semanticscholar.org/paper/abc123"
        assert "s2" in paper.data_sources

    def test_ids_parsed(self):
        client = _make_s2_client()
        paper = client._parse_paper(SAMPLE_S2_PAPER)
        assert paper.ids.doi == "10.48550/arXiv.1706.03762"
        assert paper.ids.arxiv_id == "1706.03762"
        assert paper.ids.pmid == "12345"
        assert paper.ids.pmcid == "PMC99999"
        assert paper.ids.s2_id == "abc123def456"

    def test_authors_parsed(self):
        client = _make_s2_client()
        paper = client._parse_paper(SAMPLE_S2_PAPER)
        assert len(paper.authors) == 3
        a1 = paper.authors[0]
        assert a1.name == "Ashish Vaswani"
        assert a1.family_name == "Vaswani"
        assert a1.given_name == "Ashish"
        assert a1.s2_id == "S2A1"

    def test_journal_venue(self):
        client = _make_s2_client()
        paper = client._parse_paper(SAMPLE_S2_PAPER)
        assert paper.source_venue is not None
        assert (
            paper.source_venue.name
            == "Advances in Neural Information Processing Systems"
        )

    def test_pdf_location(self):
        client = _make_s2_client()
        paper = client._parse_paper(SAMPLE_S2_PAPER)
        assert len(paper.pdf_locations) == 1
        assert paper.pdf_locations[0].url == "https://arxiv.org/pdf/1706.03762"
        assert paper.pdf_locations[0].source == "s2"
        assert paper.pdf_locations[0].is_oa is True

    def test_tldr(self):
        client = _make_s2_client()
        paper = client._parse_paper(SAMPLE_S2_PAPER)
        assert "attention mechanisms" in paper.tldr

    def test_topics_from_fields_of_study(self):
        client = _make_s2_client()
        paper = client._parse_paper(SAMPLE_S2_PAPER)
        assert "Computer Science" in paper.topics
        assert "Mathematics" in paper.topics

    def test_pub_type(self):
        client = _make_s2_client()
        paper = client._parse_paper(SAMPLE_S2_PAPER)
        assert paper.pub_type == "JournalArticle"

    def test_bibtex_cached(self):
        client = _make_s2_client()
        paper = client._parse_paper(SAMPLE_S2_PAPER)
        assert paper._bibtex == "@article{vaswani2017, title={Attention}}"

    def test_publication_date(self):
        client = _make_s2_client()
        paper = client._parse_paper(SAMPLE_S2_PAPER)
        assert paper.publication_date == "2017-06-12"

    def test_minimal_paper(self):
        """Parse a paper with minimal fields."""
        client = _make_s2_client()
        data = {"paperId": "xyz", "title": "Minimal"}
        paper = client._parse_paper(data)
        assert paper.title == "Minimal"
        assert paper.ids.s2_id == "xyz"
        assert paper.year is None
        assert paper.authors == []
        assert paper.source_venue is None
        assert paper.pdf_locations == []
        assert paper.tldr == ""
        assert paper._bibtex == ""

    def test_no_oa_pdf(self):
        client = _make_s2_client()
        data = {"paperId": "xyz", "title": "No PDF", "openAccessPdf": None}
        paper = client._parse_paper(data)
        assert paper.pdf_locations == []

    def test_no_journal(self):
        client = _make_s2_client()
        data = {"paperId": "xyz", "title": "No Journal", "journal": None}
        paper = client._parse_paper(data)
        assert paper.source_venue is None

    def test_author_without_name_skipped(self):
        client = _make_s2_client()
        data = {
            "paperId": "xyz",
            "title": "Test",
            "authors": [{"name": ""}, {"name": "Bob"}],
        }
        paper = client._parse_paper(data)
        assert len(paper.authors) == 1
        assert paper.authors[0].name == "Bob"

    def test_abstract_truncated(self):
        client = _make_s2_client()
        data = {"paperId": "xyz", "title": "Long", "abstract": "x" * 2000}
        paper = client._parse_paper(data)
        assert len(paper.abstract) <= 1000


@pytest.mark.integration
@skip_without_s2_key
class TestSemanticScholarClient:
    """Integration tests for SemanticScholarClient (requires SEMANTIC_SCHOLAR_API_KEY)."""

    async def test_search_returns_papers(self, config: Config):
        async with SemanticScholarClient(config) as client:
            papers = await client.search(
                "transformer attention mechanism", max_results=5
            )
        assert len(papers) > 0
        paper = papers[0]
        assert paper.title
        assert "s2" in paper.data_sources

    async def test_lookup_by_doi(self, config: Config):
        async with SemanticScholarClient(config) as client:
            paper = await client.lookup("DOI:10.1038/s41586-021-03819-2")
        assert paper is not None
        assert paper.title
        assert paper.ids.doi == "10.1038/s41586-021-03819-2"

    async def test_lookup_by_s2_id(self, config: Config):
        # "Attention Is All You Need"
        async with SemanticScholarClient(config) as client:
            paper = await client.lookup("204e3073870fae3d05bcbc2f6a8e263d9b72e776")
        assert paper is not None
        assert "attention" in paper.title.lower()

    async def test_lookup_by_arxiv(self, config: Config):
        async with SemanticScholarClient(config) as client:
            paper = await client.lookup("ARXIV:1706.03762")
        assert paper is not None
        assert paper.ids.arxiv_id == "1706.03762"

    async def test_lookup_by_pmid(self, config: Config):
        async with SemanticScholarClient(config) as client:
            paper = await client.lookup("PMID:34265844")
        assert paper is not None
        assert paper.ids.pmid == "34265844"

    async def test_lookup_not_found(self, config: Config):
        async with SemanticScholarClient(config) as client:
            paper = await client.lookup("DOI:10.9999/does-not-exist-xyz")
        assert paper is None

    async def test_citing_papers(self, config: Config):
        async with SemanticScholarClient(config) as client:
            citing = await client.citing_papers(
                "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
                max_results=5,
            )
        assert len(citing) > 0
        for p in citing:
            assert p.title

    async def test_references(self, config: Config):
        async with SemanticScholarClient(config) as client:
            refs = await client.references(
                "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
                max_results=5,
            )
        assert len(refs) > 0

    async def test_batch_lookup(self, config: Config):
        ids = [
            "DOI:10.1038/s41586-021-03819-2",
            "ARXIV:1706.03762",
        ]
        async with SemanticScholarClient(config) as client:
            papers = await client.batch_lookup(ids)
        assert len(papers) >= 1

    async def test_paper_has_tldr(self, config: Config):
        async with SemanticScholarClient(config) as client:
            paper = await client.lookup("204e3073870fae3d05bcbc2f6a8e263d9b72e776")
        assert paper is not None
        # TLDR may or may not be available, but the field should exist
        assert isinstance(paper.tldr, str)

    async def test_paper_has_authors(self, config: Config):
        async with SemanticScholarClient(config) as client:
            paper = await client.lookup("204e3073870fae3d05bcbc2f6a8e263d9b72e776")
        assert paper is not None
        assert len(paper.authors) > 0
        assert paper.authors[0].name

    async def test_paper_has_external_ids(self, config: Config):
        async with SemanticScholarClient(config) as client:
            paper = await client.lookup("204e3073870fae3d05bcbc2f6a8e263d9b72e776")
        assert paper is not None
        assert paper.ids.s2_id
        assert paper.ids.arxiv_id or paper.ids.doi

    async def test_paper_has_bibtex(self, config: Config):
        async with SemanticScholarClient(config) as client:
            paper = await client.lookup("204e3073870fae3d05bcbc2f6a8e263d9b72e776")
        assert paper is not None
        assert isinstance(paper._bibtex, str)
