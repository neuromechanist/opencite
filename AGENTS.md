# OpenCite Instructions

## Project Overview

OpenCite is a Python CLI tool and library for academic literature search and citation management.
It aggregates results from a wide set of academic sources (Semantic Scholar, OpenAlex, PubMed, arXiv, bioRxiv, medRxiv, OSF Preprints, Zenodo, Figshare, CrossRef, CORE),
deduplicates them, and outputs results as formatted text, JSON, BibTeX, or CSV.
It also supports PDF retrieval, HTML full-text shortcuts for arXiv (ar5iv) and bioRxiv (.full), batch downloads, and PDF-to-markdown conversion.

## Build and Run

```bash
uv sync --extra dev --extra pdf  # install package + dev deps + PDF converters (as CI does)
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
uv run pytest -m "not integration"  # unit tests (what CI runs)
uv run pytest                    # all tests, including live API calls
uv run pytest tests/test_models.py -v    # single test file
uv run pytest -k "test_doi"      # single test by name
uv run pytest -m integration     # API integration tests only
uv run pytest --cov=opencite     # with coverage
uv run ruff check src/ tests/    # lint
uv run ruff check --fix src/ tests/  # auto-fix lint
uv run ruff format src/ tests/   # format
uv run ty check                  # type check
uv run --group docs mkdocs serve # preview docs
```

CI (`.github/workflows/tests.yml`) runs only `ruff check` and `pytest -m "not integration"` on Python 3.11 to 3.13, plus a separate integration job.
`ruff format` and `ty check` run locally through pre-commit.
Docs deploy from `.github/workflows/docs.yml` (`mkdocs build --strict` to GitHub Pages), not `mkdocs gh-deploy`.

## Development Workflow

1. **Check context:** review `.context/plan.md` for current tasks and `.context/research.md` for API findings
2. **Branch:** `gh issue develop <issue-number>`, or a descriptive branch for unticketed work
3. **Code:** follow existing patterns (see `.rules/` for standards)
4. **Test:** real API calls or real sample data only (see `.rules/testing.md`)
5. **Document failures:** log dead ends in `.context/scratch_history.md`
6. **Commit:** atomic, <50 chars, no emojis, no AI attribution
7. **PR:** reference the issue; at most one full and one delta review, fixes on the same branch, then merge (see `.rules/code_review.md`)

## [CRITICAL] Core Principles

### No Mocks: Test Reality Only
- Integration tests hit the real APIs (`-m integration`); unit tests use real parsed payloads
- HTTP response fixtures (`respx`, `pytest-httpx`) are acceptable only for error paths, retries, and network failures
- No test is better than a mock test that artificially passes

**Details:** `.rules/testing.md`

### Every Source Must Return or Fail Loudly
- A source that silently returns zero results for a query it should match is a bug, not a quirk
- Log the cause of each source failure at WARNING with the source name; never swallow exceptions

### No Technical Debt Carried Forward
- Address all PR review findings before merge; only skip genuine false positives or intended design choices
- Replace, don't deprecate

**Details:** `.rules/code_review.md`

## [NEVER DO THIS]
- Never use mocks that replace business logic, stubs, or fake data in tests (`respx` fixtures for error and retry paths are the exception)
- Never use `pip`, `conda`, or `virtualenv`; use UV
- Never commit secrets, `.env` files, or API keys
- Never leave empty `except` blocks or silent failures
- Never add backward-compatibility shims; replace directly
- Never add TODO without a linked issue

## Releases & Citation

The package version is `__version__` in `src/opencite/__init__.py` (Hatch reads it).
The repository is archived to Zenodo on every GitHub release,
minting a versioned DOI under a stable concept DOI.
When you bump `__version__` for a release,
also bump `version` (and `date-released`) in `CITATION.cff` and keep `.zenodo.json` in sync,
then tag `vX.Y.Z` and create the GitHub release.
The concept DOI in `CITATION.cff` (`doi:`) and the README badge is stable across versions.

## Architecture

