"""Tests for opencite.batch."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from opencite.batch import (
    BatchResult,
    batch_download,
    prepare_output_dirs,
    read_ids_from_file,
    read_ids_from_json,
    read_ids_from_stdin,
)
from opencite.config import Config


class TestBatchResult:
    def test_to_dict(self):
        result = BatchResult(
            total=3,
            downloaded=2,
            converted=1,
            failed=[("10.1234/test", "not found")],
            conversion_failed=[("10.1234/other", "converter error")],
        )
        d = result.to_dict()
        assert d["total"] == 3
        assert d["downloaded"] == 2
        assert d["converted"] == 1
        assert len(d["failed"]) == 1
        assert d["failed"][0]["id"] == "10.1234/test"
        assert d["failed"][0]["reason"] == "not found"
        assert len(d["conversion_failed"]) == 1
        assert d["conversion_failed"][0]["id"] == "10.1234/other"
        assert d["conversion_failed"][0]["reason"] == "converter error"

    def test_empty_result(self):
        result = BatchResult()
        d = result.to_dict()
        assert d["total"] == 0
        assert d["downloaded"] == 0
        assert d["failed"] == []
        assert d["conversion_failed"] == []


class TestReadIdsFromFile:
    def test_basic(self, tmp_path):
        f = tmp_path / "dois.txt"
        f.write_text("10.1234/test1\n10.5678/test2\n")
        ids = read_ids_from_file(str(f))
        assert ids == ["10.1234/test1", "10.5678/test2"]

    def test_skips_comments_and_blanks(self, tmp_path):
        f = tmp_path / "dois.txt"
        f.write_text("# Comment\n\n10.1234/test\n# Another\n")
        ids = read_ids_from_file(str(f))
        assert ids == ["10.1234/test"]

    def test_strips_whitespace(self, tmp_path):
        f = tmp_path / "dois.txt"
        f.write_text("  10.1234/test  \n")
        ids = read_ids_from_file(str(f))
        assert ids == ["10.1234/test"]

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            read_ids_from_file("/nonexistent/dois.txt")


class TestReadIdsFromJson:
    def test_array_of_strings(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text(json.dumps(["10.1234/a", "10.1234/b"]))
        ids = read_ids_from_json(str(f))
        assert ids == ["10.1234/a", "10.1234/b"]

    def test_array_of_objects_with_doi(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text(json.dumps([{"doi": "10.1234/a"}, {"doi": "10.1234/b"}]))
        ids = read_ids_from_json(str(f))
        assert ids == ["10.1234/a", "10.1234/b"]

    def test_papers_format(self, tmp_path):
        f = tmp_path / "data.json"
        data = {"papers": [{"doi": "10.1234/a"}, {"doi": "10.1234/b"}]}
        f.write_text(json.dumps(data))
        ids = read_ids_from_json(str(f))
        assert ids == ["10.1234/a", "10.1234/b"]

    def test_invalid_format(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text(json.dumps({"something": "else"}))
        with pytest.raises(ValueError, match="Unrecognized JSON format"):
            read_ids_from_json(str(f))

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            read_ids_from_json("/nonexistent/data.json")

    def test_invalid_json(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text("not valid json {{{")
        with pytest.raises(ValueError, match="Invalid JSON"):
            read_ids_from_json(str(f))

    def test_array_of_objects_with_DOI_key(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text(json.dumps([{"DOI": "10.1234/a"}]))
        ids = read_ids_from_json(str(f))
        assert ids == ["10.1234/a"]

    def test_array_of_objects_with_id_key(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text(json.dumps([{"id": "10.1234/a"}]))
        ids = read_ids_from_json(str(f))
        assert ids == ["10.1234/a"]

    def test_mixed_strings_and_objects(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text(json.dumps(["10.1234/a", {"doi": "10.1234/b"}]))
        ids = read_ids_from_json(str(f))
        assert ids == ["10.1234/a", "10.1234/b"]

    def test_empty_array(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text(json.dumps([]))
        ids = read_ids_from_json(str(f))
        assert ids == []

    def test_papers_format_with_id_key(self, tmp_path):
        f = tmp_path / "data.json"
        data = {"papers": [{"id": "10.1234/a"}, {"doi": "10.1234/b"}]}
        f.write_text(json.dumps(data))
        ids = read_ids_from_json(str(f))
        assert ids == ["10.1234/a", "10.1234/b"]

    def test_objects_without_doi_skipped(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text(json.dumps([{"title": "No DOI"}, {"doi": "10.1234/b"}]))
        ids = read_ids_from_json(str(f))
        assert ids == ["10.1234/b"]


class TestReadIdsFromStdin:
    def test_basic(self, monkeypatch):
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("10.1234/a\n10.5678/b\n"))
        ids = read_ids_from_stdin()
        assert ids == ["10.1234/a", "10.5678/b"]

    def test_skips_comments_and_blanks(self, monkeypatch):
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("# comment\n\n10.1234/a\n"))
        ids = read_ids_from_stdin()
        assert ids == ["10.1234/a"]

    def test_strips_whitespace(self, monkeypatch):
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("  10.1234/a  \n"))
        ids = read_ids_from_stdin()
        assert ids == ["10.1234/a"]

    def test_empty_stdin(self, monkeypatch):
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        ids = read_ids_from_stdin()
        assert ids == []


class TestPrepareOutputDirs:
    def test_convert_true_creates_subdirs(self, tmp_path):
        pdf_dir, md_dir, img_dir = prepare_output_dirs(str(tmp_path), convert=True)
        assert pdf_dir.is_dir()
        assert pdf_dir.name == "pdf"
        assert md_dir is not None
        assert md_dir.is_dir()
        assert md_dir.name == "markdown"
        assert img_dir is not None
        assert img_dir.is_dir()
        assert img_dir.name == "img"
        assert img_dir.parent == md_dir

    def test_convert_false_flat_dir(self, tmp_path):
        pdf_dir, md_dir, img_dir = prepare_output_dirs(str(tmp_path), convert=False)
        assert pdf_dir == tmp_path
        assert pdf_dir.is_dir()
        assert md_dir is None
        assert img_dir is None
        assert not (tmp_path / "pdf").exists()
        assert not (tmp_path / "markdown").exists()

    def test_convert_true_nested_output_dir(self, tmp_path):
        nested = tmp_path / "deep" / "nested" / "papers"
        pdf_dir, md_dir, img_dir = prepare_output_dirs(str(nested), convert=True)
        assert pdf_dir.is_dir()
        assert pdf_dir == nested / "pdf"
        assert md_dir is not None
        assert md_dir == nested / "markdown"
        assert img_dir is not None
        assert img_dir == nested / "markdown" / "img"

    def test_convert_true_idempotent(self, tmp_path):
        pdf1, md1, img1 = prepare_output_dirs(str(tmp_path), convert=True)
        pdf2, md2, img2 = prepare_output_dirs(str(tmp_path), convert=True)
        assert pdf1 == pdf2
        assert md1 == md2
        assert img1 == img2


class TestBatchPreprintIntegration:
    """`batch_download` should try preprint HTML before PDF when converting.

    Stub the retrievers and the PDFRetriever lifecycle so the wiring is
    exercised without hitting the network or the real PDF pipeline.
    """

    @pytest.mark.asyncio
    async def test_preprint_html_path_used_when_available(self, tmp_path, monkeypatch):
        pdf_instance = MagicMock()
        pdf_instance.__aenter__ = AsyncMock(return_value=pdf_instance)
        pdf_instance.__aexit__ = AsyncMock(return_value=None)
        pdf_instance.download = AsyncMock()
        import opencite.batch as batch_mod

        monkeypatch.setattr(batch_mod, "PDFRetriever", lambda _c: pdf_instance)

        ft_instance = MagicMock()
        ft_instance.__aenter__ = AsyncMock(return_value=ft_instance)
        ft_instance.__aexit__ = AsyncMock(return_value=None)
        ft_instance.retrieve = AsyncMock(return_value=None)
        import opencite.fulltext as ft_mod

        monkeypatch.setattr(ft_mod, "FullTextRetriever", lambda _c: ft_instance)

        pre_instance = MagicMock()
        pre_instance.__aenter__ = AsyncMock(return_value=pre_instance)
        pre_instance.__aexit__ = AsyncMock(return_value=None)
        out_md = tmp_path / "papers" / "markdown" / "preprint.md"
        pre_instance.retrieve_for_identifier = AsyncMock(return_value=out_md)
        import opencite.preprint_fulltext as pre_mod

        monkeypatch.setattr(
            pre_mod, "PreprintFullTextRetriever", lambda _c: pre_instance
        )

        result = await batch_download(
            ids=["10.48550/arXiv.1706.03762"],
            config=Config(),
            output_dir=str(tmp_path / "papers"),
            convert=True,
        )

        assert result.fulltext_retrieved == 1
        assert result.converted == 1
        pdf_instance.download.assert_not_called()
        pre_instance.retrieve_for_identifier.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_preprint_html_skips_preprint_tier(self, tmp_path, monkeypatch):
        """`prefer_preprint_html=False` must not even instantiate the retriever."""
        pdf_instance = MagicMock()
        pdf_instance.__aenter__ = AsyncMock(return_value=pdf_instance)
        pdf_instance.__aexit__ = AsyncMock(return_value=None)
        pdf_instance.download = AsyncMock(return_value=None)
        import opencite.batch as batch_mod

        monkeypatch.setattr(batch_mod, "PDFRetriever", lambda _c: pdf_instance)

        ft_instance = MagicMock()
        ft_instance.__aenter__ = AsyncMock(return_value=ft_instance)
        ft_instance.__aexit__ = AsyncMock(return_value=None)
        ft_instance.retrieve = AsyncMock(return_value=None)
        import opencite.fulltext as ft_mod

        monkeypatch.setattr(ft_mod, "FullTextRetriever", lambda _c: ft_instance)

        pre_called = MagicMock()
        import opencite.preprint_fulltext as pre_mod

        monkeypatch.setattr(pre_mod, "PreprintFullTextRetriever", pre_called)

        await batch_download(
            ids=["10.48550/arXiv.1706.03762"],
            config=Config(),
            output_dir=str(tmp_path / "papers"),
            convert=True,
            prefer_preprint_html=False,
        )

        pre_called.assert_not_called()
        pdf_instance.download.assert_called_once()
