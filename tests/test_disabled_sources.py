"""Tests for `Config.disabled_sources` integration."""

from __future__ import annotations

import pytest

from opencite.citations import CitationExplorer
from opencite.config import Config
from opencite.search import SearchOrchestrator


class TestCitationExplorerDisabledSources:
    def test_default_constructs_both_clients(self):
        config = Config()
        explorer = CitationExplorer(config)
        assert explorer._openalex is not None
        assert explorer._s2 is not None

    def test_disabling_s2_skips_s2_client(self):
        config = Config(disabled_sources=["s2"])
        explorer = CitationExplorer(config)
        assert explorer._openalex is not None
        assert explorer._s2 is None

    def test_alias_disables_s2(self):
        config = Config(disabled_sources=["semantic-scholar"])
        explorer = CitationExplorer(config)
        assert explorer._s2 is None

    def test_disabling_openalex_skips_openalex_client(self):
        config = Config(disabled_sources=["openalex"])
        explorer = CitationExplorer(config)
        assert explorer._openalex is None
        assert explorer._s2 is not None

    def test_disabling_both_raises(self):
        config = Config(disabled_sources=["openalex", "s2"])
        with pytest.raises(ValueError, match="at least one"):
            CitationExplorer(config)

    @pytest.mark.asyncio
    async def test_canonical_papers_raises_when_openalex_disabled(self):
        config = Config(disabled_sources=["openalex"])
        explorer = CitationExplorer(config)
        with pytest.raises(RuntimeError, match="openalex"):
            await explorer.canonical_papers("anything")


class TestSearchOrchestratorRespectsDisabledSources:
    def test_disabled_sources_round_trips_through_orchestrator(self):
        config = Config(disabled_sources=["figshare", "core"])
        orchestrator = SearchOrchestrator(config)
        assert "figshare" in orchestrator.config.disabled_sources
        assert "core" in orchestrator.config.disabled_sources

    @pytest.mark.asyncio
    async def test_disabled_sources_skip_real_client_dispatch(self):
        """End-to-end: a disabled source's `search` method must not be awaited."""
        from unittest.mock import AsyncMock

        orchestrator = SearchOrchestrator(
            Config(disabled_sources=["s2", "figshare", "core"])
        )
        for attr in (
            "_openalex",
            "_s2",
            "_pubmed",
            "_arxiv",
            "_biorxiv",
            "_medrxiv",
            "_osf",
            "_zenodo",
            "_figshare",
            "_crossref",
            "_core",
        ):
            getattr(orchestrator, attr).search = AsyncMock(return_value=[])

        await orchestrator.search("query")

        orchestrator._s2.search.assert_not_called()
        orchestrator._figshare.search.assert_not_called()
        orchestrator._core.search.assert_not_called()
        orchestrator._openalex.search.assert_awaited_once()
        orchestrator._arxiv.search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disabled_overrides_per_call_sources_arg(self):
        """Even an explicit `sources=` argument cannot re-enable a disabled source."""
        from unittest.mock import AsyncMock

        orchestrator = SearchOrchestrator(Config(disabled_sources=["s2"]))
        orchestrator._s2.search = AsyncMock(return_value=[])
        orchestrator._openalex.search = AsyncMock(return_value=[])

        await orchestrator.search("query", sources=("openalex", "s2"))

        orchestrator._s2.search.assert_not_called()
        orchestrator._openalex.search.assert_awaited_once()


class TestConfigDisabledSourcesParsing:
    def test_default_is_empty(self):
        assert Config().disabled_sources == []

    def test_env_var_csv_is_parsed_into_list(self, monkeypatch):
        monkeypatch.setenv("OPENCITE_DISABLED_SOURCES", "s2, figshare ,core")
        config = Config.from_env()
        assert config.disabled_sources == ["s2", "figshare", "core"]

    def test_env_var_empty_string_yields_empty_list(self, monkeypatch):
        monkeypatch.setenv("OPENCITE_DISABLED_SOURCES", "")
        config = Config.from_env()
        # An explicitly empty value should still parse cleanly.
        assert config.disabled_sources == []
