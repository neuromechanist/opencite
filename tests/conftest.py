"""Shared test fixtures for opencite."""

from __future__ import annotations

import os

import pytest

from opencite.clients.base import BaseClient
from opencite.config import Config, _load_all_dotenv
from opencite.models import Author, IDSet, Paper, Source

# Load .env files into os.environ BEFORE skipif decorators evaluate.
# This is necessary because pytest.mark.skipif evaluates its condition
# at import time, before Config.from_env() would normally run.
for _key, _value in _load_all_dotenv().items():
    os.environ.setdefault(_key, _value)


@pytest.fixture(autouse=True)
def _reset_shared_rate_limiters() -> None:
    """Clear the per-process shared limiter registry between tests so
    rate state and limiter identity from one test don't bleed into the next.
    """
    BaseClient.reset_shared_limiters()


@pytest.fixture
def config() -> Config:
    """Config loaded from environment."""
    return Config.from_env()


@pytest.fixture
def sample_paper() -> Paper:
    """A sample Paper for testing."""
    return Paper(
        title="Attention Is All You Need",
        ids=IDSet(
            doi="10.48550/arXiv.1706.03762",
            s2_id="204e3073870fae3d05bcbc2f6a8e263d9b72e776",
            arxiv_id="1706.03762",
        ),
        authors=[
            Author(name="Ashish Vaswani", family_name="Vaswani", given_name="Ashish"),
            Author(name="Noam Shazeer", family_name="Shazeer", given_name="Noam"),
            Author(name="Niki Parmar", family_name="Parmar", given_name="Niki"),
        ],
        year=2017,
        source_venue=Source(name="Advances in Neural Information Processing Systems"),
        abstract="The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
        citation_count=100000,
        is_oa=True,
        url="https://arxiv.org/abs/1706.03762",
        data_sources={"semanticscholar"},
    )


@pytest.fixture
def sample_paper_minimal() -> Paper:
    """A minimal Paper with just a title and DOI."""
    return Paper(
        title="Some Paper Title",
        ids=IDSet(doi="10.1234/test.2024"),
        year=2024,
    )


def has_api_key(key_name: str) -> bool:
    """Check if an API key is available in the environment."""
    return bool(os.environ.get(key_name))


skip_without_s2_key = pytest.mark.skipif(
    not has_api_key("SEMANTIC_SCHOLAR_API_KEY"),
    reason="SEMANTIC_SCHOLAR_API_KEY not set",
)

skip_without_pubmed_key = pytest.mark.skipif(
    not has_api_key("PUBMED_API_KEY"),
    reason="PUBMED_API_KEY not set",
)

skip_without_openalex_key = pytest.mark.skipif(
    not has_api_key("OPENALEX_API_KEY"),
    reason="OPENALEX_API_KEY not set",
)

_ALL_API_KEYS = (
    "SEMANTIC_SCHOLAR_API_KEY",
    "PUBMED_API_KEY",
    "OPENALEX_API_KEY",
)

skip_without_all_keys = pytest.mark.skipif(
    not all(os.environ.get(k) for k in _ALL_API_KEYS),
    reason="Not all API keys set (need S2, PubMed, OpenAlex)",
)
