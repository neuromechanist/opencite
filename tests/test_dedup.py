"""Tests for deduplication and paper merging."""

from __future__ import annotations

from opencite.dedup import deduplicate, merge_papers
from opencite.models import Author, IDSet, Paper, PDFLocation, Source


def _paper(
    title: str = "Test Paper",
    doi: str = "",
    pmid: str = "",
    source: str = "test",
    abstract: str = "",
    citation_count: int = 0,
    authors: list[Author] | None = None,
    topics: list[str] | None = None,
    tldr: str = "",
    pdf_url: str = "",
    year: int | None = None,
) -> Paper:
    """Helper to create test papers."""
    pdf_locs = []
    if pdf_url:
        pdf_locs.append(PDFLocation(url=pdf_url, source=source))
    return Paper(
        title=title,
        ids=IDSet(doi=doi, pmid=pmid),
        authors=authors or [],
        year=year,
        abstract=abstract,
        citation_count=citation_count,
        topics=topics or [],
        tldr=tldr,
        pdf_locations=pdf_locs,
        data_sources={source},
    )


class TestDeduplicate:
    def test_no_duplicates(self):
        papers = [
            _paper("Attention Is All You Need", doi="10.1/a"),
            _paper(
                "BERT Pre-training of Deep Bidirectional Transformers", doi="10.1/b"
            ),
        ]
        result = deduplicate(papers)
        assert len(result) == 2

    def test_doi_dedup(self):
        papers = [
            _paper("Paper A", doi="10.1/a", source="openalex"),
            _paper("Paper A", doi="10.1/a", source="s2"),
        ]
        result = deduplicate(papers)
        assert len(result) == 1
        assert result[0].data_sources == {"openalex", "s2"}

    def test_doi_case_insensitive(self):
        papers = [
            _paper("Paper A", doi="10.1/ABC", source="openalex"),
            _paper("Paper A", doi="10.1/abc", source="s2"),
        ]
        result = deduplicate(papers)
        assert len(result) == 1

    def test_pmid_dedup(self):
        papers = [
            _paper("Paper A", pmid="12345", source="pubmed"),
            _paper("Paper A", pmid="12345", source="openalex"),
        ]
        result = deduplicate(papers)
        assert len(result) == 1
        assert result[0].data_sources == {"pubmed", "openalex"}

    def test_fuzzy_title_dedup(self):
        papers = [
            _paper("Attention Is All You Need", source="openalex"),
            _paper("Attention is All You Need!", source="s2"),
        ]
        result = deduplicate(papers)
        assert len(result) == 1

    def test_different_titles_not_deduped(self):
        papers = [
            _paper("Attention Is All You Need"),
            _paper("BERT: Pre-training of Deep Bidirectional Transformers"),
        ]
        result = deduplicate(papers)
        assert len(result) == 2

    def test_empty_list(self):
        assert deduplicate([]) == []

    def test_single_paper(self):
        papers = [_paper("Solo Paper")]
        result = deduplicate(papers)
        assert len(result) == 1

    def test_three_sources_same_paper(self):
        papers = [
            _paper("AlphaFold", doi="10.1038/s41586-021-03819-2", source="openalex"),
            _paper("AlphaFold", doi="10.1038/s41586-021-03819-2", source="s2"),
            _paper("AlphaFold", doi="10.1038/s41586-021-03819-2", source="pubmed"),
        ]
        result = deduplicate(papers)
        assert len(result) == 1
        assert result[0].data_sources == {"openalex", "s2", "pubmed"}


