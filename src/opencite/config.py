"""Configuration management for opencite."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Load .env file from current directory or parent directories."""
    for candidate in [Path.cwd() / ".env", Path(__file__).parents[2] / ".env"]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())
            break


@dataclass
class Config:
    """Configuration for opencite."""

    # API keys
    semantic_scholar_api_key: str = ""
    pubmed_api_key: str = ""
    openalex_api_key: str = ""
    mistral_api_key: str = ""

    # Rate limits (requests per second)
    openalex_rate_limit: float = 100.0
    s2_rate_limit: float = 1.0
    pubmed_rate_limit: float = 10.0

    # Request settings
    timeout: float = 30.0
    max_retries: int = 3

    # Output defaults
    default_max_results: int = 20
    default_format: str = "text"

    # Contact email for APIs that request it
    contact_email: str = ""

    # Logging
    log_level: str = "WARNING"

    @classmethod
    def from_env(cls) -> Config:
        """Create config from environment variables and .env file."""
        _load_dotenv()
        return cls(
            semantic_scholar_api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY", ""),
            pubmed_api_key=os.getenv("PUBMED_API_KEY", ""),
            openalex_api_key=os.getenv("OPENALEX_API_KEY", ""),
            mistral_api_key=os.getenv("MISTRAL_API_KEY", ""),
            contact_email=os.getenv("OPENCITE_EMAIL", ""),
            timeout=float(os.getenv("OPENCITE_TIMEOUT", "30.0")),
            max_retries=int(os.getenv("OPENCITE_MAX_RETRIES", "3")),
            default_max_results=int(os.getenv("OPENCITE_MAX_RESULTS", "20")),
            default_format=os.getenv("OPENCITE_FORMAT", "text"),
            log_level=os.getenv("OPENCITE_LOG_LEVEL", "WARNING").upper(),
        )

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
