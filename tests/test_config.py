"""Tests for opencite.config."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from opencite.config import (
    Config,
    _load_toml,
    _parse_dotenv,
    create_default_config,
)


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

    def test_publisher_token_fields(self):
        config = Config(
            elsevier_api_key="elsevier_test",
            wiley_tdm_token="wiley_test",
            springer_api_key="springer_test",
        )
        assert config.elsevier_api_key == "elsevier_test"
        assert config.wiley_tdm_token == "wiley_test"
        assert config.springer_api_key == "springer_test"

    def test_default_converter_field(self):
        config = Config()
        assert config.default_converter == "auto"


class TestDotenvParsing:
    def test_parse_basic(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("KEY1=value1\nKEY2=value2\n")
            f.flush()
            result = _parse_dotenv(Path(f.name))
        os.unlink(f.name)
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_parse_comments_and_blanks(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("# Comment\n\nKEY=val\n# Another\n")
            f.flush()
            result = _parse_dotenv(Path(f.name))
        os.unlink(f.name)
        assert result == {"KEY": "val"}

    def test_parse_quoted_values(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("KEY1=\"quoted\"\nKEY2='single'\n")
            f.flush()
            result = _parse_dotenv(Path(f.name))
        os.unlink(f.name)
        assert result == {"KEY1": "quoted", "KEY2": "single"}

    def test_parse_missing_file(self):
        result = _parse_dotenv(Path("/nonexistent/.env"))
        assert result == {}

    def test_parse_value_with_equals(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("KEY=value=with=equals\n")
            f.flush()
            result = _parse_dotenv(Path(f.name))
        os.unlink(f.name)
        assert result == {"KEY": "value=with=equals"}


class TestTomlLoading:
    def test_load_toml_basic(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[api_keys]\nsemantic_scholar = "sk_test"\n')
            f.flush()
            result = _load_toml(Path(f.name))
        os.unlink(f.name)
        assert result == {"semantic_scholar_api_key": "sk_test"}

    def test_load_toml_skips_empty_strings(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[api_keys]\nsemantic_scholar = ""\npubmed = "pk_test"\n')
            f.flush()
            result = _load_toml(Path(f.name))
        os.unlink(f.name)
        assert "semantic_scholar_api_key" not in result
        assert result["pubmed_api_key"] == "pk_test"

    def test_load_toml_missing_file(self):
        result = _load_toml(Path("/nonexistent/config.toml"))
        assert result == {}

    def test_load_toml_settings(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("[settings]\ntimeout = 60.0\nmax_retries = 5\n")
            f.flush()
            result = _load_toml(Path(f.name))
        os.unlink(f.name)
        assert result["timeout"] == "60.0"
        assert result["max_retries"] == "5"

    def test_load_toml_defaults(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[defaults]\nmax_results = 50\nformat = "json"\n')
            f.flush()
            result = _load_toml(Path(f.name))
        os.unlink(f.name)
        assert result["default_max_results"] == "50"
        assert result["default_format"] == "json"


class TestConfigPriority:
    def test_env_var_overrides_toml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[api_keys]\nsemantic_scholar = "from_toml"\n')
            f.flush()
            toml_path = Path(f.name)

        old_val = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        os.environ["SEMANTIC_SCHOLAR_API_KEY"] = "from_env"
        try:
            config = Config.from_env(config_path=toml_path)
            assert config.semantic_scholar_api_key == "from_env"
        finally:
            if old_val is not None:
                os.environ["SEMANTIC_SCHOLAR_API_KEY"] = old_val
            else:
                os.environ.pop("SEMANTIC_SCHOLAR_API_KEY", None)
            os.unlink(f.name)

    def test_toml_applies_when_no_env_var(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[publishers]\nelsevier = "from_toml"\n')
            f.flush()
            toml_path = Path(f.name)

        old_val = os.environ.pop("OPENCITE_ELSEVIER_KEY", None)
        try:
            config = Config.from_env(config_path=toml_path)
            assert config.elsevier_api_key == "from_toml"
        finally:
            if old_val is not None:
                os.environ["OPENCITE_ELSEVIER_KEY"] = old_val
            os.unlink(f.name)

    def test_type_coercion(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("[settings]\ntimeout = 60.0\nmax_retries = 5\n")
            f.flush()
            config = Config.from_env(config_path=Path(f.name))
        os.unlink(f.name)
        assert isinstance(config.timeout, float)
        assert isinstance(config.max_retries, int)
        assert config.timeout == 60.0
        assert config.max_retries == 5


class TestCreateDefaultConfig:
    def test_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            result = create_default_config(path)
            assert result == path
            assert path.exists()
            content = path.read_text()
            assert "[api_keys]" in content
            assert "[settings]" in content
            assert "[defaults]" in content

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deep" / "nested" / "config.toml"
            create_default_config(path)
            assert path.exists()


class TestConfigShow:
    def test_show_masks_keys(self):
        config = Config(
            semantic_scholar_api_key="sk_1234567890abcdef",
            pubmed_api_key="pk_test",
        )
        output = config.show(mask_keys=True)
        assert "sk_1...cdef" in output
        assert "****" in output  # short key gets masked as ****
        assert "sk_1234567890abcdef" not in output

    def test_show_no_mask(self):
        config = Config(semantic_scholar_api_key="sk_test")
        output = config.show(mask_keys=False)
        assert "sk_test" in output

    def test_show_empty_keys(self):
        config = Config()
        output = config.show(mask_keys=True)
        assert "(not set)" in output