### Package Layout (`src/opencite/`)
- `models.py` -- central data models: `Paper`, `Author`, `IDSet` (frozen), `Source`, `PDFLocation`, `SearchResult`, `CitationResult`, `parse_identifier()`
- `config.py` -- `Config` dataclass with `from_env()`, TOML config (`~/.opencite/config.toml`), multi-location `.env` loading, `create_default_config()`
- `exceptions.py` -- `OpenCiteError` hierarchy: `APIError`, `RateLimitError`, `APIKeyError`, etc.
- `cli.py` -- argparse with subcommands: search, lookup, cite, canonical, pdf, convert, ids, batch-fetch, config
- `utils.py` -- title normalization, fuzzy matching, author name parsing, abstract reconstruction
- `clients/` -- per-API async clients on top of `base.py` (`BaseClient`): openalex, semantic_scholar, pubmed, pmc, crossref, core, unpaywall, id_converter, and the preprint servers arxiv, biorxiv, medrxiv, osf, zenodo, figshare, which subclass `PreprintClient` in `preprint_base.py` (biorxiv and medrxiv also share `_biorxiv_like.py`)
- `sources.py` -- source-name aliases (`_ALIASES`) and `disabled_sources` handling
- `preprint_fulltext.py` -- HTML full-text retrieval for preprint servers (ar5iv, bioRxiv `.full`)
- `__main__.py` -- console entry point (`opencite`)
- `search.py` -- `SearchOrchestrator` for parallel multi-source search with dedup/merge; `ALL_SOURCES` lists the searchable sources
- `citations.py` -- `CitationExplorer` for citation graph traversal and canonical paper discovery
- `dedup.py` -- DOI + fuzzy title deduplication with paper merging
- `bibtex.py` -- BibTeX fetch (S2 citationStyles, DOI negotiation) and generation
- `pdf.py` -- multi-source PDF retrieval pipeline with publisher-authenticated downloads; `retrieve_as_markdown()` tries PMC full text before PDF fallback
- `fulltext.py` -- `FullTextRetriever` for PMC BioC full-text retrieval, bypasses PDF pipeline for OA articles
- `pmc_convert.py` -- BioC JSON to markdown converter with section structure, figures, tables, and references
- `convert.py` -- PDF-to-markdown (markitdown, markit-mistral; both in the optional `pdf` extra) with image extraction support
- `batch.py` -- batch PDF download and conversion with controlled concurrency; prefers PMC full text when converting; organizes into pdf/, markdown/, markdown/img/ subdirs
- `formatters/` -- output formatters (text, json, bibtex, csv)

### Key Design Patterns
- **IDSet** is frozen (immutable) and centralizes all identifier types (DOI, PMID, PMCID, OpenAlex, S2, ArXiv) for cross-API lookup
- **Paper.data_sources** tracks which APIs contributed data (provenance)
- **BaseClient** ABC provides rate limiting (token bucket), retry with backoff, httpx session management
- Rate limits: OpenAlex 100 req/sec, PubMed 10 req/sec, Semantic Scholar 1 req/sec, arXiv 1 req/3 sec (one in flight), CrossRef 1 req/sec public or 3 req/sec with a contact email (both with a concurrency cap), PMC 3 req/sec
- Clients that hit the same upstream budget (arXiv, CrossRef, Semantic Scholar) set `shared_limiter_key` so all instances share one limiter; a 429 pauses that limiter for everyone
- Client `search()` methods raise on failure instead of returning `[]`; the orchestrator records them in `SearchResult.failed_sources` / `skipped_sources` and the CLI exits 1 when no source succeeded
- **Full-text retrieval** (when `--convert` is used): PMC BioC API for OA articles -> structured markdown (no PDF needed).
  Uses `--no-fulltext` to skip.
- PDF retrieval tries sources in priority: publisher APIs (if tokens configured) -> OpenAlex/S2 PDF locations -> PMC OA -> direct arXiv/bioRxiv URL -> DOI content negotiation
- PDF-to-markdown `auto` mode: if `MISTRAL_API_KEY` is set, use markit-mistral (better for math/complex layouts); otherwise fall back to markitdown (free)
- Config loading priority: TOML < `.env` files < environment variables
- Batch downloads use a shared `PDFRetriever` with async semaphore for concurrency control

