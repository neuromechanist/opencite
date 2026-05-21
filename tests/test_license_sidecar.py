"""Tests for the license sidecar written next to downloaded PDFs.

The sidecar reports provenance (URL, source, license, version, oa_status,
publisher_tdm flag) so a later "is this PDF safe to commit?" check can run
without the original Paper object. opencite reports; the caller enforces.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

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

        _write_license_sidecar(pdf_path, loc.url, loc.url, paper)

        sidecar = json.loads((tmp_path / "paper.pdf.license.json").read_text())
        assert sidecar["url"] == loc.url
        assert sidecar["final_url"] == loc.url
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
            is_oa=True,
            oa_status="gold",
        )

        publisher_url = (
            "https://api.elsevier.com/content/article/doi/10.1016/j.x"
        )
        _write_license_sidecar(pdf_path, publisher_url, publisher_url, paper)

        sidecar = json.loads((tmp_path / "paper.pdf.license.json").read_text())
        assert sidecar["source"] == "publisher:elsevier"
        assert sidecar["publisher_tdm"] is True
        assert sidecar["oa_status"] == "gold"
        # bytes_is_oa must be False even when paper.is_oa is True: the
        # publisher-TDM bytes carry redistribution restrictions regardless
        # of whether the paper has an OA copy elsewhere.
        assert sidecar["is_oa"] is False

    def test_sidecar_when_no_paper_metadata(self, tmp_path: Path):
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-fake")

        _write_license_sidecar(
            pdf_path,
            "https://arxiv.org/pdf/1706.03762",
            "https://arxiv.org/pdf/1706.03762",
            None,
        )

        sidecar = json.loads((tmp_path / "paper.pdf.license.json").read_text())
        assert sidecar["source"] == "arxiv"
        assert sidecar["doi"] == ""
        assert sidecar["oa_status"] == ""
        assert sidecar["is_oa"] is False
        assert sidecar["publisher_tdm"] is False

    def test_final_url_overrides_inference_when_doi_redirects_to_publisher(
        self, tmp_path: Path
    ):
        """doi.org -> publisher TDM redirect must classify as publisher.

        Without `final_url`, the sidecar would record source='doi' and
        publisher_tdm=False, defeating the redistribution-risk signal.
        """
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-fake")
        paper = Paper(
            title="A paper",
            ids=IDSet(doi="10.1016/j.x"),
            is_oa=True,
            oa_status="gold",
        )

        _write_license_sidecar(
            pdf_path,
            url="https://doi.org/10.1016/j.x",
            final_url="https://api.elsevier.com/content/article/doi/10.1016/j.x",
            paper=paper,
        )

        sidecar = json.loads((tmp_path / "paper.pdf.license.json").read_text())
        assert sidecar["url"] == "https://doi.org/10.1016/j.x"
        assert sidecar["final_url"].startswith("https://api.elsevier.com")
        assert sidecar["source"] == "publisher:elsevier"
        assert sidecar["publisher_tdm"] is True
        assert sidecar["is_oa"] is False

    def test_write_failure_is_swallowed(self, tmp_path: Path, monkeypatch):
        """Filesystem failures must not raise -- PDF is the primary artifact."""
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-fake")

        # Monkeypatch Path.write_text to simulate a read-only filesystem.
        from pathlib import Path as _Path

        def boom(*_args, **_kwargs):
            raise OSError("read-only filesystem")

        monkeypatch.setattr(_Path, "write_text", boom)
        # Must not raise; absence of exception is the contract.
        _write_license_sidecar(
            pdf_path, "https://arxiv.org/pdf/x", "https://arxiv.org/pdf/x", None
        )

    def test_serialization_failure_is_swallowed(
        self, tmp_path: Path, monkeypatch
    ):
        """json.dumps failures (TypeError/ValueError) also must not raise."""
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-fake")

        import opencite.pdf as pdf_mod

        def bad_dumps(*_args, **_kwargs):
            raise TypeError("not JSON serializable")

        monkeypatch.setattr(pdf_mod.json, "dumps", bad_dumps)
        _write_license_sidecar(
            pdf_path, "https://arxiv.org/pdf/x", "https://arxiv.org/pdf/x", None
        )


class TestDownloadWritesSidecar:
    """Verify PDFRetriever.download wires the sidecar into the success branch."""

    @pytest.mark.asyncio
    async def test_download_writes_sidecar_next_to_pdf(
        self, tmp_path: Path, monkeypatch
    ):
        from unittest.mock import AsyncMock

        from opencite.config import Config
        from opencite.pdf import PDFRetriever

        retriever = PDFRetriever(Config())
        pdf_url = "https://arxiv.org/pdf/1706.03762"
        paper = Paper(
            title="Attention",
            ids=IDSet(doi="10.48550/arXiv.1706.03762", arxiv_id="1706.03762"),
            pdf_locations=[
                PDFLocation(url=pdf_url, source="arxiv", is_oa=True)
            ],
            is_oa=True,
            oa_status="green",
        )

        async def fake_try_download(_self, url, dest, _failures):
            dest.write_bytes(b"%PDF-fake")
            return dest, url

        monkeypatch.setattr(PDFRetriever, "_try_download", fake_try_download)
        # _collect_urls would try Unpaywall; bypass with a controlled list.
        retriever._collect_urls = AsyncMock(return_value=[pdf_url])

        result = await retriever.download(
            "10.48550/arXiv.1706.03762",
            output_dir=str(tmp_path),
            paper=paper,
            filename="attention.pdf",
        )

        assert result is not None
        assert result.exists()
        sidecar_path = result.with_suffix(result.suffix + ".license.json")
        assert sidecar_path.exists()
        sidecar = json.loads(sidecar_path.read_text())
        assert sidecar["url"] == pdf_url
        assert sidecar["source"] == "arxiv"
        assert sidecar["oa_status"] == "green"
