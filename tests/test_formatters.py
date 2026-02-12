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


class TestJsonFormatter:
    def test_format_papers(self):
        f = get_formatter("json")
        output = f.format_papers([_sample_paper()])
        data = json.loads(output)
        assert len(data) == 1
        assert data[0]["title"] == "Attention Is All You Need"
        assert data[0]["year"] == 2017
        assert data[0]["ids"]["doi"] == "10.5555/3295222.3295349"
