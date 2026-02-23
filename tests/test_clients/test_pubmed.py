"""Tests for the PubMed API client."""

from __future__ import annotations

import pytest

from opencite.clients.pubmed import (
    PubMedClient,
    _extract_authors,
    _extract_link_ids,
    _extract_pub_date,
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
        assert (
            paper.title == "Highly accurate protein structure prediction with AlphaFold"
        )
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
        data = {"linksets": [{"linksetdbs": [{"links": ["111", "222", "333"]}]}]}
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


# -- Additional XML parsing unit tests --


FULL_ARTICLE_XML = """\
<?xml version="1.0" ?>
<PubmedArticleSet>
<PubmedArticle>
    <MedlineCitation>
        <PMID>99999999</PMID>
        <Article>
            <ArticleTitle>A <i>Novel</i> Approach to Brain Imaging</ArticleTitle>
            <Abstract>
                <AbstractText Label="BACKGROUND">Brain imaging is important.</AbstractText>
                <AbstractText Label="METHODS">We used fMRI.</AbstractText>
            </Abstract>
            <AuthorList>
                <Author>
                    <LastName>Smith</LastName>
                    <ForeName>John A</ForeName>
                    <Identifier Source="ORCID">https://orcid.org/0000-0001-1111-2222</Identifier>
                </Author>
                <Author>
                    <LastName>Doe</LastName>
                    <ForeName>Jane</ForeName>
                </Author>
                <Author>
                    <CollectiveName>Brain Consortium</CollectiveName>
                </Author>
            </AuthorList>
            <Journal>
                <ISSN>1234-5678</ISSN>
                <Title>NeuroImage</Title>
                <JournalIssue>
                    <PubDate>
                        <Year>2024</Year>
                        <Month>Mar</Month>
                        <Day>15</Day>
                    </PubDate>
                </JournalIssue>
            </Journal>
            <PublicationType>Journal Article</PublicationType>
            <PublicationType>Research Support, N.I.H.</PublicationType>
        </Article>
        <MeshHeadingList>
            <MeshHeading>
                <DescriptorName>Brain</DescriptorName>
            </MeshHeading>
            <MeshHeading>
                <DescriptorName>Magnetic Resonance Imaging</DescriptorName>
            </MeshHeading>
        </MeshHeadingList>
        <KeywordList>
            <Keyword>fMRI</Keyword>
            <Keyword>brain encoding</Keyword>
        </KeywordList>
    </MedlineCitation>
    <PubmedData>
        <ArticleIdList>
            <ArticleId IdType="doi">10.1016/j.neuroimage.2024.001</ArticleId>
            <ArticleId IdType="pmc">PMC9999999</ArticleId>
        </ArticleIdList>
    </PubmedData>
</PubmedArticle>
</PubmedArticleSet>
"""

GRANT_XML = """\
<?xml version="1.0" ?>
<PubmedArticleSet>
<PubmedArticle>
    <MedlineCitation>
        <PMID>88888888</PMID>
        <Article>
            <ArticleTitle>Funded Research Paper</ArticleTitle>
            <Abstract><AbstractText>Some abstract.</AbstractText></Abstract>
            <AuthorList>
                <Author>
                    <LastName>Grant</LastName>
                    <ForeName>Bob</ForeName>
                </Author>
            </AuthorList>
            <GrantList>
                <Grant>
                    <GrantID>R01-NS123456</GrantID>
                    <Agency>NIH</Agency>
                </Grant>
                <Grant>
                    <GrantID>ERC-2020-StG</GrantID>
                    <Agency>European Research Council</Agency>
                </Grant>
            </GrantList>
        </Article>
    </MedlineCitation>
    <PubmedData>
        <ArticleIdList>
            <ArticleId IdType="doi">10.1234/grants</ArticleId>
        </ArticleIdList>
    </PubmedData>
</PubmedArticle>
</PubmedArticleSet>
"""

MEDLINE_DATE_XML = """\
<?xml version="1.0" ?>
<PubmedArticleSet>
<PubmedArticle>
    <MedlineCitation>
        <PMID>77777777</PMID>
        <Article>
            <ArticleTitle>MedlineDate Format Paper</ArticleTitle>
            <Journal>
                <Title>Some Journal</Title>
                <JournalIssue>
                    <PubDate>
                        <MedlineDate>2023 Jan-Feb</MedlineDate>
                    </PubDate>
                </JournalIssue>
            </Journal>
            <AuthorList>
                <Author><LastName>Test</LastName><ForeName>A</ForeName></Author>
            </AuthorList>
        </Article>
    </MedlineCitation>
    <PubmedData>
        <ArticleIdList />
    </PubmedData>
</PubmedArticle>
</PubmedArticleSet>
"""


class TestParseFullArticle:
    """Test _parse_article with richer XML including mixed content, MeSH, keywords."""

    def test_mixed_content_title(self):
        papers = _parse_pubmed_xml(FULL_ARTICLE_XML)
        assert len(papers) == 1
        # Mixed content <i>Novel</i> should be extracted
        assert "Novel" in papers[0].title
        assert "Brain Imaging" in papers[0].title

    def test_labeled_abstract(self):
        papers = _parse_pubmed_xml(FULL_ARTICLE_XML)
        abstract = papers[0].abstract
        assert "BACKGROUND: Brain imaging is important." in abstract
        assert "METHODS: We used fMRI." in abstract

    def test_collective_author(self):
        papers = _parse_pubmed_xml(FULL_ARTICLE_XML)
        authors = papers[0].authors
        # 3 authors: Smith, Doe, Brain Consortium
        assert len(authors) == 3
        assert authors[2].name == "Brain Consortium"
        assert authors[2].family_name == "Brain Consortium"

    def test_orcid_stripped_from_url(self):
        papers = _parse_pubmed_xml(FULL_ARTICLE_XML)
        assert papers[0].authors[0].orcid == "0000-0001-1111-2222"

    def test_mesh_terms(self):
        papers = _parse_pubmed_xml(FULL_ARTICLE_XML)
        assert "Brain" in papers[0].mesh_terms
        assert "Magnetic Resonance Imaging" in papers[0].mesh_terms

    def test_keywords_as_topics(self):
        papers = _parse_pubmed_xml(FULL_ARTICLE_XML)
        assert "fMRI" in papers[0].topics
        assert "brain encoding" in papers[0].topics

    def test_pub_type_first_only(self):
        papers = _parse_pubmed_xml(FULL_ARTICLE_XML)
        assert papers[0].pub_type == "Journal Article"

    def test_pub_date_iso(self):
        papers = _parse_pubmed_xml(FULL_ARTICLE_XML)
        assert papers[0].publication_date == "2024-03-15"

    def test_year_extraction(self):
        papers = _parse_pubmed_xml(FULL_ARTICLE_XML)
        assert papers[0].year == 2024


class TestParseGrants:
    def test_grants_extracted(self):
        papers = _parse_pubmed_xml(GRANT_XML)
        assert len(papers) == 1
        grants = papers[0].grants
        assert len(grants) == 2
        assert grants[0]["award_id"] == "R01-NS123456"
        assert grants[0]["funder"] == "NIH"
        assert grants[1]["award_id"] == "ERC-2020-StG"
        assert grants[1]["funder"] == "European Research Council"


class TestParseMedlineDate:
    def test_medline_date_year(self):
        papers = _parse_pubmed_xml(MEDLINE_DATE_XML)
        assert len(papers) == 1
        assert papers[0].year == 2023


class TestExtractPubDate:
    """Test _extract_pub_date with various month formats."""

    @staticmethod
    def _make_article(year, month=None, day=None):
        import xml.etree.ElementTree as ET

        xml = f"""<PubmedArticle><Article><Journal><JournalIssue>
            <PubDate>
                <Year>{year}</Year>"""
        if month:
            xml += f"<Month>{month}</Month>"
        if day:
            xml += f"<Day>{day}</Day>"
        xml += "</PubDate></JournalIssue></Journal></Article></PubmedArticle>"
        return ET.fromstring(xml)

    def test_full_date(self):
        article = self._make_article("2024", "06", "15")
        assert _extract_pub_date(article) == "2024-06-15"

    def test_year_month_only(self):
        article = self._make_article("2024", "11")
        assert _extract_pub_date(article) == "2024-11"

    def test_year_only(self):
        article = self._make_article("2024")
        assert _extract_pub_date(article) == "2024"

    def test_month_name(self):
        article = self._make_article("2024", "Jan", "01")
        assert _extract_pub_date(article) == "2024-01-01"


class TestExtractAuthors:
    """Test _extract_authors edge cases."""

    @staticmethod
    def _make_author_xml(author_xml):
        import xml.etree.ElementTree as ET

        xml = f"<Article><AuthorList>{author_xml}</AuthorList></Article>"
        return ET.fromstring(xml)

    def test_author_without_forename(self):
        elem = self._make_author_xml("<Author><LastName>OnlyLast</LastName></Author>")
        authors = _extract_authors(elem)
        assert len(authors) == 1
        assert authors[0].family_name == "OnlyLast"
        assert authors[0].given_name == ""
        assert authors[0].name == "OnlyLast"

    def test_author_without_lastname_skipped(self):
        elem = self._make_author_xml("<Author><ForeName>NoLast</ForeName></Author>")
        authors = _extract_authors(elem)
        assert len(authors) == 0

    def test_max_50_authors(self):
        author_xml = "".join(
            f"<Author><LastName>Author{i}</LastName><ForeName>A</ForeName></Author>"
            for i in range(60)
        )
        elem = self._make_author_xml(author_xml)
        authors = _extract_authors(elem)
        assert len(authors) == 50
