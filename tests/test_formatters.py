"""Tests for output formatters."""

from __future__ import annotations

import json

from opencite.formatters import BibtexFormatter, CsvFormatter, get_formatter
from opencite.models import Author, IDSet, Paper, Source


def _sample_paper() -> Paper:
    return Paper(
        title="Attention Is All You Need",
        ids=IDSet(doi="10.5555/3295222.3295349", pmid="12345"),
        authors=[
            Author(name="Vaswani, Ashish", family_name="Vaswani", given_name="Ashish"),
            Author(name="Shazeer, Noam", family_name="Shazeer", given_name="Noam"),
        ],
        year=2017,
        source_venue=Source(name="NeurIPS"),
        citation_count=100000,
        url="https://arxiv.org/abs/1706.03762",
        is_oa=True,
        data_sources={"openalex", "s2"},
    )


class TestGetFormatter:
    def test_text(self):
        f = get_formatter("text")
        assert f.__class__.__name__ == "TextFormatter"

    def test_json(self):
        f = get_formatter("json")
        assert f.__class__.__name__ == "JsonFormatter"

    def test_bibtex(self):
        f = get_formatter("bibtex")
        assert isinstance(f, BibtexFormatter)

    def test_csv(self):
        f = get_formatter("csv")
        assert isinstance(f, CsvFormatter)

    def test_default(self):
        f = get_formatter("unknown")
        assert f.__class__.__name__ == "TextFormatter"


class TestBibtexFormatter:
    def test_format_single(self):
        paper = _sample_paper()
        f = BibtexFormatter()
        output = f.format_single(paper)
        assert output.startswith("@article{")
        assert "Attention Is All You Need" in output

    def test_format_single_with_cached(self):
        paper = _sample_paper()
        paper._bibtex = "@article{cached, title={Cached}}"
        f = BibtexFormatter()
        output = f.format_single(paper)
        assert output == "@article{cached, title={Cached}}"

    def test_format_papers(self):
        papers = [_sample_paper(), _sample_paper()]
        papers[1] = Paper(title="Another Paper", year=2020)
        f = BibtexFormatter()
        output = f.format_papers(papers)
        entries = output.split("\n\n")
        assert len(entries) == 2

    def test_format_papers_empty(self):
        f = BibtexFormatter()
        output = f.format_papers([])
        assert output == ""


class TestCsvFormatter:
    def test_format_single(self):
        paper = _sample_paper()
        f = CsvFormatter()
        output = f.format_single(paper)
        lines = output.strip().split("\n")
        assert len(lines) == 2  # header + 1 row
        assert "title" in lines[0]
        assert "Attention Is All You Need" in lines[1]

    def test_format_papers(self):
        papers = [_sample_paper(), Paper(title="Another Paper", year=2020)]
        f = CsvFormatter()
        output = f.format_papers(papers)
        lines = output.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows

    def test_csv_fields(self):
        paper = _sample_paper()
        f = CsvFormatter()
        output = f.format_single(paper)
        header = output.split("\n")[0]
        for field in [
            "title",
            "authors",
            "year",
            "doi",
            "pmid",
            "journal",
            "citation_count",
        ]:
            assert field in header

    def test_csv_values(self):
        paper = _sample_paper()
        f = CsvFormatter()
        output = f.format_single(paper)
        row = output.split("\n")[1]
        assert "10.5555/3295222.3295349" in row
        assert "12345" in row  # PMID
        assert "NeurIPS" in row
        assert "100000" in row

    def test_format_papers_empty(self):
        f = CsvFormatter()
        output = f.format_papers([])
        lines = output.strip().split("\n")
        assert len(lines) == 1  # just header


