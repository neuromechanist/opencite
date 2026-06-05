# Architecture

OpenCite aggregates results from many academic sources, deduplicates them, and
presents them as text, JSON, BibTeX, or CSV. It also retrieves PDFs, fetches
structured full-text, and converts PDFs to markdown.

## Package layout (`src/opencite/`)

| Module | Responsibility |
| --- | --- |
| `models.py` | Central data models: `Paper`, `Author`, `IDSet` (frozen), `Source`, `PDFLocation`, `SearchResult`, `CitationResult`, `parse_identifier()` |
| `config.py` | `Config` dataclass with `from_env()`, TOML config, multi-location `.env` loading, `create_default_config()` |
| `exceptions.py` | `OpenCiteError` hierarchy: `APIError`, `RateLimitError`, `APIKeyError`, and more |
| `cli.py` | argparse subcommands: `search`, `lookup`, `cite`, `canonical`, `pdf`, `convert`, `ids`, `batch-fetch`, `config` |
| `search.py` | `SearchOrchestrator`: parallel multi-source search with dedup/merge |
| `citations.py` | `CitationExplorer`: citation-graph traversal and canonical paper discovery |
| `dedup.py` | DOI + fuzzy-title deduplication with paper merging |
| `clients/` | Per-API async clients with rate limiting (`base.py`, `openalex.py`, `semantic_scholar.py`, `pubmed.py`, `arxiv.py`, ...) |
| `bibtex.py` | BibTeX fetch (S2 citation styles, DOI negotiation) and generation |
| `pdf.py` | Multi-source PDF retrieval with publisher-authenticated downloads |
| `fulltext.py` | `FullTextRetriever`: PMC BioC full-text for OA articles |
| `pmc_convert.py` | BioC JSON to markdown (sections, figures, tables, references) |
| `convert.py` | PDF-to-markdown (markitdown, markit-mistral) with image extraction |
| `batch.py` | Batch PDF download and conversion with controlled concurrency |
| `formatters/` | Output formatters (text, json, bibtex, csv) |
| `utils.py` | Title normalization, fuzzy matching, author parsing, abstract reconstruction |

## Key design patterns

- **`IDSet` is frozen.** It centralizes every identifier type (DOI, PMID, PMCID,
  OpenAlex, S2, arXiv) so cross-API lookup and deduplication have one source of
  truth.
- **Provenance.** `Paper.data_sources` records which APIs contributed data to a
  merged record.
- **Rate-limited clients.** `BaseClient` provides a token-bucket rate limiter,
  retry with backoff, and httpx session management. Each source has its own
  limit (OpenAlex 100 req/s, PubMed 10 req/s, Semantic Scholar 1 req/s, arXiv
  3 req/s, and so on).
- **Parallel fan-out, sequential drain.** `SearchOrchestrator.search()` launches
  one task per source, then awaits them, merges, deduplicates, sorts, and
  truncates to `max_results`. Pending tasks are always cancelled and drained so
  none outlives the call.
- **Full-text shortcuts.** When converting, OpenCite prefers PMC BioC structured
  full-text for open-access articles (no PDF needed) and HTML full-text for
  arXiv ar5iv and bioRxiv/medRxiv `.full`.
- **PDF priority chain.** Publisher APIs (if tokens are configured) -> OpenAlex /
  S2 PDF locations -> PMC OA -> direct arXiv/bioRxiv URL -> DOI content
  negotiation.
- **Config precedence.** TOML < `.env` files < environment variables.

## Source integrations

| Source | Backend | Notes |
| --- | --- | --- |
| OpenAlex | `pyalex` | Broadest coverage (250M+ works); best for PDF URLs, filtering, citation counts |
| Semantic Scholar | httpx REST | TLDR summaries, embeddings, batch 500 IDs, `citationStyles` for BibTeX |
| PubMed / PMC | NCBI eutils XML | MeSH terms, ID Converter API; PMC BioC for structured full-text |
| arXiv | Atom v1 API | Search + direct ID lookup; no key; direct PDF |
| bioRxiv / medRxiv | CrossRef + Content API | Keyword search via CrossRef; DOI lookup via Content API; no key |
| OSF Preprints | `api.osf.io/v2/preprints/` | PsyArXiv / SocArXiv / EarthArXiv / MetaArXiv; provider recorded as `osf:{provider}` |
| Zenodo | `zenodo.org/api/records` | Filtered to publication preprints; optional access token |
| Figshare | `api.figshare.com/v2` | Filtered to preprints; no key |
| CrossRef | CrossRef REST | DOI metadata and preprint search |
| CORE | CORE API | Aggregated open access |
