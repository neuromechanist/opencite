"""Tests for BioC JSON to markdown conversion."""

from __future__ import annotations

from opencite.pmc_convert import (
    _format_table_text,
    _is_image_file,
    bioc_to_markdown,
    extract_figure_files,
    extract_metadata,
)


def _make_passage(
    text: str,
    section_type: str = "",
    ptype: str = "paragraph",
    **extra_infons: str,
) -> dict:
    """Helper to create a BioC passage dict."""
    infons = {"section_type": section_type, "type": ptype}
    infons.update(extra_infons)
    return {
        "infons": infons,
        "text": text,
        "sentences": [],
        "annotations": [],
        "relations": [],
    }


def _make_document(passages: list[dict]) -> dict:
    """Wrap passages in a document dict."""
    return {"id": "PMC12345", "infons": {}, "passages": passages}


class TestBiocToMarkdown:
    def test_empty_document(self):
        doc = _make_document([])
        assert bioc_to_markdown(doc) == ""

    def test_title_only(self):
        doc = _make_document(
            [
                _make_passage("My Article Title", section_type="TITLE", ptype="front"),
            ]
        )
        md = bioc_to_markdown(doc)
        assert md.startswith("# My Article Title")

    def test_abstract(self):
        doc = _make_document(
            [
                _make_passage("My Article", section_type="TITLE", ptype="front"),
                _make_passage(
                    "This is the abstract.", section_type="ABSTRACT", ptype="abstract"
                ),
            ]
        )
        md = bioc_to_markdown(doc)
        assert "## Abstract" in md
        assert "This is the abstract." in md

    def test_intro_with_explicit_heading(self):
        doc = _make_document(
            [
                _make_passage("Background", section_type="INTRO", ptype="title_1"),
                _make_passage(
                    "Some intro text.", section_type="INTRO", ptype="paragraph"
                ),
            ]
        )
        md = bioc_to_markdown(doc)
        assert "## Background" in md
        assert "Some intro text." in md

    def test_intro_with_default_heading(self):
        doc = _make_document(
            [
                _make_passage(
                    "Some intro text.", section_type="INTRO", ptype="paragraph"
                ),
            ]
        )
        md = bioc_to_markdown(doc)
        assert "## Introduction" in md

    def test_subsection_heading(self):
        doc = _make_document(
            [
                _make_passage("Methods", section_type="METHODS", ptype="title_1"),
                _make_passage("Sub-section", section_type="METHODS", ptype="title_2"),
                _make_passage("Details.", section_type="METHODS", ptype="paragraph"),
            ]
        )
        md = bioc_to_markdown(doc)
        assert "## Methods" in md
        assert "### Sub-section" in md
        assert "Details." in md

    def test_figure_with_image(self):
        doc = _make_document(
            [
                _make_passage(
                    "A schematic of the system.",
                    section_type="FIG",
                    ptype="fig_caption",
                    file="fig1.jpg",
                    id="F1",
                ),
            ]
        )
        md = bioc_to_markdown(doc)
        assert "![F1](fig1.jpg)" in md
        assert "**Figure F1**:" in md
        assert "A schematic of the system." in md

    def test_figure_with_images_dir(self):
        doc = _make_document(
            [
                _make_passage(
                    "Caption.",
                    section_type="FIG",
                    ptype="fig_caption",
                    file="fig1.png",
                    id="F1",
                ),
            ]
        )
        md = bioc_to_markdown(doc, images_dir="img/paper1")
        assert "![F1](img/paper1/fig1.png)" in md

    def test_figure_with_xml_file_no_image(self):
        doc = _make_document(
            [
                _make_passage(
                    "Table data.",
                    section_type="FIG",
                    ptype="fig_caption",
                    file="table.xml",
                    id="T1",
                ),
            ]
        )
        md = bioc_to_markdown(doc)
        assert "![" not in md
        assert "Table data." in md

    def test_table_caption(self):
        doc = _make_document(
            [
                _make_passage(
                    "Patient demographics.",
                    section_type="TABLE",
                    ptype="table_caption",
                    id="T1",
                ),
            ]
        )
        md = bioc_to_markdown(doc)
        assert "**Table T1**:" in md

    def test_table_content(self):
        doc = _make_document(
            [
                _make_passage(
                    "Name\tAge\tStatus\nAlice\t30\tActive",
                    section_type="TABLE",
                    ptype="table",
                ),
            ]
        )
        md = bioc_to_markdown(doc)
        assert "| Name | Age | Status |" in md
        assert "| Alice | 30 | Active |" in md
        assert "| --- | --- | --- |" in md

    def test_references(self):
        doc = _make_document(
            [
                _make_passage(
                    "Smith J. et al. (2020). Title. Journal.",
                    section_type="REF",
                    ptype="ref",
                ),
                _make_passage(
                    "Doe A. et al. (2019). Title. Journal.",
                    section_type="REF",
                    ptype="ref",
                ),
            ]
        )
        md = bioc_to_markdown(doc)
        assert "## References" in md
        assert "- Smith J. et al." in md
        assert "- Doe A. et al." in md

    def test_references_heading_not_duplicated(self):
        doc = _make_document(
            [
                _make_passage("Ref 1.", section_type="REF", ptype="ref"),
                _make_passage("Ref 2.", section_type="REF", ptype="ref"),
            ]
        )
        md = bioc_to_markdown(doc)
        assert md.count("## References") == 1

    def test_footnote(self):
        doc = _make_document(
            [
                _make_passage(
                    "This is a footnote.", section_type="INTRO", ptype="footnote"
                ),
            ]
        )
        md = bioc_to_markdown(doc)
        assert "> This is a footnote." in md

    def test_multiple_sections(self):
        doc = _make_document(
            [
                _make_passage("Title", section_type="TITLE", ptype="front"),
                _make_passage(
                    "Abstract text.", section_type="ABSTRACT", ptype="abstract"
                ),
                _make_passage("Introduction", section_type="INTRO", ptype="title_1"),
                _make_passage("Intro text.", section_type="INTRO", ptype="paragraph"),
                _make_passage("Methods", section_type="METHODS", ptype="title_1"),
                _make_passage(
                    "Methods text.", section_type="METHODS", ptype="paragraph"
                ),
                _make_passage("Results", section_type="RESULTS", ptype="title_1"),
                _make_passage(
                    "Results text.", section_type="RESULTS", ptype="paragraph"
                ),
            ]
        )
        md = bioc_to_markdown(doc)
        lines = md.split("\n")
        # Check section order
        headings = [line for line in lines if line.startswith("#")]
        assert headings[0] == "# Title"
        assert "## Abstract" in headings
        assert "## Introduction" in headings
        assert "## Methods" in headings
        assert "## Results" in headings

    def test_empty_text_passages_skipped(self):
        doc = _make_document(
            [
                _make_passage("", section_type="INTRO", ptype="paragraph"),
                _make_passage("  ", section_type="INTRO", ptype="paragraph"),
                _make_passage("Real content.", section_type="INTRO", ptype="paragraph"),
            ]
        )
        md = bioc_to_markdown(doc)
        assert "Real content." in md
        # Should only have the intro heading + content, not empty lines from blank passages
        assert md.count("Introduction") == 1

    def test_table_footnote(self):
        doc = _make_document(
            [
                _make_passage("p < 0.05", section_type="TABLE", ptype="table_footnote"),
            ]
        )
        md = bioc_to_markdown(doc)
        assert "*p < 0.05*" in md

    def test_discussion_and_conclusion(self):
        doc = _make_document(
            [
                _make_passage(
                    "Discussion text.", section_type="DISCUSS", ptype="paragraph"
                ),
                _make_passage(
                    "Conclusion text.", section_type="CONCL", ptype="paragraph"
                ),
            ]
        )
        md = bioc_to_markdown(doc)
        assert "## Discussion" in md
        assert "## Conclusion" in md