### API Integrations
- **OpenAlex** -- `pyalex` library; broadest coverage (250M+ works); best for PDF URLs, filtering, citation counts
- **Semantic Scholar** -- `httpx` REST; TLDR summaries, SPECTER embeddings, batch 500 IDs, `citationStyles` for BibTeX
- **PubMed/PMC** -- NCBI eutils XML; MeSH terms, ID Converter API; PMC BioC REST API for structured full-text (OA subset, ~4M+ articles)
- **arXiv** -- Atom v1 API; search + direct lookup by arXiv ID; no key required; direct PDF at `arxiv.org/pdf/{id}`
- **bioRxiv/medRxiv** -- CrossRef (owner prefixes `10.1101` and `10.64898`, the latter for DOIs minted since the move to openRxiv) for keyword search; bioRxiv Content API for DOI lookup with biorxiv/medrxiv server fallback; no key required.
  Each is a first-class `--source`; the server is read from `resource.primary.URL` (or container-title) so attribution stays clean.
- **OSF Preprints** -- keyword search through SHARE (`share.osf.io/api/v3/index-card-search`), hydrated via `api.osf.io/v2/preprints/?filter[id]=`, because the v2 endpoint no longer supports `filter[q]`; covers PsyArXiv/SocArXiv/EarthArXiv/MetaArXiv.
  Provider slug recorded in `data_sources` as `osf:{provider}`; no key required.
- **Zenodo** -- `zenodo.org/api/records` filtered to `resource_type=publication-preprint`; plain queries require every term (`+term`); optional `ZENODO_ACCESS_TOKEN` for higher rate limits.
- **CORE** -- `api.core.ac.uk/v3/search/works/` (trailing slash; the shared client follows redirects); requires `CORE_API_KEY`, and is left out of default searches without one.
- **Figshare** -- `api.figshare.com/v2/articles/search` filtered to `item_type=11` (preprint); no key required.

### Adding a New Search Source
1. Create `src/opencite/clients/{name}.py` subclassing `BaseClient`, or `PreprintClient` for a preprint server (`openalex.py` and `osf.py` are references)
2. Add its rate limit to `Config` in `config.py` (and `_TOML_MAP` if configurable)
3. Add the source to `ALL_SOURCES` in `search.py` and to `_ALIASES` in `sources.py`
4. Instantiate it in `SearchOrchestrator.__init__`, `__aenter__`, and `__aexit__`
5. Add a `_search_{name}` method and an `if "{name}" in sources:` task block in `SearchOrchestrator.search`
6. Update `_lookup_by_type` if the source resolves identifiers
7. Add it to the `--source` choices in `cli.py` and the source table in `docs/guides/searching.md`
8. Add parser tests on real payloads and a live `@pytest.mark.integration` search test

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

Core: `httpx`, `pyalex`
PDF extra (`pdf`): `markitdown`, `markit-mistral>=0.2.3`
Dev extra (`dev`): `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-timeout`, `respx`, `ruff`, `ty`, `pre-commit`
Docs group (`docs`): `mkdocs-material`, `mkdocstrings[python]`

## [REFERENCE] Rules Directory

`.rules/` holds generic templates; where they differ from this file (for example CI steps, `uv sync --dev`, or `mkdocs gh-deploy`), this file wins.

- `.rules/testing.md` -- no-mock policy
- `.rules/python.md` -- UV, ruff, ty
- `.rules/git.md` -- commits, branches, merges
- `.rules/code_review.md` -- PR review toolkit and checklist
- `.rules/ci_cd.md` -- GitHub Actions setup
- `.rules/documentation.md` -- MkDocs setup
- `.rules/self_improve.md` -- turning lessons into rules

## Context Files
- `.context/plan.md` -- current tasks and phases
- `.context/research.md` -- API explorations and findings
- `.context/ideas.md` -- design concepts (create when needed)
- `.context/scratch_history.md` -- failed attempts (create when needed)

## Project Memory

- `.memory/` is the tracked, cross-agent store for durable operational observations.
- Keep one fact per Markdown file with `name`, `description`, `type`, `recorded`, and `revalidate_after` frontmatter; add a one-line hook to `.memory/INDEX.md`.
- `.context/decisions/` (when present) contains binding Architecture Decision Records,
  `.context/` contains non-binding analysis and plans,
  and `.memory/` contains non-binding observations.
  Promote a memory to an ADR when it encodes a choice; never treat a memory as policy.
- Correct or delete a memory when it becomes false.
  Never store secrets, tokens, credentials, private transcripts, customer data, personal data, or information about a named individual.
