"""Unit tests for CitationExplorer branches that don't need network access.

Exercises `citing_papers`, `references`, `canonical_papers`, and
`_lookup_seed` with mocked openalex/s2 clients so the previously
integration-only paths get patch coverage.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from opencite.citations import CitationExplorer
from opencite.config import Config
from opencite.models import IDSet, IDType, Paper


def _seed(doi: str = "", openalex_id: str = "", s2_id: str = "") -> Paper:
    return Paper(
        title="Seed",
        ids=IDSet(doi=doi, openalex_id=openalex_id, s2_id=s2_id),
    )


def _stub_explorer(
    seed: Paper | None = None,
    *,
    openalex_disabled: bool = False,
    s2_disabled: bool = False,
    openalex_citing: list[Paper] | None = None,
    s2_citing: list[Paper] | None = None,
    openalex_refs: list[Paper] | None = None,
    s2_refs: list[Paper] | None = None,
) -> CitationExplorer:
    disabled = [
        name
        for name, flag in (("openalex", openalex_disabled), ("s2", s2_disabled))
        if flag
    ]
    explorer = CitationExplorer(Config(disabled_sources=disabled))

    if explorer._openalex is not None:
        explorer._openalex.citing_papers = AsyncMock(
            return_value=openalex_citing or []
        )
        explorer._openalex.references = AsyncMock(return_value=openalex_refs or [])
        explorer._openalex.lookup_doi = AsyncMock(return_value=seed)
        explorer._openalex.canonical_search = AsyncMock(return_value=[])
    if explorer._s2 is not None:
        explorer._s2.citing_papers = AsyncMock(return_value=s2_citing or [])
        explorer._s2.references = AsyncMock(return_value=s2_refs or [])
        explorer._s2.lookup = AsyncMock(return_value=seed)
    return explorer


class TestCitingPapers:
    @pytest.mark.asyncio
    async def test_unknown_seed_returns_empty_result(self):
        explorer = _stub_explorer(seed=None)
        explorer._s2.lookup = AsyncMock(return_value=None)
        explorer._openalex.lookup_doi = AsyncMock(return_value=None)

        result = await explorer.citing_papers("10.1234/x")
        assert result.papers == []
        assert result.direction == "citing"
        assert result.seed_paper.title == "Unknown"

    @pytest.mark.asyncio
    async def test_gathers_from_both_when_both_ids_present(self):
        seed = _seed(doi="10.1234/x", openalex_id="W1", s2_id="S1")
        oa_paper = Paper(
            title="OpenAlex citing paper alpha", ids=IDSet(doi="10.1234/alpha")
        )
        s2_paper = Paper(
            title="Semantic Scholar citing beta", ids=IDSet(doi="10.1234/beta")
        )
        explorer = _stub_explorer(
            seed=seed,
            openalex_citing=[oa_paper],
            s2_citing=[s2_paper],
        )

        result = await explorer.citing_papers("10.1234/x")
        assert len(result.papers) == 2
        explorer._openalex.citing_papers.assert_awaited_once()
        explorer._s2.citing_papers.assert_awaited_once_with("S1", max_results=50)

    @pytest.mark.asyncio
    async def test_s2_doi_fallback_when_no_s2_id(self):
        seed = _seed(doi="10.1234/x", openalex_id="W1")  # no s2_id
        explorer = _stub_explorer(seed=seed, s2_citing=[Paper(title="x")])

        await explorer.citing_papers("10.1234/x")
        explorer._s2.citing_papers.assert_awaited_once_with(
            "DOI:10.1234/x", max_results=50
        )

    @pytest.mark.asyncio
    async def test_min_citations_filter_applied(self):
        seed = _seed(openalex_id="W1")
        lo = Paper(title="lo", ids=IDSet(doi="10.1/lo"), citation_count=5)
        hi = Paper(title="hi", ids=IDSet(doi="10.1/hi"), citation_count=500)
        explorer = _stub_explorer(seed=seed, openalex_citing=[lo, hi])

        result = await explorer.citing_papers("10.1234/x", min_citations=100)
        titles = [p.title for p in result.papers]
        assert titles == ["hi"]

    @pytest.mark.asyncio
    async def test_only_openalex_when_s2_disabled(self):
        seed = _seed(doi="10.1234/x", openalex_id="W1", s2_id="S1")
        explorer = _stub_explorer(
            seed=seed,
            s2_disabled=True,
            openalex_citing=[Paper(title="oa")],
        )

        result = await explorer.citing_papers("10.1234/x")
        assert result.seed_paper.ids.openalex_id == "W1"
        explorer._openalex.citing_papers.assert_awaited_once()
        assert explorer._s2 is None
        assert [p.title for p in result.papers] == ["oa"]


class TestReferences:
    @pytest.mark.asyncio
    async def test_unknown_seed_returns_empty(self):
        explorer = _stub_explorer(seed=None)
        explorer._s2.lookup = AsyncMock(return_value=None)
        explorer._openalex.lookup_doi = AsyncMock(return_value=None)

        result = await explorer.references("10.1234/x")
        assert result.papers == []
        assert result.direction == "references"

    @pytest.mark.asyncio
    async def test_gathers_from_both_when_both_ids_present(self):
        seed = _seed(doi="10.1234/x", openalex_id="W1", s2_id="S1")
        explorer = _stub_explorer(
            seed=seed,
            openalex_refs=[
                Paper(title="OpenAlex reference one", ids=IDSet(doi="10.1234/r1"))
            ],
            s2_refs=[
                Paper(title="S2 reference two", ids=IDSet(doi="10.1234/r2"))
            ],
        )

        result = await explorer.references("10.1234/x")
        assert len(result.papers) == 2

    @pytest.mark.asyncio
    async def test_s2_doi_fallback_for_references(self):
        seed = _seed(doi="10.1234/x", openalex_id="W1")
        explorer = _stub_explorer(seed=seed, s2_refs=[Paper(title="ref")])

        await explorer.references("10.1234/x")
        explorer._s2.references.assert_awaited_once_with(
            "DOI:10.1234/x", max_results=50
        )


class TestCanonicalPapers:
    @pytest.mark.asyncio
    async def test_delegates_to_openalex(self):
        seed = _seed(openalex_id="W1")
        explorer = _stub_explorer(seed=seed)
        explorer._openalex.canonical_search = AsyncMock(
            return_value=[Paper(title="top")]
        )

        result = await explorer.canonical_papers("topic", max_results=5)
        assert [p.title for p in result] == ["top"]
        explorer._openalex.canonical_search.assert_awaited_once()


class TestLookupSeed:
    @pytest.mark.asyncio
    async def test_doi_merges_s2_and_openalex(self):
        s2_paper = Paper(title="merged", ids=IDSet(doi="10.1234/x", s2_id="S1"))
        oa_paper = Paper(title="merged", ids=IDSet(doi="10.1234/x", openalex_id="W1"))
        explorer = _stub_explorer(seed=s2_paper)
        explorer._openalex.lookup_doi = AsyncMock(return_value=oa_paper)

        result = await explorer._lookup_seed(IDType.DOI, "10.1234/x")
        assert result is not None
        assert result.ids.s2_id == "S1"
        assert result.ids.openalex_id == "W1"

    @pytest.mark.asyncio
    async def test_doi_falls_back_to_openalex_when_s2_misses(self):
        explorer = _stub_explorer(seed=None)
        explorer._s2.lookup = AsyncMock(return_value=None)
        oa_paper = Paper(title="oa", ids=IDSet(doi="10.1234/x"))
        explorer._openalex.lookup_doi = AsyncMock(return_value=oa_paper)

        result = await explorer._lookup_seed(IDType.DOI, "10.1234/x")
        assert result is oa_paper

    @pytest.mark.asyncio
    async def test_pmid_lookup_via_s2(self):
        paper = Paper(title="x", ids=IDSet(pmid="12345"))
        explorer = _stub_explorer(seed=paper)
        explorer._s2.lookup = AsyncMock(return_value=paper)

        result = await explorer._lookup_seed(IDType.PMID, "12345")
        assert result is paper

    @pytest.mark.asyncio
    async def test_pmid_lookup_enriches_with_openalex_when_doi_known(self):
        s2_paper = Paper(title="x", ids=IDSet(pmid="12345", doi="10.1234/x"))
        oa_paper = Paper(
            title="x",
            ids=IDSet(pmid="12345", doi="10.1234/x", openalex_id="W1"),
        )
        explorer = _stub_explorer(seed=None)
        explorer._s2.lookup = AsyncMock(return_value=s2_paper)
        explorer._openalex.lookup_doi = AsyncMock(return_value=oa_paper)

        result = await explorer._lookup_seed(IDType.PMID, "12345")
        # The OpenAlex enrichment merged in the W1 id.
        assert result is not None
        assert result.ids.openalex_id == "W1"
        explorer._openalex.lookup_doi.assert_awaited_once_with("10.1234/x")

    @pytest.mark.asyncio
    async def test_arxiv_lookup_via_s2(self):
        paper = Paper(title="x", ids=IDSet(arxiv_id="2106.15928"))
        explorer = _stub_explorer(seed=paper)
        explorer._s2.lookup = AsyncMock(return_value=paper)

        result = await explorer._lookup_seed(IDType.ARXIV, "2106.15928")
        assert result is paper
        explorer._s2.lookup.assert_awaited_once_with("ARXIV:2106.15928")

    @pytest.mark.asyncio
    async def test_openalex_id_lookup(self):
        paper = Paper(title="x", ids=IDSet(openalex_id="W1"))
        explorer = _stub_explorer(seed=paper)

        result = await explorer._lookup_seed(IDType.OPENALEX, "W1")
        explorer._openalex.lookup_doi.assert_awaited_once_with("W1")
        assert result is paper

    @pytest.mark.asyncio
    async def test_s2_id_lookup(self):
        paper = Paper(title="x", ids=IDSet(s2_id="abc123"))
        explorer = _stub_explorer(seed=paper)
        explorer._s2.lookup = AsyncMock(return_value=paper)

        result = await explorer._lookup_seed(IDType.S2, "abc123")
        assert result is paper

    @pytest.mark.asyncio
    async def test_pmcid_returns_none_when_no_lookup_path(self):
        # PMCID isn't handled by either of the explorer's clients.
        explorer = _stub_explorer(seed=None)
        result = await explorer._lookup_seed(IDType.PMCID, "PMC1234")
        assert result is None

    @pytest.mark.asyncio
    async def test_lookup_when_s2_disabled_uses_openalex(self):
        oa_paper = Paper(title="oa", ids=IDSet(doi="10.1234/x"))
        explorer = _stub_explorer(seed=None, s2_disabled=True)
        explorer._openalex.lookup_doi = AsyncMock(return_value=oa_paper)

        result = await explorer._lookup_seed(IDType.DOI, "10.1234/x")
        assert result is oa_paper

    @pytest.mark.asyncio
    async def test_lookup_when_openalex_disabled_uses_s2(self):
        s2_paper = Paper(title="s2", ids=IDSet(doi="10.1234/x"))
        explorer = _stub_explorer(seed=s2_paper, openalex_disabled=True)

        result = await explorer._lookup_seed(IDType.DOI, "10.1234/x")
        assert result is s2_paper


class TestContextManagerSkipsDisabledClients:
    @pytest.mark.asyncio
    async def test_aenter_aexit_when_s2_disabled(self):
        explorer = CitationExplorer(Config(disabled_sources=["s2"]))
        # Avoid network: replace openalex enter/exit with no-op mocks.
        explorer._openalex.__aenter__ = AsyncMock(return_value=explorer._openalex)
        explorer._openalex.__aexit__ = AsyncMock(return_value=None)

        async with explorer:
            pass

        explorer._openalex.__aenter__.assert_awaited_once()
        explorer._openalex.__aexit__.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aenter_aexit_with_both_clients_enabled(self):
        explorer = CitationExplorer(Config())
        for client in (explorer._openalex, explorer._s2):
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=None)

        async with explorer:
            pass

        explorer._openalex.__aenter__.assert_awaited_once()
        explorer._s2.__aenter__.assert_awaited_once()
        explorer._openalex.__aexit__.assert_awaited_once()
        explorer._s2.__aexit__.assert_awaited_once()
