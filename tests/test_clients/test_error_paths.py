"""Tests for BaseClient retry/backoff logic using respx HTTP mocking.

These tests verify error handling paths in BaseClient._request() without
hitting real APIs. They use respx to simulate HTTP error responses and
network failures.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from opencite.clients.base import BaseClient
from opencite.config import Config
from opencite.exceptions import APIError, APIKeyError

BASE_URL = "https://test-api.example.com"


class _TestClient(BaseClient):
    """Concrete BaseClient subclass for testing."""

    def __init__(self, config: Config):
        super().__init__(
            config=config,
            base_url=BASE_URL,
            rate_limit=1000.0,
            burst=100,
            timeout=5.0,
            max_retries=3,
        )

    def _default_headers(self) -> dict[str, str]:
        return {"X-Test": "true"}


@pytest.fixture
def test_config() -> Config:
    return Config(timeout=5.0, max_retries=3)


class TestRetryOn429:
    @respx.mock
    async def test_retries_on_429_then_succeeds(self, test_config: Config):
        route = respx.get(f"{BASE_URL}/data").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        async with _TestClient(test_config) as client:
            resp = await client.get("/data")
        assert resp.status_code == 200
        assert route.call_count == 2

    @respx.mock
    async def test_429_exhausts_retries(self, test_config: Config):
        respx.get(f"{BASE_URL}/data").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "0"})
        )
        async with _TestClient(test_config) as client:
            with pytest.raises(APIError, match="Failed after 3 retries"):
                await client.get("/data")


class TestRetryOn500:
    @respx.mock
    async def test_retries_on_500_then_succeeds(self, test_config: Config):
        route = respx.get(f"{BASE_URL}/data").mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        async with _TestClient(test_config) as client:
            resp = await client.get("/data")
        assert resp.status_code == 200
        assert route.call_count == 2

    @respx.mock
    async def test_500_exhausts_retries(self, test_config: Config):
        respx.get(f"{BASE_URL}/data").mock(return_value=httpx.Response(500))
        async with _TestClient(test_config) as client:
            with pytest.raises(APIError, match="Failed after 3 retries"):
                await client.get("/data")


class TestClientErrors:
    @respx.mock
    async def test_404_raises_immediately(self, test_config: Config):
        route = respx.get(f"{BASE_URL}/missing").mock(return_value=httpx.Response(404))
        async with _TestClient(test_config) as client:
            with pytest.raises(APIError, match="HTTP 404"):
                await client.get("/missing")
        assert route.call_count == 1

    @respx.mock
    async def test_401_raises_api_key_error(self, test_config: Config):
        route = respx.get(f"{BASE_URL}/auth").mock(return_value=httpx.Response(401))
        async with _TestClient(test_config) as client:
            with pytest.raises(APIKeyError):
                await client.get("/auth")
        assert route.call_count == 1

    @respx.mock
    async def test_403_raises_api_key_error(self, test_config: Config):
        route = respx.get(f"{BASE_URL}/forbidden").mock(
            return_value=httpx.Response(403)
        )
        async with _TestClient(test_config) as client:
            with pytest.raises(APIKeyError):
                await client.get("/forbidden")
        assert route.call_count == 1


class TestNetworkErrors:
    @respx.mock
    async def test_connection_error_retries_then_succeeds(self, test_config: Config):
        route = respx.get(f"{BASE_URL}/data").mock(
            side_effect=[
                httpx.ConnectError("Connection refused"),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        async with _TestClient(test_config) as client:
            resp = await client.get("/data")
        assert resp.status_code == 200
        assert route.call_count == 2

    @respx.mock
    async def test_timeout_retries_then_succeeds(self, test_config: Config):
        route = respx.get(f"{BASE_URL}/data").mock(
            side_effect=[
                httpx.ReadTimeout("Read timed out"),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        async with _TestClient(test_config) as client:
            resp = await client.get("/data")
        assert resp.status_code == 200
        assert route.call_count == 2

    @respx.mock
    async def test_connection_error_exhausts_retries(self, test_config: Config):
        respx.get(f"{BASE_URL}/data").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        async with _TestClient(test_config) as client:
            with pytest.raises(APIError, match="Failed after 3 retries"):
                await client.get("/data")


class TestClientNotInitialized:
    async def test_request_without_context_manager(self, test_config: Config):
        client = _TestClient(test_config)
        with pytest.raises(RuntimeError, match="Client not initialized"):
            await client.get("/data")


class TestPostMethod:
    @respx.mock
    async def test_post_request(self, test_config: Config):
        route = respx.post(f"{BASE_URL}/submit").mock(
            return_value=httpx.Response(200, json={"created": True})
        )
        async with _TestClient(test_config) as client:
            resp = await client.post("/submit", json={"key": "value"})
        assert resp.status_code == 200
        assert route.call_count == 1
