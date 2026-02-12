"""Tests for the Semantic Scholar API client."""

from __future__ import annotations

import pytest

from opencite.clients.semantic_scholar import SemanticScholarClient
from opencite.config import Config
from tests.conftest import skip_without_s2_key


@pytest.fixture
def config() -> Config:
    return Config.from_env()


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
