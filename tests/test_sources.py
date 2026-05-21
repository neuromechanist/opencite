"""Tests for opencite.sources (source-name canonicalization)."""

from __future__ import annotations

from opencite.sources import canonicalize, is_source_enabled


class TestCanonicalize:
    def test_canonical_keys_pass_through(self):
        for key in ("openalex", "s2", "pubmed", "arxiv", "biorxiv", "medrxiv"):
            assert canonicalize(key) == key

    def test_known_aliases_resolve(self):
        assert canonicalize("semanticscholar") == "s2"
        assert canonicalize("semantic_scholar") == "s2"
        assert canonicalize("semantic-scholar") == "s2"
        assert canonicalize("ncbi") == "pubmed"

    def test_case_and_whitespace_insensitive(self):
        assert canonicalize("  Semantic-Scholar  ") == "s2"
        assert canonicalize("OPENALEX") == "openalex"

    def test_unknown_passes_through_lowercased(self):
        # Typos shouldn't silently match -- the caller can warn if needed.
        assert canonicalize("semanticscholr") == "semanticscholr"


class TestIsSourceEnabled:
    def test_empty_disabled_list_means_enabled(self):
        assert is_source_enabled("s2", []) is True

    def test_canonical_match_disables(self):
        assert is_source_enabled("s2", ["s2"]) is False

    def test_alias_in_disabled_matches_canonical_name(self):
        assert is_source_enabled("s2", ["semantic-scholar"]) is False
        assert is_source_enabled("semanticscholar", ["s2"]) is False

    def test_other_sources_unaffected(self):
        disabled = ["s2"]
        assert is_source_enabled("openalex", disabled) is True
        assert is_source_enabled("pubmed", disabled) is True