class TestExtractFigureFiles:
    def test_no_figures(self):
        doc = _make_document(
            [
                _make_passage("Text.", section_type="INTRO", ptype="paragraph"),
            ]
        )
        assert extract_figure_files(doc) == []

    def test_image_figures(self):
        doc = _make_document(
            [
                _make_passage(
                    "Caption.",
                    section_type="FIG",
                    ptype="fig_caption",
                    file="fig1.jpg",
                    id="F1",
                ),
                _make_passage(
                    "Caption.",
                    section_type="FIG",
                    ptype="fig_caption",
                    file="fig2.png",
                    id="F2",
                ),
            ]
        )
        figures = extract_figure_files(doc)
        assert len(figures) == 2
        assert figures[0] == ("F1", "fig1.jpg")
        assert figures[1] == ("F2", "fig2.png")

    def test_xml_files_excluded(self):
        doc = _make_document(
            [
                _make_passage(
                    "Table.",
                    section_type="TABLE",
                    ptype="table",
                    file="T1.xml",
                    id="T1",
                ),
            ]
        )
        assert extract_figure_files(doc) == []

    def test_no_duplicates(self):
        doc = _make_document(
            [
                _make_passage(
                    "Caption.",
                    section_type="FIG",
                    ptype="fig_caption",
                    file="fig1.jpg",
                    id="F1",
                ),
                _make_passage(
                    "Alt caption.",
                    section_type="FIG",
                    ptype="fig_title_caption",
                    file="fig1.jpg",
                    id="F1",
                ),
            ]
        )
        figures = extract_figure_files(doc)
        assert len(figures) == 1


