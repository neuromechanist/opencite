"""Tests for the license sidecar written next to downloaded PDFs.

The sidecar reports provenance (URL, source, license, version, oa_status,
publisher_tdm flag) so a later "is this PDF safe to commit?" check can run
without the original Paper object. opencite reports; the caller enforces.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from opencite.models import IDSet, Paper, PDFLocation
from opencite.pdf import _infer_source_from_url, _write_license_sidecar

if TYPE_CHECKING:
    from pathlib import Path


class TestInferSourceFromUrl:
    def test_elsevier(self):
        assert _infer_source_from_url("https://api.elsevier.com/x") == (
            "publisher:elsevier"
        )

    def test_wiley(self):
        assert _infer_source_from_url("https://api.wiley.com/x") == (
            "publisher:wiley"
        )

    def test_springer(self):
        assert _infer_source_from_url("https://api.springernature.com/x") == (
            "publisher:springer"
        )

    def test_arxiv(self):
        assert _infer_source_from_url("https://arxiv.org/pdf/1706.03762") == "arxiv"

    def test_pmc(self):
        assert _infer_source_from_url("https://pmc.ncbi.nlm.nih.gov/PMC42") == "pmc"

    def test_biorxiv(self):
        assert (
            _infer_source_from_url("https://www.biorxiv.org/content/foo.full.pdf")
            == "biorxiv"
        )

    def test_doi(self):
        assert _infer_source_from_url("https://doi.org/10.1234/abc") == "doi"

    def test_unknown_url(self):
        assert _infer_source_from_url("https://example.com/foo.pdf") == "unknown"


class TestSidecarWriting:
    def test_sidecar_matches_known_pdf_location(self, tmp_path: Path):
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-fake")
        loc = PDFLocation(
            url="https://example.com/paper.pdf",
            source="openalex",
            version="publishedVersion",
            is_oa=True,
            license="cc-by",
        )
        paper = Paper(
            title="A paper",
            ids=IDSet(doi="10.1234/abc"),
            pdf_locations=[loc],
            is_oa=True,
            oa_status="gold",
        )

        _write_license_sidecar(pdf_path, loc.url, paper)

        sidecar = json.loads((tmp_path / "paper.pdf.license.json").read_text())
        assert sidecar["url"] == loc.url
        assert sidecar["source"] == "openalex"
        assert sidecar["license"] == "cc-by"
        assert sidecar["version"] == "publishedVersion"
        assert sidecar["oa_status"] == "gold"
        assert sidecar["is_oa"] is True
        assert sidecar["doi"] == "10.1234/abc"
        assert sidecar["publisher_tdm"] is False
        assert sidecar["pdf_filename"] == "paper.pdf"
        assert "retrieved_at" in sidecar

    def test_sidecar_flags_publisher_tdm_when_no_metadata_match(
        self, tmp_path: Path
    ):
        # Publisher-API URLs are synthesized in _collect_urls and are not in
        # paper.pdf_locations; we fall back to URL inference and must flag
        # publisher_tdm=True so downstream scanners can detect it.
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-fake")
        paper = Paper(
            title="A paper",
            ids=IDSet(doi="10.1016/j.x"),
            oa_status="closed",
        )

        _write_license_sidecar(
            pdf_path, "https://api.elsevier.com/content/article/doi/10.1016/j.x", paper
        )

        sidecar = json.loads((tmp_path / "paper.pdf.license.json").read_text())
        assert sidecar["source"] == "publisher:elsevier"
        assert sidecar["publisher_tdm"] is True
        assert sidecar["oa_status"] == "closed"

    def test_sidecar_when_no_paper_metadata(self, tmp_path: Path):
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-fake")

        _write_license_sidecar(pdf_path, "https://arxiv.org/pdf/1706.03762", None)

        sidecar = json.loads((tmp_path / "paper.pdf.license.json").read_text())
        assert sidecar["source"] == "arxiv"
        assert sidecar["doi"] == ""
        assert sidecar["oa_status"] == ""
        assert sidecar["is_oa"] is False
        assert sidecar["publisher_tdm"] is False
