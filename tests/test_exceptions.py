"""Tests for opencite.exceptions."""

from __future__ import annotations

from opencite.exceptions import (
    APIError,
    APIKeyError,
    ConfigurationError,
    ConversionError,
    IDConversionError,
    OpenCiteError,
    PDFRetrievalError,
    RateLimitError,
    SearchError,
)


class TestOpenCiteError:
    def test_basic(self):
        err = OpenCiteError("something went wrong")
        assert str(err) == "something went wrong"
        assert err.message == "something went wrong"
        assert err.details is None

    def test_with_details(self):
        err = OpenCiteError("failed", details="extra info")
        assert str(err) == "failed\nDetails: extra info"
        assert err.details == "extra info"

    def test_is_exception(self):
        err = OpenCiteError("test")
        assert isinstance(err, Exception)


class TestConfigurationError:
    def test_inherits(self):
        err = ConfigurationError("bad config")
        assert isinstance(err, OpenCiteError)
        assert str(err) == "bad config"


class TestAPIError:
    def test_basic(self):
        err = APIError("api failure")
        assert str(err) == "api failure"
        assert err.status_code is None
        assert err.cause is None

    def test_with_status_and_cause(self):
        cause = ValueError("original")
        err = APIError("api failure", status_code=500, cause=cause)
        assert err.status_code == 500
        assert err.cause is cause

    def test_inherits_opencite_error(self):
        err = APIError("test")
        assert isinstance(err, OpenCiteError)


class TestAPIErrorFromHttpError:
    def test_401_returns_api_key_error(self):
        original = Exception("unauthorized")
        err = APIError.from_http_error(original, 401)
        assert isinstance(err, APIKeyError)

    def test_403_returns_api_key_error(self):
        original = Exception("forbidden")
        err = APIError.from_http_error(original, 403)
        assert isinstance(err, APIKeyError)

    def test_429_returns_rate_limit_error(self):
        original = Exception("too many requests")
        err = APIError.from_http_error(original, 429)
        assert isinstance(err, RateLimitError)
        assert err.cause is original

    def test_other_status_returns_api_error(self):
        original = Exception("server error")
        err = APIError.from_http_error(original, 502)
        assert isinstance(err, APIError)
        assert not isinstance(err, APIKeyError)
        assert not isinstance(err, RateLimitError)
        assert err.status_code == 502
        assert "HTTP 502" in str(err)
        assert err.cause is original


class TestAPIKeyError:
    def test_default_message(self):
        err = APIKeyError()
        assert "Invalid or missing API key" in str(err)
        assert "environment variable" in err.details

    def test_custom_message(self):
        err = APIKeyError("custom key error")
        assert "custom key error" in str(err)

    def test_inherits_api_error(self):
        assert isinstance(APIKeyError(), APIError)


class TestRateLimitError:
    def test_default(self):
        err = RateLimitError()
        assert "Rate limit exceeded" in str(err)
        assert err.retry_after is None

    def test_with_retry_after(self):
        err = RateLimitError(retry_after=30)
        assert err.retry_after == 30
        assert "30s" in err.details

    def test_with_cause(self):
        cause = ValueError("original")
        err = RateLimitError(cause=cause)
        assert err.cause is cause

    def test_inherits_api_error(self):
        assert isinstance(RateLimitError(), APIError)


class TestLeafExceptions:
    def test_search_error(self):
        err = SearchError("search failed")
        assert isinstance(err, OpenCiteError)
        assert str(err) == "search failed"

    def test_pdf_retrieval_error(self):
        err = PDFRetrievalError("no pdf")
        assert isinstance(err, OpenCiteError)
        assert str(err) == "no pdf"

    def test_conversion_error(self):
        err = ConversionError("convert failed")
        assert isinstance(err, OpenCiteError)
        assert str(err) == "convert failed"

    def test_id_conversion_error(self):
        err = IDConversionError("id convert failed")
        assert isinstance(err, OpenCiteError)
        assert str(err) == "id convert failed"