class TestExtractMetadata:
    def test_extracts_front_matter(self):
        doc = _make_document(
            [
                {
                    "infons": {
                        "section_type": "TITLE",
                        "type": "front",
                        "article-id_doi": "10.1234/test",
                        "article-id_pmc": "PMC12345",
                        "article-id_pmid": "67890",
                        "year": "2023",
                        "volume": "10",
                        "issue": "2",
                        "license": "CC BY",
                        "name_0": "surname:Smith;given-names:John",
                        "name_1": "surname:Doe;given-names:Jane",
                    },
                    "text": "Article Title",
                    "sentences": [],
                    "annotations": [],
                    "relations": [],
                },
            ]
        )
        meta = extract_metadata(doc)
        assert meta["doi"] == "10.1234/test"
        assert meta["pmcid"] == "PMC12345"
        assert meta["pmid"] == "67890"
        assert meta["year"] == "2023"
        assert meta["title"] == "Article Title"
        assert len(meta["authors"]) == 2
        assert "Smith" in meta["authors"][0]

    def test_no_front_matter(self):
        doc = _make_document(
            [
                _make_passage("Text.", section_type="INTRO", ptype="paragraph"),
            ]
        )
        assert extract_metadata(doc) == {}


class TestIsImageFile:
    def test_jpg(self):
        assert _is_image_file("fig1.jpg") is True

    def test_png(self):
        assert _is_image_file("fig1.png") is True

    def test_svg(self):
        assert _is_image_file("diagram.svg") is True

    def test_xml(self):
        assert _is_image_file("table.xml") is False

    def test_no_extension(self):
        assert _is_image_file("noextension") is False

    def test_case_insensitive(self):
        assert _is_image_file("FIG.JPG") is True


class TestFormatTableText:
    def test_simple_table(self):
        text = "Name\tAge\nAlice\t30\nBob\t25"
        result = _format_table_text(text)
        assert "| Name | Age |" in result
        assert "| --- | --- |" in result
        assert "| Alice | 30 |" in result
        assert "| Bob | 25 |" in result

    def test_single_column(self):
        text = "Item\nA\nB"
        result = _format_table_text(text)
        assert "| Item |" in result
        assert "| A |" in result

    def test_uneven_columns(self):
        text = "A\tB\tC\nX\tY"
        result = _format_table_text(text)
        # Short row should be padded
        assert result.count("|") > 0

    def test_empty_string(self):
        assert _format_table_text("") == ""