class TestMergePapers:
    def test_merge_ids(self):
        a = _paper("Test", doi="10.1/a", source="openalex")
        b = _paper("Test", pmid="12345", source="pubmed")
        merged = merge_papers(a, b)
        assert merged.ids.doi == "10.1/a"
        assert merged.ids.pmid == "12345"

    def test_merge_data_sources(self):
        a = _paper("Test", source="openalex")
        b = _paper("Test", source="s2")
        merged = merge_papers(a, b)
        assert merged.data_sources == {"openalex", "s2"}

    def test_prefer_longer_abstract(self):
        a = _paper("Test", abstract="Short.")
        b = _paper("Test", abstract="This is a much longer abstract with more detail.")
        merged = merge_papers(a, b)
        assert merged.abstract == b.abstract

    def test_merge_tldr(self):
        a = _paper("Test", tldr="")
        b = _paper("Test", tldr="A concise summary.")
        merged = merge_papers(a, b)
        assert merged.tldr == "A concise summary."

    def test_higher_citation_count(self):
        a = _paper("Test", citation_count=50)
        b = _paper("Test", citation_count=100)
        merged = merge_papers(a, b)
        assert merged.citation_count == 100

    def test_prefer_more_authors(self):
        a = _paper(
            "Test",
            authors=[
                Author(name="Smith", family_name="Smith"),
            ],
        )
        b = _paper(
            "Test",
            authors=[
                Author(name="Alice Smith", family_name="Smith", given_name="Alice"),
                Author(name="Bob Jones", family_name="Jones", given_name="Bob"),
            ],
        )
        merged = merge_papers(a, b)
        assert len(merged.authors) == 2

    def test_merge_pdf_locations(self):
        a = _paper("Test", pdf_url="https://example.com/a.pdf")
        b = _paper("Test", pdf_url="https://example.com/b.pdf")
        merged = merge_papers(a, b)
        assert len(merged.pdf_locations) == 2

    def test_merge_pdf_locations_no_duplicates(self):
        a = _paper("Test", pdf_url="https://example.com/same.pdf")
        b = _paper("Test", pdf_url="https://example.com/same.pdf")
        merged = merge_papers(a, b)
        assert len(merged.pdf_locations) == 1

    def test_merge_topics(self):
        a = _paper("Test", topics=["Machine Learning", "NLP"])
        b = _paper("Test", topics=["NLP", "Computer Vision"])
        merged = merge_papers(a, b)
        assert len(merged.topics) == 3
        assert "Machine Learning" in merged.topics
        assert "Computer Vision" in merged.topics

    def test_merge_is_oa(self):
        a_with_oa = Paper(title="Test", ids=IDSet(), is_oa=True, data_sources={"a"})
        b = _paper("Test")
        merged = merge_papers(b, a_with_oa)
        assert merged.is_oa is True

    def test_merge_source_venue(self):
        a = _paper("Test")
        b = Paper(
            title="Test",
            ids=IDSet(),
            source_venue=Source(name="Nature"),
            data_sources={"b"},
        )
        merged = merge_papers(a, b)
        assert merged.source_venue is not None
        assert merged.source_venue.name == "Nature"

    def test_merge_year(self):
        a = _paper("Test", year=None)
        b = _paper("Test", year=2021)
        merged = merge_papers(a, b)
        assert merged.year == 2021

    def test_merge_grants(self):
        a = Paper(
            title="Test",
            ids=IDSet(),
            grants=[{"funder": "NIH", "award_id": "R01"}],
            data_sources={"a"},
        )
        b = Paper(
            title="Test",
            ids=IDSet(),
            grants=[
                {"funder": "NIH", "award_id": "R01"},
                {"funder": "NSF", "award_id": "1234"},
            ],
            data_sources={"b"},
        )
        merged = merge_papers(a, b)
        assert len(merged.grants) == 2

    def test_merge_grants_empty(self):
        a = _paper("Test")
        b = Paper(
            title="Test",
            ids=IDSet(),
            grants=[{"funder": "NIH", "award_id": "R01"}],
            data_sources={"b"},
        )
        merged = merge_papers(a, b)
        assert len(merged.grants) == 1

    def test_merge_mesh_terms(self):
        a = Paper(
            title="Test",
            ids=IDSet(),
            mesh_terms=["Brain", "Imaging"],
            data_sources={"a"},
        )
        b = Paper(
            title="Test",
            ids=IDSet(),
            mesh_terms=["Brain", "Neurons"],
            data_sources={"b"},
        )
        merged = merge_papers(a, b)
        assert len(merged.mesh_terms) == 3

    def test_merge_keywords(self):
        a = Paper(
            title="Test",
            ids=IDSet(),
            keywords=["fMRI", "encoding"],
            data_sources={"a"},
        )
        b = Paper(
            title="Test",
            ids=IDSet(),
            keywords=["fmri", "decoding"],
            data_sources={"b"},
        )
        merged = merge_papers(a, b)
        # "fMRI" and "fmri" should deduplicate (case-insensitive)
        assert len(merged.keywords) == 3

    def test_merge_publication_date(self):
        a = _paper("Test")
        b = Paper(
            title="Test",
            ids=IDSet(),
            publication_date="2024-01-15",
            data_sources={"b"},
        )
        merged = merge_papers(a, b)
        assert merged.publication_date == "2024-01-15"

    def test_merge_pub_type(self):
        a = _paper("Test")
        b = Paper(
            title="Test",
            ids=IDSet(),
            pub_type="journal-article",
            data_sources={"b"},
        )
        merged = merge_papers(a, b)
        assert merged.pub_type == "journal-article"

    def test_merge_url(self):
        a = _paper("Test")
        b = Paper(
            title="Test",
            ids=IDSet(),
            url="https://example.com/paper",
            data_sources={"b"},
        )
        merged = merge_papers(a, b)
        assert merged.url == "https://example.com/paper"

    def test_merge_bibtex(self):
        a = Paper(
            title="Test",
            ids=IDSet(),
            _bibtex="@article{a, title={Test}}",
            data_sources={"a"},
        )
        b = _paper("Test")
        merged = merge_papers(a, b)
        assert merged._bibtex == "@article{a, title={Test}}"

    def test_merge_is_retracted(self):
        a = _paper("Test")
        b = Paper(
            title="Test",
            ids=IDSet(),
            is_retracted=True,
            data_sources={"b"},
        )
        merged = merge_papers(a, b)
        assert merged.is_retracted is True

    def test_merge_influential_citation_count(self):
        a = Paper(
            title="Test",
            ids=IDSet(),
            influential_citation_count=10,
            data_sources={"a"},
        )
        b = Paper(
            title="Test",
            ids=IDSet(),
            influential_citation_count=25,
            data_sources={"b"},
        )
        merged = merge_papers(a, b)
        assert merged.influential_citation_count == 25
