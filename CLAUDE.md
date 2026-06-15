# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenCite is a Python CLI tool and library for academic literature search and citation management. It aggregates results from a wide set of academic sources (Semantic Scholar, OpenAlex, PubMed, arXiv, bioRxiv, medRxiv, OSF Preprints, Zenodo, Figshare, CrossRef, CORE), deduplicates them, and outputs results as formatted text, JSON, BibTeX, or CSV. It also supports PDF retrieval, HTML full-text shortcuts for arXiv (ar5iv) and bioRxiv (.full), batch downloads, and PDF-to-markdown conversion.

## Build and Run

```bash
uv sync --extra dev              # install package + dev deps
uv run opencite --version        # verify CLI works
uv run opencite search "query"   # search for papers
uv run opencite lookup DOI       # look up a specific paper
uv run opencite cite DOI         # citation graph
uv run opencite canonical "topic"  # most-cited papers in a field
uv run opencite pdf DOI -o paper.pdf --convert  # download PDF + convert to markdown
uv run opencite batch-fetch dois.txt --convert -o ./papers  # batch download
uv run opencite config init      # create config template
```

## Testing and Linting

```bash
uv run pytest                    # run all tests
uv run pytest tests/test_models.py -v    # single test file
uv run pytest -k "test_doi"      # single test by name
uv run pytest -m integration     # API integration tests only
uv run ruff check src/ tests/    # lint
uv run ruff check --fix src/ tests/  # auto-fix lint
uv run ruff format src/ tests/   # format
```

## Releases & Citation

The package version is `__version__` in `src/opencite/__init__.py` (Hatch reads it). The
repository is archived to Zenodo on every GitHub release, minting a versioned DOI under a stable
concept DOI. When you bump `__version__` for a release, also bump `version` (and `date-released`)
in `CITATION.cff` and keep `.zenodo.json` in sync, then tag `vX.Y.Z` and create the GitHub
release. The concept DOI, added to `CITATION.cff` (`doi:`) and the README badge after the first
Zenodo deposit, is stable across versions.

## Architecture

### Package Layout (`src/opencite/`)
- `models.py` -- central data models: `Paper`, `Author`, `IDSet` (frozen), `Source`, `PDFLocation`, `SearchResult`, `CitationResult`, `parse_identifier()`
- `config.py` -- `Config` dataclass with `from_env()`, TOML config (`~/.opencite/config.toml`), multi-location `.env` loading, `create_default_config()`
- `exceptions.py` -- `OpenCiteError` hierarchy: `APIError`, `RateLimitError`, `APIKeyError`, etc.
- `cli.py` -- argparse with subcommands: search, lookup, cite, canonical, pdf, convert, ids, batch-fetch, config
- `utils.py` -- title normalization, fuzzy matching, author name parsing, abstract reconstruction
- `clients/` -- per-API async clients with rate limiting (base.py, openalex.py, semantic_scholar.py, pubmed.py, arxiv.py, biorxiv.py, pmc.py, id_converter.py)
- `search.py` -- `SearchOrchestrator` for parallel multi-source search with dedup/merge
- `citations.py` -- `CitationExplorer` for citation graph traversal and canonical paper discovery
- `dedup.py` -- DOI + fuzzy title deduplication with paper merging
- `bibtex.py` -- BibTeX fetch (S2 citationStyles, DOI negotiation) and generation
- `pdf.py` -- multi-source PDF retrieval pipeline with publisher-authenticated downloads; `retrieve_as_markdown()` tries PMC full text before PDF fallback
- `fulltext.py` -- `FullTextRetriever` for PMC BioC full-text retrieval, bypasses PDF pipeline for OA articles
- `pmc_convert.py` -- BioC JSON to markdown converter with section structure, figures, tables, and references
- `convert.py` -- PDF-to-markdown (markitdown, markit-mistral; both included by default) with image extraction support
- `batch.py` -- batch PDF download and conversion with controlled concurrency; prefers PMC full text when converting; organizes into pdf/, markdown/, markdown/img/ subdirs
- `formatters/` -- output formatters (text, json, bibtex, csv)

