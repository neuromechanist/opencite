# OpenCite Project Memory

## Project Overview
OpenCite is a Python CLI/library for academic literature search and citation management. Aggregates Semantic Scholar, OpenAlex, PubMed (and arXiv/bioRxiv being added). Deduplicates and outputs text/JSON/BibTeX/CSV.

## Key Architecture
- `src/opencite/` package layout
- `models.py` - `Paper`, `IDSet` (frozen), `Author`, `Source`, `PDFLocation`, `SearchResult`
- `clients/` - async HTTP clients inheriting `BaseClient` ABC (base.py)
- `search.py` - `SearchOrchestrator` coordinates parallel search across sources
- `config.py` - `Config` dataclass, loaded from TOML/env vars

## Adding a New Source
1. Create `src/opencite/clients/{name}.py` implementing `BaseClient`
2. Add rate limit field to `Config` dataclass in `config.py`
3. Add source to `ALL_SOURCES` list in `search.py`
4. Add client instantiation to `SearchOrchestrator.__init__/__aenter__/__aexit__`
5. Add `_search_{name}` method to `SearchOrchestrator`
6. Update `_lookup_by_type` if needed

## Key Files
- `src/opencite/clients/base.py` - `BaseClient` ABC (rate limiting, retry, httpx)
- `src/opencite/clients/openalex.py` - Reference implementation (most complete)
- `src/opencite/search.py` - `SearchOrchestrator`, `ALL_SOURCES`
- `src/opencite/config.py` - `Config` dataclass with `_TOML_MAP`
- `src/opencite/models.py` - `IDSet` has `arxiv_id` field

## Commands
- `uv sync --extra dev` - install deps
- `uv run pytest` - run tests
- `uv run ruff check src/ tests/` - lint
- `uv run ruff format src/ tests/` - format

See `suggested_commands.md` for full list.