class TestTextFormatter:
    def test_format_papers(self):
        f = get_formatter("text")
        output = f.format_papers([_sample_paper()])
        assert "Vaswani & Shazeer" in output
        assert "(2017)" in output
        assert "Attention Is All You Need" in output

    def test_no_results(self):
        f = get_formatter("text")
        output = f.format_papers([])
        assert "No results" in output

    def test_format_single(self):
        f = get_formatter("text")
        output = f.format_single(_sample_paper())
        assert "[1]" in output
        assert "Vaswani & Shazeer" in output
        assert "Attention Is All You Need" in output

    def test_format_papers_count_label_singular(self):
        f = get_formatter("text")
        output = f.format_papers([_sample_paper()])
        assert "1 result" in output

    def test_format_papers_count_label_plural(self):
        f = get_formatter("text")
        output = f.format_papers([_sample_paper(), Paper(title="Other", year=2020)])
        assert "2 results" in output

    def test_includes_doi(self):
        f = get_formatter("text")
        output = f.format_single(_sample_paper())
        assert "DOI: 10.5555/3295222.3295349" in output

    def test_includes_citation_count(self):
        f = get_formatter("text")
        output = f.format_single(_sample_paper())
        assert "Cited: 100000" in output

    def test_includes_journal(self):
        f = get_formatter("text")
        output = f.format_single(_sample_paper())
        assert "Journal: NeurIPS" in output

    def test_includes_url(self):
        f = get_formatter("text")
        output = f.format_single(_sample_paper())
        assert "https://arxiv.org/abs/1706.03762" in output

    def test_includes_pmid(self):
        f = get_formatter("text")
        output = f.format_single(_sample_paper())
        assert "PMID: 12345" in output

    def test_verbose_includes_abstract(self):
        paper = Paper(
            title="Test",
            abstract="This is a test abstract.",
            year=2024,
        )
        f = get_formatter("text")
        output = f.format_single(paper, verbose=True)
        assert "Abstract: This is a test abstract." in output

    def test_verbose_truncates_long_abstract(self):
        paper = Paper(
            title="Test",
            abstract="A" * 400,
            year=2024,
        )
        f = get_formatter("text")
        output = f.format_single(paper, verbose=True)
        assert "..." in output

    def test_verbose_includes_tldr(self):
        paper = Paper(
            title="Test",
            tldr="Short summary of the paper.",
            year=2024,
        )
        f = get_formatter("text")
        output = f.format_single(paper, verbose=True)
        assert "TLDR: Short summary of the paper." in output

    def test_missing_fields_no_crash(self):
        paper = Paper(title="Bare Paper")
        f = get_formatter("text")
        output = f.format_single(paper)
        assert "Bare Paper" in output
        assert "Unknown" in output  # authors_short

    def test_includes_pmcid(self):
        paper = Paper(title="Test", ids=IDSet(pmcid="PMC12345"), year=2024)
        f = get_formatter("text")
        output = f.format_single(paper)
        assert "PMCID: PMC12345" in output

    def test_includes_openalex_id(self):
        paper = Paper(title="Test", ids=IDSet(openalex_id="W123456"), year=2024)
        f = get_formatter("text")
        output = f.format_single(paper)
        assert "OpenAlex: W123456" in output


class TestJsonFormatter:
    def test_format_papers(self):
        f = get_formatter("json")
        output = f.format_papers([_sample_paper()])
        data = json.loads(output)
        assert len(data) == 1
        assert data[0]["title"] == "Attention Is All You Need"
        assert data[0]["year"] == 2017
        assert data[0]["ids"]["doi"] == "10.5555/3295222.3295349"

    def test_format_single(self):
        f = get_formatter("json")
        output = f.format_single(_sample_paper())
        data = json.loads(output)
        assert data["title"] == "Attention Is All You Need"
        assert data["citation_count"] == 100000
        assert data["is_oa"] is True
        assert data["url"] == "https://arxiv.org/abs/1706.03762"
        assert "openalex" in data["data_sources"]
        assert "s2" in data["data_sources"]

    def test_format_single_includes_authors(self):
        f = get_formatter("json")
        output = f.format_single(_sample_paper())
        data = json.loads(output)
        assert len(data["authors"]) == 2
        assert data["authors"][0]["name"] == "Vaswani, Ashish"
        assert data["authors"][0]["family_name"] == "Vaswani"
        assert data["authors"][0]["given_name"] == "Ashish"

    def test_optional_fields_omitted_when_empty(self):
        paper = Paper(title="Bare Paper", year=2024)
        f = get_formatter("json")
        output = f.format_single(paper)
        data = json.loads(output)
        assert "journal" not in data
        assert "publication_date" not in data
        assert "pub_type" not in data
        assert "is_retracted" not in data

    def test_optional_fields_present_when_set(self):
        paper = Paper(
            title="Full Paper",
            year=2024,
            source_venue=Source(name="Nature"),
            publication_date="2024-01-15",
            pub_type="journal-article",
            is_retracted=True,
        )
        f = get_formatter("json")
        output = f.format_single(paper)
        data = json.loads(output)
        assert data["journal"] == "Nature"
        assert data["publication_date"] == "2024-01-15"
        assert data["pub_type"] == "journal-article"
        assert data["is_retracted"] is True

    def test_verbose_includes_abstract_and_tldr(self):
        from opencite.models import PDFLocation

        paper = Paper(
            title="Test",
            year=2024,
            abstract="This is the abstract.",
            tldr="Short summary.",
            topics=["AI", "ML"],
            mesh_terms=["Brain"],
            pdf_locations=[
                PDFLocation(url="https://example.com/test.pdf", source="s2", is_oa=True)
            ],
            grants=[{"funder": "NIH", "award_id": "R01"}],
        )
        f = get_formatter("json")
        output = f.format_single(paper, verbose=True)
        data = json.loads(output)
        assert data["abstract"] == "This is the abstract."
        assert data["tldr"] == "Short summary."
        assert data["topics"] == ["AI", "ML"]
        assert data["mesh_terms"] == ["Brain"]
        assert len(data["pdf_locations"]) == 1
        assert data["grants"] == [{"funder": "NIH", "award_id": "R01"}]

    def test_non_verbose_omits_abstract(self):
        paper = Paper(title="Test", abstract="Some abstract", year=2024)
        f = get_formatter("json")
        output = f.format_single(paper, verbose=False)
        data = json.loads(output)
        assert "abstract" not in data
