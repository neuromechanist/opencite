"""Tests for opencite.models."""

from __future__ import annotations

import pytest

from opencite.models import (
    Author,
    CitationResult,
    IDSet,
    IDType,
    Paper,
    PDFLocation,
    SearchResult,
    Source,
    parse_identifier,
)


class TestIDSet:
    def test_has_any_with_doi(self):
        ids = IDSet(doi="10.1234/test")
        assert ids.has_any()

    def test_has_any_empty(self):
        ids = IDSet()
        assert not ids.has_any()

    def test_best_lookup_id_doi_first(self):
        ids = IDSet(doi="10.1234/test", pmid="12345")
        id_type, value = ids.best_lookup_id()
        assert id_type == IDType.DOI
        assert value == "10.1234/test"

    def test_best_lookup_id_pmid_fallback(self):
        ids = IDSet(pmid="12345")
        id_type, value = ids.best_lookup_id()
        assert id_type == IDType.PMID
        assert value == "12345"

    def test_best_lookup_id_pmcid_fallback(self):
        ids = IDSet(pmcid="PMC999")
        id_type, value = ids.best_lookup_id()
        assert id_type == IDType.PMCID
        assert value == "PMC999"

    def test_best_lookup_id_s2_fallback(self):
        ids = IDSet(s2_id="abc123def456")
        id_type, value = ids.best_lookup_id()
        assert id_type == IDType.S2
        assert value == "abc123def456"

    def test_best_lookup_id_openalex_fallback(self):
        ids = IDSet(openalex_id="W12345")
        id_type, value = ids.best_lookup_id()
        assert id_type == IDType.OPENALEX
        assert value == "W12345"

    def test_best_lookup_id_arxiv_fallback(self):
        ids = IDSet(arxiv_id="2106.15928")
        id_type, value = ids.best_lookup_id()
        assert id_type == IDType.ARXIV
        assert value == "2106.15928"

    def test_best_lookup_id_raises_when_empty(self):
        ids = IDSet()
        with pytest.raises(ValueError, match="No identifier"):
            ids.best_lookup_id()

    def test_merge(self):
        a = IDSet(doi="10.1234/test", pmid="111")
        b = IDSet(pmcid="PMC999", s2_id="abc123")
        merged = a.merge(b)
        assert merged.doi == "10.1234/test"
        assert merged.pmid == "111"
        assert merged.pmcid == "PMC999"
        assert merged.s2_id == "abc123"

    def test_merge_prefers_first(self):
        a = IDSet(doi="10.1234/a")
        b = IDSet(doi="10.1234/b")
        merged = a.merge(b)
        assert merged.doi == "10.1234/a"

    def test_frozen(self):
        ids = IDSet(doi="10.1234/test")
        with pytest.raises(AttributeError):
            ids.doi = "changed"  # type: ignore[misc]


class TestAuthor:
    def test_citation_name_full(self):
        a = Author(name="Jane Smith", family_name="Smith", given_name="Jane")
        assert a.citation_name() == "Smith, J."

    def test_citation_name_no_given(self):
        a = Author(name="Smith", family_name="Smith")
        assert a.citation_name() == "Smith"


class TestPaper:
    def test_doi_property(self, sample_paper):
        assert sample_paper.doi == "10.48550/arXiv.1706.03762"

    def test_authors_short_multiple(self, sample_paper):
        assert sample_paper.authors_short == "Vaswani et al."

    def test_authors_short_single(self):
        p = Paper(
            title="X",
            authors=[Author(name="Smith", family_name="Smith")],
        )
        assert p.authors_short == "Smith"

    def test_authors_short_two(self):
        p = Paper(
            title="X",
            authors=[
                Author(name="Smith", family_name="Smith"),
                Author(name="Jones", family_name="Jones"),
            ],
        )
        assert p.authors_short == "Smith & Jones"

    def test_authors_short_none(self):
        p = Paper(title="X")
        assert p.authors_short == "Unknown"

    def test_best_pdf_url_prefers_published(self):
        p = Paper(
            title="X",
            pdf_locations=[
                PDFLocation(url="http://a.pdf", source="s2", version="acceptedVersion"),
                PDFLocation(
                    url="http://b.pdf", source="openalex", version="publishedVersion"
                ),
            ],
        )
        assert p.best_pdf_url == "http://b.pdf"

    def test_best_pdf_url_fallback(self):
        p = Paper(
            title="X",
            pdf_locations=[
                PDFLocation(url="http://a.pdf", source="s2"),
            ],
        )
        assert p.best_pdf_url == "http://a.pdf"

    def test_best_pdf_url_none(self):
        p = Paper(title="X")
        assert p.best_pdf_url is None

    def test_journal_property(self):
        p = Paper(title="X", source_venue=Source(name="Nature"))
        assert p.journal == "Nature"

    def test_journal_property_none(self):
        p = Paper(title="X")
        assert p.journal == ""

    def test_year_str(self):
        assert Paper(title="X", year=2024).year_str == "2024"
        assert Paper(title="X").year_str == ""


class TestParseIdentifier:
    def test_doi_pattern(self):
        id_type, value = parse_identifier("10.1038/nature12345")
        assert id_type == IDType.DOI
        assert value == "10.1038/nature12345"

    def test_doi_prefix(self):
        id_type, value = parse_identifier("doi:10.1038/nature12345")
        assert id_type == IDType.DOI
        assert value == "10.1038/nature12345"

    def test_pmid_prefix(self):
        id_type, value = parse_identifier("pmid:12345678")
        assert id_type == IDType.PMID
        assert value == "12345678"

    def test_bare_digits_as_pmid(self):
        id_type, value = parse_identifier("12345678")
        assert id_type == IDType.PMID
        assert value == "12345678"

    def test_pmcid_prefix(self):
        id_type, value = parse_identifier("pmc:PMC1234567")
        assert id_type == IDType.PMCID
        assert value == "PMC1234567"

    def test_pmcid_prefix_without_pmc_in_value(self):
        """pmc:1234567 should auto-add PMC prefix."""
        id_type, value = parse_identifier("pmc:1234567")
        assert id_type == IDType.PMCID
        assert value == "PMC1234567"

    def test_pmcid_no_prefix(self):
        id_type, value = parse_identifier("PMC1234567")
        assert id_type == IDType.PMCID
        assert value == "PMC1234567"

    def test_arxiv_prefix(self):
        id_type, value = parse_identifier("arxiv:2106.15928")
        assert id_type == IDType.ARXIV
        assert value == "2106.15928"

    def test_openalex_id(self):
        id_type, value = parse_identifier("W2741809807")
        assert id_type == IDType.OPENALEX
        assert value == "W2741809807"

    def test_s2_hex_id(self):
        hex_id = "a" * 40
        id_type, value = parse_identifier(hex_id)
        assert id_type == IDType.S2
        assert value == hex_id

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Cannot determine"):
            parse_identifier("some random text")


class TestSearchResult:
    def test_basic(self, sample_paper):
        sr = SearchResult(
            query="attention",
            papers=[sample_paper],
            total_by_source={"semanticscholar": 1},
            deduplicated_count=0,
        )
        assert len(sr.papers) == 1
        assert sr.query == "attention"


class TestCitationResult:
    def test_basic(self, sample_paper):
        cr = CitationResult(
            seed_paper=sample_paper,
            papers=[],
            direction="citing",
            total_available=0,
        )
        assert cr.direction == "citing"
        assert cr.seed_paper.title == "Attention Is All You Need"
