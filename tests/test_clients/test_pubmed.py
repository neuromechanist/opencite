"""Tests for the PubMed API client."""

from __future__ import annotations

import pytest

from opencite.clients.pubmed import (
    PubMedClient,
    _extract_link_ids,
    _month_to_num,
    _parse_pubmed_xml,
)
from opencite.config import Config
from tests.conftest import skip_without_pubmed_key


@pytest.fixture
def config() -> Config:
    return Config.from_env()


# -- Unit tests for XML parsing (no API needed) --


SAMPLE_XML = """\
<?xml version="1.0" ?>
<PubmedArticleSet>
<PubmedArticle>
    <MedlineCitation>
        <PMID>34265844</PMID>
        <Article>
            <ArticleTitle>Highly accurate protein structure prediction with AlphaFold</ArticleTitle>
            <Abstract>
                <AbstractText>Proteins are essential to life.</AbstractText>
            </Abstract>
            <AuthorList>
                <Author>
                    <LastName>Jumper</LastName>
                    <ForeName>John</ForeName>
                    <Identifier Source="ORCID">0000-0001-2345-6789</Identifier>
                </Author>
                <Author>
                    <LastName>Evans</LastName>
                    <ForeName>Richard</ForeName>
                </Author>
            </AuthorList>
            <Journal>
                <ISSN>0028-0836</ISSN>
                <Title>Nature</Title>
            </Journal>
            <PublicationType>Journal Article</PublicationType>
        </Article>
    </MedlineCitation>
    <PubmedData>
        <ArticleIdList>
            <ArticleId IdType="doi">10.1038/s41586-021-03819-2</ArticleId>
            <ArticleId IdType="pmc">PMC8371605</ArticleId>
        </ArticleIdList>
        <History>
            <PubMedPubDate PubStatus="pubmed">
                <Year>2021</Year>
                <Month>07</Month>
                <Day>16</Day>
            </PubMedPubDate>
        </History>
    </PubmedData>
</PubmedArticle>
</PubmedArticleSet>
"""


