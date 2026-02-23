"""Tests for opencite.clients.base (RateLimiter and BaseClient)."""

from __future__ import annotations

import asyncio
import time

import pytest

from opencite.clients.base import BaseClient, RateLimiter
from opencite.config import Config


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_initial_burst_allows_immediate_calls(self):
        rl = RateLimiter(rate=10.0, burst=3)
        # Should be able to acquire burst count immediately
        for _ in range(3):
            await rl.acquire()
        # Tokens should be exhausted now
        assert rl._tokens < 1.0

    @pytest.mark.asyncio
    async def test_single_token_burst(self):
        rl = RateLimiter(rate=100.0, burst=1)
        start = time.monotonic()
        await rl.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05  # First call should be near-instant

    @pytest.mark.asyncio
    async def test_rate_limits_after_burst(self):
        rl = RateLimiter(rate=100.0, burst=1)
        await rl.acquire()
        # Second call should need to wait for token refill
        start = time.monotonic()
        await rl.acquire()
        elapsed = time.monotonic() - start
        # At 100 req/s, wait should be ~0.01s; allow generous margin
        assert elapsed < 0.5

    @pytest.mark.asyncio
    async def test_tokens_refill_over_time(self):
        rl = RateLimiter(rate=1000.0, burst=5)
        # Drain all tokens
        for _ in range(5):
            await rl.acquire()
        # Wait a bit for refill
        await asyncio.sleep(0.01)
        # Should be able to acquire again
        await rl.acquire()

    @pytest.mark.asyncio
    async def test_tokens_capped_at_burst(self):
        rl = RateLimiter(rate=1000.0, burst=3)
        # Wait long enough that many tokens would accumulate
        await asyncio.sleep(0.05)
        # Acquire burst + 1 to verify cap
        for _ in range(3):
            await rl.acquire()
        # The 4th should require waiting
        assert rl._tokens < 1.0

    def test_init_values(self):
        rl = RateLimiter(rate=10.0, burst=5)
        assert rl.rate == 10.0
        assert rl.burst == 5
        assert rl._tokens == 5.0


class _ConcreteClient(BaseClient):
    """Minimal concrete subclass for testing BaseClient."""

    def _default_headers(self) -> dict[str, str]:
        return {"X-Test": "true"}


class TestBaseClient:
    def test_init_default_values(self):
        config = Config()
        client = _ConcreteClient(
            config=config,
            base_url="https://api.example.com",
            rate_limit=10.0,
            burst=5,
        )
        assert client.base_url == "https://api.example.com"
        assert client.timeout == config.timeout
        assert client.max_retries == config.max_retries
        assert client._client is None

    def test_init_custom_timeout_and_retries(self):
        config = Config()
        client = _ConcreteClient(
            config=config,
            base_url="https://api.example.com",
            rate_limit=10.0,
            timeout=30.0,
            max_retries=5,
        )
        assert client.timeout == 30.0
        assert client.max_retries == 5

    @pytest.mark.asyncio
    async def test_context_manager(self):
        config = Config()
        client = _ConcreteClient(
            config=config,
            base_url="https://api.example.com",
            rate_limit=10.0,
        )
        assert client._client is None
        async with client:
            assert client._client is not None
        assert client._client is None

    @pytest.mark.asyncio
    async def test_request_without_context_raises(self):
        config = Config()
        client = _ConcreteClient(
            config=config,
            base_url="https://api.example.com",
            rate_limit=10.0,
        )
        with pytest.raises(RuntimeError, match="Client not initialized"):
            await client.get("/test")

    def test_rate_limiter_configured(self):
        config = Config()
        client = _ConcreteClient(
            config=config,
            base_url="https://api.example.com",
            rate_limit=50.0,
            burst=10,
        )
        assert client.rate_limiter.rate == 50.0
        assert client.rate_limiter.burst == 10
