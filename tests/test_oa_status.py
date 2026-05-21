"""Tests for `Paper.oa_status` reporting (model + formatters + merge)."""

from __future__ import annotations

import json

from opencite.dedup import merge_papers
from opencite.formatters.csv_fmt import CsvFormatter
from opencite.formatters.json_fmt import JsonFormatter
from opencite.models import IDSet, Paper, PDFLocation


def _paper(**overrides) -> Paper:
    defaults = {
        "title": "T",
        "ids": IDSet(doi="10.1/x"),
    }
    defaults.update(overrides)
    return Paper(**defaults)


class TestPaperOaStatusField:
    def test_default_is_empty_string(self):
        assert _paper().oa_status == ""

    def test_round_trips_through_constructor(self):
        for status in ("gold", "hybrid", "green", "bronze", "closed", "diamond"):
            assert _paper(oa_status=status).oa_status == status


class TestMergePreservesOaStatus:
    def test_existing_status_wins_when_present(self):
        a = _paper(oa_status="gold")
        b = _paper(oa_status="hybrid")
        assert merge_papers(a, b).oa_status == "gold"

    def test_takes_from_new_when_existing_empty(self):
        a = _paper(oa_status="")
        b = _paper(oa_status="bronze")
        assert merge_papers(a, b).oa_status == "bronze"


class TestJsonFormatterSurfacesOaStatus:
    def test_oa_status_in_top_level_output(self):
        paper = _paper(oa_status="bronze")
        text = JsonFormatter().format_single(paper)
        assert json.loads(text)["oa_status"] == "bronze"

    def test_pdf_location_license_and_version_in_verbose(self):
        loc = PDFLocation(
            url="https://example.com/x.pdf",
            source="openalex",
            version="publishedVersion",
            license="cc-by",
            is_oa=True,
        )
        paper = _paper(pdf_locations=[loc])
        out = json.loads(JsonFormatter().format_single(paper, verbose=True))
        location = out["pdf_locations"][0]
        assert location["license"] == "cc-by"
        assert location["version"] == "publishedVersion"
        assert location["is_oa"] is True


class TestCsvFormatterSurfacesOaStatus:
    def test_oa_status_column_present(self):
        paper = _paper(oa_status="green")
        out = CsvFormatter().format_single(paper)
        # First row is header, second is the data row.
        header, row = out.splitlines()
        assert "oa_status" in header.split(",")
        idx = header.split(",").index("oa_status")
        assert row.split(",")[idx] == "green"
