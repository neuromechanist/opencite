"""Tests for the PreprintFullTextRetriever dispatch + writer.

The retriever picks the right `PreprintClient` for a paper by data_sources
attribution first, then DOI prefix. These tests stub the clients so the
dispatch logic is exercised without hitting any network.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from opencite.clients.preprint_base import FulltextRoute, PreprintClient
from opencite.config import Config
from opencite.models import IDSet, Paper
from opencite.preprint_fulltext import PreprintFullTextRetriever


class _FakePreprintClient(PreprintClient):
    """Minimal in-memory preprint client used to validate dispatch.

    Records every call to ``fetch_fulltext`` so tests can assert which client
    served a given paper. Returns a deterministic markdown body keyed on the
    client name and the paper DOI / arXiv ID.
    """

    def __init__(self, config: Config, name_value: str) -> None:
        # Construct via a public-facing arXiv-style base URL; we never hit
        # the network in these tests, so the URL is purely cosmetic.
        super().__init__(
            config=config,
            base_url="https://example.invalid",
            rate_limit=1000.0,
            burst=10,
        )
        # Override the ClassVar at instance level for each fake instance.
        self.name = name_value  # type: ignore[misc]
        self.fetch_calls: list[Paper] = []

    def _default_headers(self) -> dict[str, str]:
        return {}

    async def search(self, query: str, max_results: int = 20, **kwargs):  # noqa: ARG002
        return []

    async def lookup_doi(self, doi: str):  # noqa: ARG002
        return None

    def fulltext_route(self, paper: Paper) -> FulltextRoute:  # noqa: ARG002
        return FulltextRoute.HTML

    async def fetch_fulltext(self, paper: Paper) -> str | None:
        self.fetch_calls.append(paper)
        ident = paper.doi or paper.ids.arxiv_id or "unknown"
        return f"# {self.name}: {ident}\n\nFake markdown."


# Subclasses with proper ClassVar names so __init_subclass__ accepts them.
class FakeArxiv(_FakePreprintClient):
    name: ClassVar[str] = "arxiv"

    def __init__(self, config: Config) -> None:
        super().__init__(config, "arxiv")


class FakeBiorxiv(_FakePreprintClient):
    name: ClassVar[str] = "biorxiv"

    def __init__(self, config: Config) -> None:
        super().__init__(config, "biorxiv")


class FakeMedrxiv(_FakePreprintClient):
    name: ClassVar[str] = "medrxiv"

    def __init__(self, config: Config) -> None:
        super().__init__(config, "medrxiv")


@pytest.fixture
def _config() -> Config:
    return Config()


@pytest.fixture
async def retriever(_config: Config):
    fakes = [FakeArxiv(_config), FakeBiorxiv(_config), FakeMedrxiv(_config)]
    async with PreprintFullTextRetriever(_config, clients=fakes) as r:
        yield r, fakes


class TestDispatch:
    @pytest.mark.asyncio
    async def test_data_source_attribution_picks_client(self, retriever, tmp_path):
        r, fakes = retriever
        paper = Paper(
            title="Some preprint",
            ids=IDSet(doi="10.1234/foo"),  # not a known prefix
            data_sources={"medrxiv"},
        )
        path = await r.retrieve(paper, output_dir=tmp_path, identifier="10.1234/foo")
        assert path is not None
        # FakeMedrxiv (index 2) was called; others were not.
        assert len(fakes[2].fetch_calls) == 1
        assert fakes[0].fetch_calls == []
        assert fakes[1].fetch_calls == []

    @pytest.mark.asyncio
    async def test_arxiv_doi_prefix_routes_to_arxiv(self, retriever, tmp_path):
        r, fakes = retriever
        paper = Paper(
            title="ArXiv paper",
            ids=IDSet(doi="10.48550/arXiv.1706.03762"),
        )
        path = await r.retrieve(paper, output_dir=tmp_path, identifier="arxiv-doi")
        assert path is not None
        assert len(fakes[0].fetch_calls) == 1
        assert fakes[1].fetch_calls == []

    @pytest.mark.asyncio
    async def test_biorxiv_prefix_routes_to_biorxiv(self, retriever, tmp_path):
        r, fakes = retriever
        paper = Paper(
            title="bioRxiv paper",
            ids=IDSet(doi="10.1101/2024.09.12.612645"),
        )
        path = await r.retrieve(paper, output_dir=tmp_path, identifier="biorxiv-doi")
        assert path is not None
        # bioRxiv preferred over medRxiv when DOI prefix alone is the signal.
        assert len(fakes[1].fetch_calls) == 1
        assert fakes[2].fetch_calls == []

    @pytest.mark.asyncio
    async def test_unknown_doi_returns_none(self, retriever, tmp_path):
        r, _ = retriever
        paper = Paper(
            title="Random paper",
            ids=IDSet(doi="10.1038/nature12373"),
        )
        path = await r.retrieve(paper, output_dir=tmp_path, identifier="random")
        assert path is None

    @pytest.mark.asyncio
    async def test_route_none_returns_none(self, _config: Config, tmp_path):
        """A client whose route is NONE must not be invoked for fetch."""

        class FakeNoneRoute(_FakePreprintClient):
            name: ClassVar[str] = "biorxiv"

            def __init__(self, config: Config) -> None:
                super().__init__(config, "biorxiv")

            def fulltext_route(self, paper: Paper) -> FulltextRoute:  # noqa: ARG002
                return FulltextRoute.NONE

        fake = FakeNoneRoute(_config)
        async with PreprintFullTextRetriever(_config, clients=[fake]) as r:
            paper = Paper(
                title="bioRxiv paper",
                ids=IDSet(doi="10.1101/2024.09.12.612645"),
            )
            path = await r.retrieve(paper, output_dir=tmp_path, identifier="x")
        assert path is None
        # fetch_fulltext was never called because the route was NONE.
        assert fake.fetch_calls == []


class TestWrite:
    @pytest.mark.asyncio
    async def test_writes_markdown_to_output_dir(self, retriever, tmp_path):
        r, _ = retriever
        paper = Paper(
            title="Attention Is All You Need",
            ids=IDSet(doi="10.48550/arXiv.1706.03762"),
        )
        path = await r.retrieve(
            paper,
            output_dir=tmp_path,
            identifier="attention",
        )
        assert path is not None
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "arxiv: 10.48550/arXiv.1706.03762" in content
