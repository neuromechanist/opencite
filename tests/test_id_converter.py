"""Tests for opencite.clients.id_converter."""

from __future__ import annotations

from opencite.clients.id_converter import _detect_id_type, _group_ids_by_type


class TestDetectIdType:
    def test_pure_digits_is_pmid(self):
        assert _detect_id_type("12345678") == "pmid"

    def test_pmc_prefix_uppercase(self):
        assert _detect_id_type("PMC1234567") == "pmcid"

    def test_pmc_prefix_lowercase(self):
        assert _detect_id_type("pmc1234567") == "pmcid"

    def test_doi_prefix(self):
        assert _detect_id_type("10.1038/nature12345") == "doi"

    def test_doi_without_slash(self):
        # Anything that's not pure digits or PMC prefix falls through to DOI
        assert _detect_id_type("some_other_id") == "doi"

    def test_whitespace_stripped(self):
        assert _detect_id_type("  12345678  ") == "pmid"
        assert _detect_id_type("  PMC123  ") == "pmcid"


class TestGroupIdsByType:
    def test_groups_correctly(self):
        ids = ["12345", "PMC111", "10.1234/test", "67890", "PMC222"]
        groups = _group_ids_by_type(ids)
        assert set(groups["pmid"]) == {"12345", "67890"}
        assert set(groups["pmcid"]) == {"PMC111", "PMC222"}
        assert groups["doi"] == ["10.1234/test"]

    def test_empty_list(self):
        groups = _group_ids_by_type([])
        assert groups == {}

    def test_all_same_type(self):
        ids = ["12345", "67890", "11111"]
        groups = _group_ids_by_type(ids)
        assert len(groups) == 1
        assert "pmid" in groups
        assert len(groups["pmid"]) == 3


# NOTE: IDConverterClient integration tests omitted because pmc.ncbi.nlm.nih.gov
# blocks httpx requests (bot detection via TLS fingerprinting). The API works
# with curl but not from Python HTTP clients. If this is fixed upstream,
# integration tests should be added here.