class TestParsePubmedXml:
    def test_parse_single_article(self):
        papers = _parse_pubmed_xml(SAMPLE_XML)
        assert len(papers) == 1
        paper = papers[0]
        assert paper.title == "Highly accurate protein structure prediction with AlphaFold"
        assert paper.ids.pmid == "34265844"
        assert paper.ids.doi == "10.1038/s41586-021-03819-2"
        assert paper.ids.pmcid == "PMC8371605"

    def test_parse_authors(self):
        papers = _parse_pubmed_xml(SAMPLE_XML)
        paper = papers[0]
        assert len(paper.authors) == 2
        assert paper.authors[0].family_name == "Jumper"
        assert paper.authors[0].given_name == "John"
        assert paper.authors[0].name == "John Jumper"
        assert paper.authors[0].orcid == "0000-0001-2345-6789"
        assert paper.authors[1].family_name == "Evans"

    def test_parse_abstract(self):
        papers = _parse_pubmed_xml(SAMPLE_XML)
        assert "Proteins are essential" in papers[0].abstract

    def test_parse_journal(self):
        papers = _parse_pubmed_xml(SAMPLE_XML)
        paper = papers[0]
        assert paper.source_venue is not None
        assert paper.source_venue.name == "Nature"
        assert paper.source_venue.issn == "0028-0836"

    def test_parse_data_sources(self):
        papers = _parse_pubmed_xml(SAMPLE_XML)
        assert "pubmed" in papers[0].data_sources

    def test_parse_pub_type(self):
        papers = _parse_pubmed_xml(SAMPLE_XML)
        assert papers[0].pub_type == "Journal Article"

    def test_parse_invalid_xml(self):
        papers = _parse_pubmed_xml("<not valid><<<")
        assert papers == []

    def test_parse_empty_set(self):
        papers = _parse_pubmed_xml(
            '<?xml version="1.0"?><PubmedArticleSet></PubmedArticleSet>'
        )
        assert papers == []

    def test_parse_article_without_title(self):
        xml = """\
<?xml version="1.0" ?>
<PubmedArticleSet>
<PubmedArticle>
    <MedlineCitation><PMID>12345</PMID><Article></Article></MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""
        papers = _parse_pubmed_xml(xml)
        assert papers == []


class TestMonthToNum:
    def test_numeric(self):
        assert _month_to_num("01") == 1
        assert _month_to_num("12") == 12

    def test_name(self):
        assert _month_to_num("Jan") == 1
        assert _month_to_num("December") == 12
        assert _month_to_num("mar") == 3

    def test_empty(self):
        assert _month_to_num("") is None

    def test_invalid(self):
        assert _month_to_num("13") is None


class TestExtractLinkIds:
    def test_extracts_ids(self):
        data = {
            "linksets": [
                {
                    "linksetdbs": [
                        {
                            "links": ["111", "222", "333"]
                        }
                    ]
                }
            ]
        }
        ids = _extract_link_ids(data)
        assert ids == ["111", "222", "333"]

    def test_empty_linksets(self):
        assert _extract_link_ids({"linksets": []}) == []

    def test_missing_linksets(self):
        assert _extract_link_ids({}) == []


# -- Integration tests (require API key) --


@pytest.mark.integration
@skip_without_pubmed_key
class TestPubMedClient:
    """Integration tests for PubMedClient (requires PUBMED_API_KEY)."""

    async def test_search_returns_papers(self, config: Config):
        async with PubMedClient(config) as client:
            papers = await client.search("fMRI brain encoding model", max_results=5)
        assert len(papers) > 0
        paper = papers[0]
        assert paper.title
        assert "pubmed" in paper.data_sources

    async def test_search_returns_pmids(self, config: Config):
        async with PubMedClient(config) as client:
            papers = await client.search("CRISPR gene editing", max_results=3)
        assert len(papers) > 0
        for p in papers:
            assert p.ids.pmid

    async def test_lookup_pmid(self, config: Config):
        async with PubMedClient(config) as client:
            paper = await client.lookup_pmid("34265844")
        assert paper is not None
        assert "AlphaFold" in paper.title or "protein" in paper.title.lower()
        assert paper.ids.pmid == "34265844"

    async def test_lookup_pmid_not_found(self, config: Config):
        async with PubMedClient(config) as client:
            paper = await client.lookup_pmid("9999999999")
        assert paper is None

    async def test_lookup_doi(self, config: Config):
        async with PubMedClient(config) as client:
            paper = await client.lookup_doi("10.1038/s41586-021-03819-2")
        assert paper is not None
        assert paper.ids.doi == "10.1038/s41586-021-03819-2"

    async def test_fetch_by_pmids(self, config: Config):
        async with PubMedClient(config) as client:
            papers = await client.fetch_by_pmids(["34265844", "33318457"])
        assert len(papers) >= 1

    async def test_citing_papers(self, config: Config):
        # PMID 34265844 is the AlphaFold paper; should have citations
        async with PubMedClient(config) as client:
            citing = await client.citing_papers("34265844", max_results=5)
        assert len(citing) > 0

    async def test_references(self, config: Config):
        async with PubMedClient(config) as client:
            refs = await client.references("34265844", max_results=5)
        assert len(refs) > 0

    async def test_paper_has_authors(self, config: Config):
        async with PubMedClient(config) as client:
            paper = await client.lookup_pmid("34265844")
        assert paper is not None
        assert len(paper.authors) > 0
        assert paper.authors[0].family_name

    async def test_paper_has_journal(self, config: Config):
        async with PubMedClient(config) as client:
            paper = await client.lookup_pmid("34265844")
        assert paper is not None
        assert paper.source_venue is not None
        assert paper.source_venue.name

    async def test_paper_has_mesh_terms(self, config: Config):
        async with PubMedClient(config) as client:
            paper = await client.lookup_pmid("34265844")
        assert paper is not None
        # MeSH terms may or may not be present, but the field should be a list
        assert isinstance(paper.mesh_terms, list)
