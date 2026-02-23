"""Configuration management for opencite.

Loads configuration from multiple sources with the following priority
(later sources override earlier ones):

1. ~/.opencite/config.toml (lowest)
2. ~/.opencite/.env
3. .env in current working directory
4. Environment variables (highest for individual values)
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".opencite"
CONFIG_FILE = CONFIG_DIR / "config.toml"

_CONFIG_TEMPLATE = """\
# opencite configuration
# See: https://github.com/neuromechanist/opencite

[api_keys]
semantic_scholar = ""
pubmed = ""
openalex = ""
mistral = ""

[publishers]
# elsevier = ""
# wiley_tdm = ""
# springer = ""

[settings]
contact_email = ""
timeout = 30.0
max_retries = 3
log_level = "WARNING"

[defaults]
max_results = 20
format = "text"
converter = "auto"
"""

# Mapping: TOML path -> (Config field name, env var name)
_TOML_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("api_keys", "semantic_scholar"): (
        "semantic_scholar_api_key",
        "SEMANTIC_SCHOLAR_API_KEY",
    ),
    ("api_keys", "pubmed"): ("pubmed_api_key", "PUBMED_API_KEY"),
    ("api_keys", "openalex"): ("openalex_api_key", "OPENALEX_API_KEY"),
    ("api_keys", "mistral"): ("mistral_api_key", "MISTRAL_API_KEY"),
    ("publishers", "elsevier"): ("elsevier_api_key", "OPENCITE_ELSEVIER_KEY"),
    ("publishers", "wiley_tdm"): ("wiley_tdm_token", "OPENCITE_WILEY_TDM_TOKEN"),
    ("publishers", "springer"): ("springer_api_key", "OPENCITE_SPRINGER_KEY"),
    ("settings", "contact_email"): ("contact_email", "OPENCITE_EMAIL"),
    ("settings", "timeout"): ("timeout", "OPENCITE_TIMEOUT"),
    ("settings", "max_retries"): ("max_retries", "OPENCITE_MAX_RETRIES"),
    ("settings", "log_level"): ("log_level", "OPENCITE_LOG_LEVEL"),
    ("defaults", "max_results"): ("default_max_results", "OPENCITE_MAX_RESULTS"),
    ("defaults", "format"): ("default_format", "OPENCITE_FORMAT"),
    ("defaults", "converter"): ("default_converter", "OPENCITE_CONVERTER"),
}


def _parse_dotenv(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict without modifying os.environ."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            result[key] = value
    return result


def _load_all_dotenv() -> dict[str, str]:
    """Load .env files from multiple locations, merging with priority.

    Priority (later overrides earlier):
    1. ~/.opencite/.env
    2. .env in CWD
    """
    merged: dict[str, str] = {}
    candidates = [
        CONFIG_DIR / ".env",
        Path.cwd() / ".env",
    ]
    for path in candidates:
        merged.update(_parse_dotenv(path))
    return merged


def _load_toml(config_path: Path | None = None) -> dict[str, str]:
    """Load TOML config and flatten to field_name -> value mapping."""
    path = config_path or _resolve_config_path()
    if not path.exists():
        return {}

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        logger.warning("Failed to parse %s: %s", path, e)
        return {}

    result: dict[str, str] = {}
    for (section, key), (field_name, _env_var) in _TOML_MAP.items():
        if section in data and key in data[section]:
            val = data[section][key]
            if val != "":  # Skip empty strings (template defaults)
                result[field_name] = str(val)
    return result


def _resolve_config_path() -> Path:
    """Resolve the config file path from OPENCITE_CONFIG env var or default."""
    env_path = os.environ.get("OPENCITE_CONFIG")
    if env_path:
        return Path(env_path)
    return CONFIG_FILE


def create_default_config(path: Path | None = None) -> Path:
    """Create a default config.toml file.

    Returns the path to the created file.
    """
    target = path or CONFIG_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_CONFIG_TEMPLATE)
    return target


@dataclass
class Config:
    """Configuration for opencite."""

    # API keys
    semantic_scholar_api_key: str = ""
    pubmed_api_key: str = ""
    openalex_api_key: str = ""
    mistral_api_key: str = ""

    # Publisher tokens
    elsevier_api_key: str = ""
    wiley_tdm_token: str = ""
    springer_api_key: str = ""

    # Rate limits (requests per second)
    openalex_rate_limit: float = 100.0
    s2_rate_limit: float = 1.0
    pubmed_rate_limit: float = 10.0
    arxiv_rate_limit: float = 3.0
    biorxiv_rate_limit: float = 10.0

    # Request settings
    timeout: float = 30.0
    max_retries: int = 3

    # Output defaults
    default_max_results: int = 20
    default_format: str = "text"
    default_converter: str = "auto"

    # Contact email for APIs that request it
    contact_email: str = ""

    # Logging
    log_level: str = "WARNING"

    @classmethod
    def from_env(cls, config_path: Path | None = None) -> Config:
        """Create config from TOML, .env files, and environment variables.

        Priority (later overrides earlier):
        1. Config dataclass defaults
        2. ~/.opencite/config.toml
        3. .env files (~/.opencite/.env, then CWD .env)
        4. Environment variables
        """
        kwargs: dict[str, str | float | int] = {}

        # Layer 1: TOML config
        toml_values = _load_toml(config_path)
        kwargs.update(toml_values)

        # Layer 2: .env files (merged)
        dotenv_values = _load_all_dotenv()

        # Layer 3: Environment variables (highest priority)
        # Map env var names to field names and apply
        for (_section, _key), (field_name, env_var) in _TOML_MAP.items():
            # Check env var first (highest priority), then .env, then keep TOML value
            env_val = os.environ.get(env_var)
            if env_val is not None:
                kwargs[field_name] = env_val
            elif env_var in dotenv_values:
                kwargs[field_name] = dotenv_values[env_var]

        # Also set env vars from .env for other tools that read os.environ
        for key, value in dotenv_values.items():
            os.environ.setdefault(key, value)

        # Type-coerce values to match field types
        field_types = {f.name: f.type for f in fields(cls)}
        coerced: dict[str, str | float | int] = {}
        for key, val in kwargs.items():
            expected_type = field_types.get(key, "str")
            if expected_type == "float" and not isinstance(val, float):
                coerced[key] = float(val)
            elif expected_type == "int" and not isinstance(val, int):
                coerced[key] = int(val)
            else:
                coerced[key] = val

        config = cls(**coerced)

        # Normalize log_level
        config.log_level = config.log_level.upper()

        return config

    def validate(self) -> list[str]:
        """Validate configuration. Returns list of warnings."""
        warnings = []
        if not self.openalex_api_key:
            warnings.append("OPENALEX_API_KEY not set. OpenAlex requires an API key.")
        if not self.semantic_scholar_api_key:
            warnings.append(
                "SEMANTIC_SCHOLAR_API_KEY not set. "
                "Semantic Scholar will use shared rate limit (unreliable)."
            )
        if not self.pubmed_api_key:
            warnings.append(
                "PUBMED_API_KEY not set. PubMed rate limit: 3 req/sec instead of 10."
            )
        return warnings

    def setup_logging(self) -> None:
        """Configure logging based on log_level."""
        logging.basicConfig(
            level=getattr(logging, self.log_level, logging.WARNING),
            format="%(levelname)s: %(name)s: %(message)s",
        )
        # Reduce noise from libraries
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("pyalex").setLevel(logging.WARNING)

    def show(self, mask_keys: bool = True) -> str:
        """Return a human-readable string of the resolved config.

        API keys are masked by default.
        """
        lines = []
        for f in fields(self):
            val = getattr(self, f.name)
            if mask_keys and "key" in f.name.lower() or "token" in f.name.lower():
                if val:
                    val = val[:4] + "..." + val[-4:] if len(val) > 8 else "****"
                else:
                    val = "(not set)"
            lines.append(f"  {f.name}: {val}")
        return "\n".join(lines)
