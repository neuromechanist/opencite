"""Base API client with rate limiting and retry logic."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Self

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

import httpx

from opencite.exceptions import APIError

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for async operations.

    The token state (rate, tokens, refill clock) is plain floats and safe
    to share across event loops. The serializing `asyncio.Lock`, however,
    binds to whichever event loop first acquires it; when the limiter is
    re-used from a different loop (e.g. successive pytest-asyncio test
    functions), the lock is transparently recreated.
    """

    def __init__(self, rate: float, burst: int = 1, max_concurrent: int | None = None):
        """
        Args:
            rate: Requests per second allowed.
            burst: Maximum burst size.
            max_concurrent: Maximum requests in flight at once, or None
                for no cap. Some APIs (e.g. CrossRef) limit concurrency
                separately from request rate.
        """
        self.rate = rate
        self.burst = burst
        self.max_concurrent = max_concurrent
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock: asyncio.Lock | None = None
        self._lock_loop_id: int | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._semaphore_loop_id: int | None = None

    def _lock_for_loop(self) -> asyncio.Lock:
        loop_id = id(asyncio.get_running_loop())
        if self._lock is None or self._lock_loop_id != loop_id:
            self._lock = asyncio.Lock()
            self._lock_loop_id = loop_id
        return self._lock

    def _semaphore_for_loop(self) -> asyncio.Semaphore | None:
        if self.max_concurrent is None:
            return None
        loop_id = id(asyncio.get_running_loop())
        if self._semaphore is None or self._semaphore_loop_id != loop_id:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
            self._semaphore_loop_id = loop_id
        return self._semaphore

    @contextlib.asynccontextmanager
    async def slot(self) -> AsyncGenerator[None]:
        """Hold a concurrency slot (if capped) and consume one token."""
        semaphore = self._semaphore_for_loop()
        if semaphore is None:
            await self.acquire()
            yield
            return
        async with semaphore:
            await self.acquire()
            yield

    async def acquire(self) -> None:
        """Wait until a token is available, then consume one."""
        async with self._lock_for_loop():
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
            self._last_refill = now

            if self._tokens < 1.0:
                wait_time = (1.0 - self._tokens) / self.rate
                await asyncio.sleep(wait_time)
                self._tokens = 0.0
                self._last_refill = time.monotonic()
            else:
                self._tokens -= 1.0


class BaseClient(ABC):
    """Abstract base for all API clients.

    Handles HTTP session lifecycle, rate limiting, retries,
    and error normalization.

    Subclasses that should share a single token bucket across every
    instance in the process (e.g. Semantic Scholar's ~1 req/sec budget)
    set `shared_limiter_key` to a unique string. The first instance to
    initialize creates the limiter at the given rate; later instances
    reuse it regardless of who created them. Subclasses without a key
    keep per-instance limiters, matching the previous behavior.
    """

    # Per-process registry of shared rate limiters, keyed by `shared_limiter_key`.
    # Populated lazily by `__init__`. Use `reset_shared_limiters()` for tests.
    _shared_limiters: ClassVar[dict[str, RateLimiter]] = {}
    _shared_limiters_lock: ClassVar[threading.Lock] = threading.Lock()
    shared_limiter_key: ClassVar[str | None] = None

    def __init__(
        self,
        config: Config,
        base_url: str,
        rate_limit: float,
        burst: int = 1,
        timeout: float | None = None,
        max_retries: int | None = None,
        max_concurrent: int | None = None,
    ):
        self.config = config
        self.base_url = base_url
        self.rate_limiter = self._resolve_rate_limiter(
            rate_limit, burst, max_concurrent
        )
        self.timeout = timeout or config.timeout
        self.max_retries = max_retries or config.max_retries
        self._client: httpx.AsyncClient | None = None

    def _resolve_rate_limiter(
        self, rate_limit: float, burst: int, max_concurrent: int | None
    ) -> RateLimiter:
        key = self.shared_limiter_key
        if key is None:
            return RateLimiter(rate_limit, burst, max_concurrent)
        with BaseClient._shared_limiters_lock:
            limiter = BaseClient._shared_limiters.get(key)
            if limiter is None:
                limiter = RateLimiter(rate_limit, burst, max_concurrent)
                BaseClient._shared_limiters[key] = limiter
            return limiter

    @classmethod
    def reset_shared_limiters(cls) -> None:
        """Clear the shared limiter registry. Intended for tests."""
        with BaseClient._shared_limiters_lock:
            BaseClient._shared_limiters.clear()

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self._default_headers(),
            # Upstream APIs move endpoints behind 3xx (CORE now 301s
            # /v3/search/works -> /v3/search/works/). Without this the redirect
            # surfaces as an APIError and the source silently returns nothing.
            # httpx strips Authorization on cross-origin redirects, so this does
            # not leak an API key to a third-party host.
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @abstractmethod
    def _default_headers(self) -> dict[str, str]:
        """Return default headers including API keys."""
        ...

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a rate-limited, retried HTTP request."""
        if self._client is None:
            raise RuntimeError("Client not initialized. Use 'async with'.")

        last_failure: str | None = None
        for attempt in range(self.max_retries):
            try:
                async with self.rate_limiter.slot():
                    resp = await self._client.request(method, path, **kwargs)
                if resp.status_code == 429:
                    last_failure = "HTTP 429 Too Many Requests"
                    retry_after = _retry_after_seconds(resp)
                    logger.warning(
                        "Rate limited by %s, waiting %ds (attempt %d/%d)",
                        self.base_url,
                        retry_after,
                        attempt + 1,
                        self.max_retries,
                    )
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as e:
                last_failure = _describe(e)
                if e.response.status_code >= 500:
                    wait = 2**attempt
                    logger.warning(
                        "Server error %d from %s, retry in %ds",
                        e.response.status_code,
                        self.base_url,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise APIError.from_http_error(
                    e, e.response.status_code, _describe(e)
                ) from e
            except httpx.RequestError as e:
                last_failure = _describe(e)
                wait = 2**attempt
                logger.warning(
                    "Request error from %s: %s, retry in %ds",
                    self.base_url,
                    _describe(e),
                    wait,
                )
                await asyncio.sleep(wait)

        raise APIError(
            f"Failed after {self.max_retries} retries to {self.base_url}",
            details=last_failure,
        )

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._request("POST", path, **kwargs)


# Query parameters that carry credentials or contact details; their values
# are masked before a URL is put in an error message or log line.
_SENSITIVE_PARAMS = frozenset(
    {"api_key", "apikey", "key", "token", "access_token", "email", "mailto"}
)


def _redact_url(url: httpx.URL) -> str:
    params = [
        (name, "***" if name.lower() in _SENSITIVE_PARAMS else value)
        for name, value in url.params.multi_items()
    ]
    return str(url.copy_with(params=params)) if params else str(url)


def _describe(exc: Exception) -> str:
    """Render an exception for errors and logs without leaking credentials.

    HTTP status errors embed the request URL, which can hold an API key as a
    query parameter, so they are rebuilt from the status and a redacted URL.
    httpx timeouts often have an empty message, so fall back to the type name.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        resp = exc.response
        return (
            f"{resp.status_code} {resp.reason_phrase} for url "
            f"'{_redact_url(exc.request.url)}'"
        )
    return str(exc) or type(exc).__name__


def _retry_after_seconds(resp: httpx.Response, default: int = 5) -> int:
    """Parse a numeric Retry-After header; fall back for HTTP-date or junk."""
    try:
        return max(0, int(resp.headers.get("Retry-After", default)))
    except ValueError:
        return default