### Key Design Patterns
- **IDSet** is frozen (immutable) and centralizes all identifier types (DOI, PMID, PMCID, OpenAlex, S2, ArXiv) for cross-API lookup
- **Paper.data_sources** tracks which APIs contributed data (provenance)
- **BaseClient** ABC provides rate limiting (token bucket), retry with backoff, httpx session management
- Rate limits: OpenAlex 100 req/sec, PubMed 10 req/sec, Semantic Scholar 1 req/sec, arXiv 3 req/sec, bioRxiv 10 req/sec, PMC 3 req/sec
- **Full-text retrieval** (when `--convert` is used): PMC BioC API for OA articles -> structured markdown (no PDF needed). Uses `--no-fulltext` to skip.
- PDF retrieval tries sources in priority: publisher APIs (if tokens configured) -> OpenAlex/S2 PDF locations -> PMC OA -> direct arXiv/bioRxiv URL -> DOI content negotiation
- PDF-to-markdown `auto` mode: if `MISTRAL_API_KEY` is set, use markit-mistral (better for math/complex layouts); otherwise fall back to markitdown (free)
- Config loading priority: TOML < `.env` files < environment variables
- Batch downloads use a shared `PDFRetriever` with async semaphore for concurrency control

### API Integrations
- **OpenAlex** -- `pyalex` library; broadest coverage (250M+ works); best for PDF URLs, filtering, citation counts
- **Semantic Scholar** -- `httpx` REST; TLDR summaries, SPECTER embeddings, batch 500 IDs, `citationStyles` for BibTeX
- **PubMed/PMC** -- NCBI eutils XML; MeSH terms, ID Converter API; PMC BioC REST API for structured full-text (OA subset, ~4M+ articles)
- **arXiv** -- Atom v1 API; search + direct lookup by arXiv ID; no key required; direct PDF at `arxiv.org/pdf/{id}`
- **bioRxiv/medRxiv** -- CrossRef (`prefix:10.1101`) for keyword search; bioRxiv Content API for DOI lookup with biorxiv/medrxiv server fallback; no key required. Each is a first-class `--source`; container-title post-filtering keeps attribution clean.
- **OSF Preprints** -- single client wrapping `api.osf.io/v2/preprints/`; covers PsyArXiv/SocArXiv/EarthArXiv/MetaArXiv. Provider slug recorded in `data_sources` as `osf:{provider}`; no key required.
- **Zenodo** -- `zenodo.org/api/records` filtered to `resource_type=publication-preprint`; optional `ZENODO_ACCESS_TOKEN` for higher rate limits.
- **Figshare** -- `api.figshare.com/v2/articles/search` filtered to `item_type=11` (preprint); no key required.

## Configuration

Config loading priority (later overrides earlier):
1. `~/.opencite/config.toml`
2. `~/.opencite/.env`
3. `.env` in working directory
4. Environment variables

### API keys

- `SEMANTIC_SCHOLAR_API_KEY` -- Semantic Scholar API
- `PUBMED_API_KEY` -- NCBI/PubMed API
- `OPENALEX_API_KEY` -- OpenAlex API (required since Feb 2026)
- `MISTRAL_API_KEY` -- Mistral AI for PDF-to-markdown conversion (optional)

### Publisher tokens (optional, for authenticated PDF access)

- `ELSEVIER_API_KEY` -- Elsevier/ScienceDirect
- `WILEY_TDM_TOKEN` -- Wiley TDM
- `SPRINGER_API_KEY` -- Springer Nature

## Dependencies

Core: `httpx`, `pyalex`, `markitdown`, `markit-mistral>=0.2.2`
Dev: `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `pre-commit`
