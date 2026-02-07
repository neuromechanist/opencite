# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenCite is a Python CLI tool and library for academic literature search and citation management. It aggregates results from three academic APIs (Semantic Scholar, OpenAlex, PubMed), deduplicates them, and outputs results as formatted text, JSON, or BibTeX. It also supports PDF-to-markdown conversion via Mistral AI OCR and Microsoft MarkItDown.

**Status:** Early stage; currently a single script (`scripts/lit_search.py`) being evolved into a proper Python package with CLI.

## Architecture

### Current State
- `scripts/lit_search.py` -- standalone async script that searches all three APIs in parallel, deduplicates by DOI and fuzzy title matching, and outputs results
- `Paper` dataclass is the central data model (title, authors, year, doi, abstract, url, source, citation_count, journal, pmid, keywords, bibtex)
- `.env` files at root and `scripts/` hold API keys (loaded manually, not via python-dotenv)

### API Integrations
- **OpenAlex** -- uses `pyalex` library; supports keyword search and citation graph (papers citing a DOI)
- **Semantic Scholar** -- direct REST via `httpx`; supports keyword search and DOI lookup; requires API key in `x-api-key` header
- **PubMed** -- NCBI eutils (esearch + efetch); XML response parsing; requires API key as query param

### PDF-to-Markdown
- **markit-mistral** (`../markit-mistral`) -- Mistral AI OCR-based converter, installed as dependency; CLI: `markit-mistral document.pdf -o output.md`
- **markitdown** (Microsoft) -- open source alternative; repo: https://github.com/microsoft/markitdown

## Running the Script

```bash
# Keyword search (all sources)
uv run --with httpx --with pyalex scripts/lit_search.py "query terms"

# Search single source
uv run --with httpx --with pyalex scripts/lit_search.py "query" --source pubmed

# BibTeX output
uv run --with httpx --with pyalex scripts/lit_search.py "query" --bibtex

# Citation search (papers citing a DOI)
uv run --with httpx --with pyalex scripts/lit_search.py --citing "10.1038/s41593-021-00962-x"

# DOI lookup
uv run --with httpx --with pyalex scripts/lit_search.py --doi "10.1038/..." --bibtex

# Batch DOI lookup and append to .bib file
uv run --with httpx --with pyalex scripts/lit_search.py --dois "10.1038/..." "10.1016/..." --append-bib refs.bib

# JSON output
uv run --with httpx --with pyalex scripts/lit_search.py "query" -o results.json
```

## Environment Variables

Required in `.env` (root or `scripts/`):
- `SEMANTIC_SCHOLAR_API_KEY` -- Semantic Scholar API
- `PUBMED_API_KEY` -- NCBI/PubMed API
- `OPENALEX_API_KEY` -- OpenAlex API (not yet used in code)
- `MISTRAL_API_KEY` -- Mistral AI for PDF-to-markdown conversion

## Planned Evolution

The project is being restructured from a standalone script into:
1. A proper Python package with CLI (using UV for dependency management)
2. A Claude Code skill/plugin that wraps the CLI
3. Core capabilities: keyword search, DOI lookup, citation graph traversal, BibTeX generation, PDF retrieval, PDF-to-markdown conversion (via markit-mistral and markitdown)

## Dependencies

Runtime: `httpx`, `pyalex`
PDF conversion: `markit-mistral` (from `../markit-mistral`), `markitdown`
Build/run: `uv`
