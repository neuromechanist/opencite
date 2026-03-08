"""Tests for the PMC BioC client."""

from __future__ import annotations

from opencite.clients.pmc import PMCClient


class TestNormalizePmcid:
    def test_with_prefix(self):
        assert PMCClient._normalize_pmcid("PMC5334499") == "PMC5334499"

    def test_without_prefix(self):
        assert PMCClient._normalize_pmcid("5334499") == "PMC5334499"

    def test_lowercase_prefix(self):
        assert PMCClient._normalize_pmcid("pmc5334499") == "PMC5334499"

    def test_mixed_case_prefix(self):
        assert PMCClient._normalize_pmcid("Pmc5334499") == "PMC5334499"

    def test_with_whitespace(self):
        assert PMCClient._normalize_pmcid("  PMC5334499  ") == "PMC5334499"


class TestDefaultHeaders:
    def _make_client(self, **config_kwargs):
        from opencite.config import Config

        client = PMCClient.__new__(PMCClient)
        client.config = Config(**config_kwargs)
        return client

    def test_headers_with_no_api_key(self):
        client = self._make_client()
        headers = client._default_headers()
        assert headers["Accept"] == "application/json"
        assert "api_key" not in headers

    def test_headers_with_pubmed_api_key(self):
        client = self._make_client(pubmed_api_key="test-key")
        headers = client._default_headers()
        assert headers["api_key"] == "test-key"
