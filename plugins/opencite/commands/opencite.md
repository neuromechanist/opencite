---
description: Academic literature search and citation management
allowed-tools: Bash, Read, Write, Glob, Grep
argument-hint: <search|lookup|cite|canonical|pdf|convert|ids|batch-fetch|config> [args...]
---

# OpenCite CLI

You are helping the user run opencite commands for academic literature search and citation management.

## Setup Check

First, verify opencite is installed:

```bash
uvx opencite --version
```

If not installed, run `uv tool install opencite` or `pip install opencite`.

## Routing

Based on the user's request, determine which subcommand to use:

- **search** - Find papers matching a query across Semantic Scholar, OpenAlex, and PubMed
- **lookup** - Look up a specific paper by DOI, PMID, PMCID, or other identifier
- **cite** - Get citing/cited-by papers for a given identifier (citation graph)
- **canonical** - Find the most-cited papers in a field or topic
- **pdf** - Download a PDF for a paper by identifier
- **convert** - Convert a PDF file to markdown
- **ids** - Convert between identifier types (DOI, PMID, PMCID)
- **batch-fetch** - Download PDFs for multiple papers from a file, JSON, or stdin
- **config** - Manage opencite configuration (init, show, path)

## Common Patterns

### Search and export BibTeX
```bash
uvx opencite search "neural oscillations" -f bibtex -o refs.bib
```

### Look up by DOI
```bash
uvx opencite lookup "10.1038/s41586-024-07487-w"
```

### Citation graph
```bash
uvx opencite cite "10.1038/s41586-024-07487-w" --direction both
```

### Find canonical papers
```bash
uvx opencite canonical "transformer architecture" --max 10
```

### Download PDF and convert
```bash
uvx opencite pdf "10.1038/s41586-024-07487-w" -o paper.pdf --convert
uvx opencite convert paper.pdf -o paper.md --converter auto
```

### Batch download with conversion
```bash
uvx opencite batch-fetch dois.txt --convert --summary report.json
uvx opencite search "tDCS" -f json -o results.json
uvx opencite batch-fetch --from-json results.json --convert -o ./papers
```

### Convert IDs
```bash
uvx opencite ids "10.1038/s41586-024-07487-w" -f json
```

### Configure API keys
```bash
uvx opencite config init   # creates ~/.opencite/config.toml template
uvx opencite config show   # display resolved config (keys masked)
uvx opencite config path   # show config file location
```

## Output Formats

All search/lookup/cite/canonical commands support `-f`/`--format`:
- `text` (default) - human-readable table
- `json` - structured JSON
- `bibtex` - BibTeX entries for citation managers
- `csv` - comma-separated values

Use `-o`/`--output <file>` to write to a file instead of stdout.

Run the appropriate command based on the user's request. If the user's intent is ambiguous, ask which subcommand they need.
