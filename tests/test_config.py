"""Tests for opencite.config."""

from __future__ import annotations

from opencite.config import Config


class TestConfig:
    def test_from_env(self):
        config = Config.from_env()
        assert isinstance(config, Config)
        assert config.timeout == 30.0
        assert config.max_retries == 3
        assert config.default_max_results == 20
        assert config.default_format == "text"

    def test_from_env_reads_api_keys(self):
        config = Config.from_env()
        # These may or may not be set depending on environment
        assert isinstance(config.semantic_scholar_api_key, str)
        assert isinstance(config.pubmed_api_key, str)
        assert isinstance(config.openalex_api_key, str)

    def test_validate_warns_missing_keys(self):
        config = Config()  # All keys empty
        warnings = config.validate()
        assert len(warnings) >= 1
        assert any("OPENALEX_API_KEY" in w for w in warnings)

    def test_validate_no_warnings_with_keys(self):
        config = Config(
            openalex_api_key="test",
            semantic_scholar_api_key="test",
            pubmed_api_key="test",
        )
        warnings = config.validate()
        assert len(warnings) == 0

    def test_setup_logging(self):
        config = Config(log_level="DEBUG")
        config.setup_logging()
        # Should not raise

    def test_custom_values(self):
        config = Config(
            timeout=60.0,
            max_retries=5,
            default_max_results=50,
            s2_rate_limit=2.0,
        )
        assert config.timeout == 60.0
        assert config.max_retries == 5
        assert config.default_max_results == 50
        assert config.s2_rate_limit == 2.0
