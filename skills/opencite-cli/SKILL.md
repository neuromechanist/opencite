---
name: OpenCite CLI
description: This skill should be used when the user asks to "search for papers", "find citations", "look up a DOI", "get BibTeX", "download PDF", "convert PDF to markdown", "find canonical papers", "convert identifiers", or mentions opencite, academic literature search, citation management, or paper retrieval.
version: 0.1.0
---

# OpenCite CLI Reference

OpenCite is a CLI tool and Python library for academic literature search and citation management. It aggregates results from Semantic Scholar, OpenAlex, and PubMed, deduplicates them, and outputs formatted results.

## Installation

```bash
uv sync                    # basic install
uv sync --extra convert    # with PDF conversion support
uv sync --extra dev        # with dev tools
```

## Environment Variables

Required API keys in `.env`:
- `SEMANTIC_SCHOLAR_API_KEY` - Semantic Scholar API
- `PUBMED_API_KEY` - NCBI/PubMed API
- `OPENALEX_API_KEY` - OpenAlex API (required since Feb 2026)
- `MISTRAL_API_KEY` - (optional) Mistral AI for enhanced PDF-to-markdown

## Commands

### search - Find papers

```bash
uv run opencite search "query string" [options]
```

Options:
- `--limit N` - Max results (default: 10)
- `--sources s2,openalex,pubmed` - Which APIs to query
- `--format text|json|bibtex|csv` - Output format
- `--output FILE` - Write to file
- `--verbose` - Show detailed progress

### lookup - Look up a paper

```bash
uv run opencite lookup IDENTIFIER [options]
```

Accepts DOI, PMID, PMCID, S2 ID, OpenAlex ID, or ArXiv ID. Auto-detects the type.

Options:
- `--format text|json|bibtex|csv`
- `--output FILE`

### cite - Citation graph

```bash
uv run opencite cite IDENTIFIER [options]
```

Options:
- `--direction citing|cited-by|both` - Direction of citations
- `--depth N` - How many hops (default: 1)
- `--limit N` - Max papers per hop
- `--format text|json|bibtex|csv`
- `--output FILE`

### canonical - Most-cited papers

```bash
uv run opencite canonical "topic" [options]
```

Finds the most-cited, foundational papers for a topic.

Options:
- `--limit N` - Number of papers (default: 10)
- `--format text|json|bibtex|csv`
- `--output FILE`

### pdf - Download PDF

```bash
uv run opencite pdf IDENTIFIER [options]
```

Tries multiple sources: OpenAlex, S2, PMC Open Access, DOI content negotiation.

Options:
- `--output FILE` - Output path (default: auto-named from title)

### convert - PDF to markdown

```bash
uv run opencite convert FILE.pdf [options]
```

Uses markitdown (free) or markit-mistral (if MISTRAL_API_KEY set) for better math/complex layout handling.

Options:
- `--output FILE` - Output path
- `--method auto|markitdown|mistral` - Conversion method

### ids - Convert identifiers

```bash
uv run opencite ids IDENTIFIER [options]
```

Options:
- `--from doi|pmid|pmcid` - Source ID type
- `--to doi|pmid|pmcid` - Target ID type

## Common Workflows

### Literature review: search, filter, export
```bash
# Search broadly
uv run opencite search "motor cortex oscillations" --limit 20 --format json --output results.json

# Export BibTeX for citation manager
uv run opencite search "motor cortex oscillations" --limit 20 --format bibtex --output refs.bib
```

### Deep-dive on a paper's impact
```bash
# Look up the paper
uv run opencite lookup "10.1038/s41586-024-07487-w"

# Get papers that cite it
uv run opencite cite "10.1038/s41586-024-07487-w" --direction citing --limit 20

# Get its references
uv run opencite cite "10.1038/s41586-024-07487-w" --direction cited-by --limit 20
```

### Find foundational papers and download
```bash
# Find canonical papers
uv run opencite canonical "attention mechanism" --limit 5

# Download the top result's PDF
uv run opencite pdf "DOI_FROM_RESULTS" --output attention.pdf

# Convert to markdown for reading
uv run opencite convert attention.pdf --output attention.md
```

### Cross-reference identifier conversion
```bash
# Convert DOI to PMID
uv run opencite ids "10.1001/jama.2024.12345" --from doi --to pmid

# Convert PMID to DOI
uv run opencite ids "38765432" --from pmid --to doi
```

## Error Handling

- **Rate limits**: Semantic Scholar has aggressive rate limiting (1 req/sec). If you get rate limit errors, wait and retry.
- **Missing API keys**: Commands will warn about missing keys but still query available sources.
- **Timeouts**: API calls may time out; retry or try a different source with `--sources`.
- **No results**: Try broader search terms or check identifier format.

## Python API

For programmatic use:
```python
from opencite import Config, Paper, SearchResult
from opencite.search import SearchOrchestrator

config = Config.from_env()
orchestrator = SearchOrchestrator(config)
results = await orchestrator.search("query", limit=10)
```
