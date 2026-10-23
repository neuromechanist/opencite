"""Tests for the per-process shared rate limiter on BaseClient.

The intent is to verify that subclasses opting in via `shared_limiter_key`
all see the same RateLimiter instance, so concurrent callers can't blow
through a tight per-source budget (e.g. Semantic Scholar's ~1 req/sec).
"""

from __future__ import annotations

import asyncio
import time
from typing import ClassVar

import pytest

from opencite.clients.arxiv import ArXivClient
from opencite.clients.base import BaseClient, RateLimiter
from opencite.clients.biorxiv import BioRxivClient
from opencite.clients.crossref import CrossRefClient
from opencite.clients.id_converter import IDConverterClient
from opencite.clients.medrxiv import MedRxivClient
from opencite.clients.openalex import OpenAlexClient
from opencite.clients.pubmed import PubMedClient
from opencite.clients.semantic_scholar import SemanticScholarClient
from opencite.config import Config


class _UnsharedClient(BaseClient):
    """Sentinel: a client class with no shared_limiter_key."""

    def _default_headers(self) -> dict[str, str]:
        return {}


class _SharedClient(BaseClient):
    """Sentinel: a client class that opts in to a shared limiter."""

    shared_limiter_key: ClassVar[str | None] = "shared-test"

    def _default_headers(self) -> dict[str, str]:
        return {}


class TestSharedLimiterOptIn:
    def test_unshared_clients_get_independent_limiters(self):
        config = Config()
        a = _UnsharedClient(config, base_url="https://x", rate_limit=10.0)
        b = _UnsharedClient(config, base_url="https://x", rate_limit=10.0)
        assert a.rate_limiter is not b.rate_limiter

    def test_shared_clients_get_the_same_limiter(self):
        config = Config()
        a = _SharedClient(config, base_url="https://a", rate_limit=10.0)
        b = _SharedClient(config, base_url="https://b", rate_limit=10.0)
        assert a.rate_limiter is b.rate_limiter

    def test_reset_clears_registry(self):
        config = Config()
        a = _SharedClient(config, base_url="https://a", rate_limit=10.0)
        BaseClient.reset_shared_limiters()
        b = _SharedClient(config, base_url="https://a", rate_limit=10.0)
        assert a.rate_limiter is not b.rate_limiter


class TestRealClientsShareBudgets:
    def test_s2_clients_share_one_limiter(self):
        config = Config()
        a = SemanticScholarClient(config)
        b = SemanticScholarClient(config)
        assert a.rate_limiter is b.rate_limiter

    def test_openalex_clients_share_one_limiter(self):
        config = Config()
        a = OpenAlexClient(config)
        b = OpenAlexClient(config)
        assert a.rate_limiter is b.rate_limiter

    def test_pubmed_and_id_converter_share_ncbi_budget(self):
        config = Config()
        a = PubMedClient(config)
        b = IDConverterClient(config)
        # Both NCBI eutils endpoints share one budget so the per-key
        # ~10 req/sec ceiling isn't doubled.
        assert a.rate_limiter is b.rate_limiter

    def test_s2_and_openalex_have_separate_budgets(self):
        config = Config()
        s2 = SemanticScholarClient(config)
        oa = OpenAlexClient(config)
        assert s2.rate_limiter is not oa.rate_limiter


class TestRateLimiterAcrossLoops:
    """Acquiring from a freshly-created event loop must not raise."""

    def test_acquire_in_two_sequential_loops(self):
        rl = RateLimiter(rate=100.0, burst=2)
        # First loop drains a token, second loop reuses the limiter.
        asyncio.run(rl.acquire())
        asyncio.run(rl.acquire())


class TestSharedLimiterSerializesRate:
    """Two clients sharing a 1 req/s limiter must observe the limit jointly."""

    @pytest.mark.asyncio
    async def test_shared_limiter_caps_combined_throughput(self):
        config = Config()
        # Force a deterministic, low rate via the shared registry.
        BaseClient.reset_shared_limiters()
        a = _SharedClient(config, base_url="https://a", rate_limit=10.0)
        _SharedClient(config, base_url="https://b", rate_limit=10.0)
        # First call drains the single burst token; second waits ~0.1s
        # because both instances share one bucket.
        await a.rate_limiter.acquire()
        start = time.monotonic()
        await a.rate_limiter.acquire()
        elapsed = time.monotonic() - start
        # At 10 req/s, refill time is 0.1s. Allow generous margin.
        assert elapsed >= 0.05


class TestConcurrencyCap:
    """`max_concurrent` bounds requests in flight, independent of rate."""

    @pytest.mark.asyncio
    async def test_slot_caps_in_flight_holders(self):
        rl = RateLimiter(rate=1000.0, burst=10, max_concurrent=1)
        in_flight = 0
        peak = 0

        async def hold() -> None:
            nonlocal in_flight, peak
            async with rl.slot():
                in_flight += 1
                peak = max(peak, in_flight)
                await asyncio.sleep(0.02)
                in_flight -= 1

        await asyncio.gather(*(hold() for _ in range(4)))
        assert peak == 1

    @pytest.mark.asyncio
    async def test_slot_without_cap_allows_overlap(self):
        rl = RateLimiter(rate=1000.0, burst=10)
        in_flight = 0
        peak = 0

        async def hold() -> None:
            nonlocal in_flight, peak
            async with rl.slot():
                in_flight += 1
                peak = max(peak, in_flight)
                await asyncio.sleep(0.02)
                in_flight -= 1

        await asyncio.gather(*(hold() for _ in range(4)))
        assert peak > 1


class TestCrossRefBudget:
    """CrossRef, bioRxiv, and medRxiv searches all spend one CrossRef budget."""

    def setup_method(self):
        BaseClient.reset_shared_limiters()

    def teardown_method(self):
        BaseClient.reset_shared_limiters()

    def test_preprint_clients_share_crossref_limiter(self):
        config = Config()
        crossref = CrossRefClient(config)
        biorxiv = BioRxivClient(config)
        medrxiv = MedRxivClient(config)
        assert biorxiv._crossref.rate_limiter is crossref.rate_limiter
        assert medrxiv._crossref.rate_limiter is crossref.rate_limiter

    def test_public_pool_limits_without_contact_email(self):
        limiter = CrossRefClient(Config(contact_email="")).rate_limiter
        assert (limiter.rate, limiter.max_concurrent) == (0.9, 1)

    def test_polite_pool_limits_with_contact_email(self):
        limiter = CrossRefClient(Config(contact_email="a@example.org")).rate_limiter
        assert (limiter.rate, limiter.max_concurrent) == (2.7, 3)


class TestArxivBudget:
    def setup_method(self):
        BaseClient.reset_shared_limiters()

    def teardown_method(self):
        BaseClient.reset_shared_limiters()

    def test_arxiv_instances_share_one_serial_limiter(self):
        config = Config()
        a = ArXivClient(config)
        b = ArXivClient(config)
        assert a.rate_limiter is b.rate_limiter
        assert a.rate_limiter.max_concurrent == 1
        # arXiv API policy: at most one request every three seconds.
        assert a.rate_limiter.rate <= 1 / 3


class TestPause:
    @pytest.mark.asyncio
    async def test_pause_delays_next_acquire_for_every_caller(self):
        rl = RateLimiter(rate=1000.0, burst=10)
        rl.pause(0.1)
        start = time.monotonic()
        await rl.acquire()
        assert time.monotonic() - start >= 0.08
