"""Tests for bibtex module."""

from __future__ import annotations

from opencite.bibtex import _format_authors_bibtex, _make_cite_key, generate_bibtex
from opencite.models import Author, Paper


class TestMakeCiteKey:
    def test_basic(self):
        paper = Paper(
            title="Attention Is All You Need",
            authors=[
                Author(
                    name="Vaswani, Ashish", family_name="Vaswani", given_name="Ashish"
                )
            ],
            year=2017,
        )
        assert _make_cite_key(paper) == "vaswani2017attention"

    def test_no_authors(self):
        paper = Paper(title="Some Paper", year=2020)
        key = _make_cite_key(paper)
        assert key == "unknown2020some"

    def test_no_year(self):
        paper = Paper(
            title="A Paper",
            authors=[Author(name="Smith, John", family_name="Smith")],
        )
        key = _make_cite_key(paper)
        assert key == "smitha"

    def test_special_chars_in_name(self):
        paper = Paper(
            title="Test Paper",
            authors=[Author(name="O'Brien, James", family_name="O'Brien")],
            year=2021,
        )
        key = _make_cite_key(paper)
        assert key == "obrien2021test"


class TestFormatAuthorsBibtex:
    def test_single_author(self):
        paper = Paper(
            title="Test",
            authors=[
                Author(name="Smith, John", family_name="Smith", given_name="John")
            ],
        )
        assert _format_authors_bibtex(paper) == "Smith, John"

    def test_multiple_authors(self):
        paper = Paper(
            title="Test",
            authors=[
                Author(name="Smith, John", family_name="Smith", given_name="John"),
                Author(name="Doe, Jane", family_name="Doe", given_name="Jane"),
            ],
        )
        assert _format_authors_bibtex(paper) == "Smith, John and Doe, Jane"

    def test_no_structured_name(self):
        paper = Paper(
            title="Test",
            authors=[Author(name="J. Smith")],
        )
        assert _format_authors_bibtex(paper) == "J. Smith"

    def test_empty(self):
        paper = Paper(title="Test")
        assert _format_authors_bibtex(paper) == ""


class TestGenerateBibtex:
    def test_full_entry(self):
        from opencite.models import IDSet, Source

        paper = Paper(
            title="Attention Is All You Need",
            ids=IDSet(doi="10.5555/3295222.3295349"),
            authors=[
                Author(
                    name="Vaswani, Ashish", family_name="Vaswani", given_name="Ashish"
                ),
            ],
            year=2017,
            source_venue=Source(name="NeurIPS"),
            url="https://example.com",
        )
        bib = generate_bibtex(paper)
        assert bib.startswith("@article{vaswani2017attention,")
        assert "title = {Attention Is All You Need}" in bib
        assert "author = {Vaswani, Ashish}" in bib
        assert "journal = {NeurIPS}" in bib
        assert "year = {2017}" in bib
        assert "doi = {10.5555/3295222.3295349}" in bib
        assert "url = {https://example.com}" in bib

    def test_minimal_entry(self):
        paper = Paper(title="A Simple Paper")
        bib = generate_bibtex(paper)
        assert bib.startswith("@article{")
        assert "title = {A Simple Paper}" in bib
        assert "author" not in bib
        assert "journal" not in bib
