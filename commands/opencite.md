---
description: Academic literature search and citation management
allowed-tools: Bash, Read, Write, Glob, Grep
argument-hint: <search|lookup|cite|canonical|pdf|convert|ids> [args...]
---

# OpenCite CLI

You are helping the user run opencite commands for academic literature search and citation management.

## Setup Check

First, verify opencite is installed:

```bash
uv run opencite --version
```

If not installed, run `uv sync` in the opencite project directory.

## Routing

Based on the user's request, determine which subcommand to use:

- **search** - Find papers matching a query across Semantic Scholar, OpenAlex, and PubMed
- **lookup** - Look up a specific paper by DOI, PMID, PMCID, or other identifier
- **cite** - Get citing/cited-by papers for a given identifier (citation graph)
- **canonical** - Find the most-cited papers in a field or topic
- **pdf** - Download a PDF for a paper by identifier
- **convert** - Convert a PDF file to markdown
- **ids** - Convert between identifier types (DOI, PMID, PMCID)

## Common Patterns

### Search and export BibTeX
```bash
uv run opencite search "neural oscillations" --format bibtex --output refs.bib
```

### Look up by DOI
```bash
uv run opencite lookup "10.1038/s41586-024-07487-w"
```

### Citation graph
```bash
uv run opencite cite "10.1038/s41586-024-07487-w" --direction both --depth 1
```

### Find canonical papers
```bash
uv run opencite canonical "transformer architecture" --limit 10
```

### Download PDF and convert
```bash
uv run opencite pdf "10.1038/s41586-024-07487-w" --output paper.pdf
uv run opencite convert paper.pdf --output paper.md
```

### Convert IDs
```bash
uv run opencite ids "10.1038/s41586-024-07487-w" --from doi --to pmid
```

## Output Formats

All search/lookup/cite/canonical commands support `--format`:
- `text` (default) - human-readable table
- `json` - structured JSON
- `bibtex` - BibTeX entries for citation managers
- `csv` - comma-separated values

Use `--output <file>` to write to a file instead of stdout.

Run the appropriate command based on the user's request. If the user's intent is ambiguous, ask which subcommand they need.
