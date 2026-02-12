"""Tests for opencite.batch."""

from __future__ import annotations

import json
import tempfile

import pytest

from opencite.batch import (
    BatchResult,
    read_ids_from_file,
    read_ids_from_json,
)


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
    def test_basic(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("10.1234/test1\n10.5678/test2\n")
            f.flush()
            ids = read_ids_from_file(f.name)
        assert ids == ["10.1234/test1", "10.5678/test2"]

    def test_skips_comments_and_blanks(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# Comment\n\n10.1234/test\n# Another\n")
            f.flush()
            ids = read_ids_from_file(f.name)
        assert ids == ["10.1234/test"]

    def test_strips_whitespace(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("  10.1234/test  \n")
            f.flush()
            ids = read_ids_from_file(f.name)
        assert ids == ["10.1234/test"]

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            read_ids_from_file("/nonexistent/dois.txt")


class TestReadIdsFromJson:
    def test_array_of_strings(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(["10.1234/a", "10.1234/b"], f)
            f.flush()
            ids = read_ids_from_json(f.name)
        assert ids == ["10.1234/a", "10.1234/b"]

    def test_array_of_objects_with_doi(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([{"doi": "10.1234/a"}, {"doi": "10.1234/b"}], f)
            f.flush()
            ids = read_ids_from_json(f.name)
        assert ids == ["10.1234/a", "10.1234/b"]

    def test_papers_format(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {"papers": [{"doi": "10.1234/a"}, {"doi": "10.1234/b"}]}
            json.dump(data, f)
            f.flush()
            ids = read_ids_from_json(f.name)
        assert ids == ["10.1234/a", "10.1234/b"]

    def test_invalid_format(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"something": "else"}, f)
            f.flush()
            with pytest.raises(ValueError, match="Unrecognized JSON format"):
                read_ids_from_json(f.name)

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            read_ids_from_json("/nonexistent/data.json")

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {{{")
            f.flush()
            with pytest.raises(ValueError, match="Invalid JSON"):
                read_ids_from_json(f.name)
