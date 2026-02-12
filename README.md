# OpenCite

Academic literature search, citation management, and PDF retrieval CLI.

Searches Semantic Scholar, OpenAlex, and PubMed in parallel, deduplicates results, and supports BibTeX output, citation graph traversal, PDF retrieval, batch downloads, and PDF-to-markdown conversion.

## Installation

```bash
# uv (recommended)
uv pip install opencite
uv pip install 'opencite[convert]'     # with PDF conversion (markitdown + markit-mistral)

# pip
pip install opencite
pip install 'opencite[convert]'

# uvx (no install needed, runs from cache)
uvx opencite --version
```

For development:

```bash
git clone https://github.com/neuromechanist/opencite.git
cd opencite
uv sync --extra dev
```

## Claude Code Plugin

OpenCite is available as a [Claude Code](https://claude.ai/code) plugin, giving Claude direct access to academic literature search and citation management.

To install:

1. Open Claude Code
2. Type `/plugin` and press Enter
3. Select "Add marketplace"
4. Enter `neuromechanist/opencite`
5. Restart Claude Code

Once installed, use `/opencite` or ask Claude to search for papers, look up DOIs, get BibTeX, etc.

## Quick Start

```bash
# Search for papers
opencite search "transformer attention mechanism"

# Look up a paper by DOI
opencite lookup 10.1038/nature12345

# Find most-cited papers in a field
opencite canonical "deep learning for neuroscience" --min-citations 500

# Get papers citing a specific work
opencite cite 10.1038/nature12345

# Download a PDF
opencite pdf 10.1038/nature12345 -o paper.pdf

# Download and convert to markdown in one step
opencite pdf 10.1038/nature12345 -o paper.pdf --convert

# Batch download from a file of DOIs
opencite batch-fetch dois.txt --convert --summary report.json -o ./papers

# Convert a local PDF to markdown
opencite convert paper.pdf -o paper.md
```

## Configuration

OpenCite supports TOML config, `.env` files, and environment variables.

### Quick setup

```bash
opencite config init    # creates ~/.opencite/config.toml with template
opencite config show    # display resolved config (keys masked)
opencite config path    # show config file location
```

### Config loading priority

Later sources override earlier ones:

1. `~/.opencite/config.toml`
2. `~/.opencite/.env`
3. `.env` in working directory
4. Environment variables

### API keys

Required for academic database access:

```bash
export SEMANTIC_SCHOLAR_API_KEY=your_key
export PUBMED_API_KEY=your_key
export OPENALEX_API_KEY=your_key
```

Optional:

```bash
export MISTRAL_API_KEY=your_key        # for PDF-to-markdown via Mistral OCR
```

### Publisher tokens (optional)

For authenticated PDF downloads from paywalled publishers:

```bash
export ELSEVIER_API_KEY=your_key       # Elsevier/ScienceDirect
export WILEY_TDM_TOKEN=your_token      # Wiley TDM
export SPRINGER_API_KEY=your_key       # Springer Nature
```

These can also be set in `~/.opencite/config.toml`:

```toml
[publishers]
elsevier = "your_key"
wiley_tdm = "your_token"
springer = "your_key"
```

## Commands

### search - Find papers

```bash
opencite search "query" [--max N] [--source all|openalex|s2|pubmed]
    [--year-from YYYY] [--year-to YYYY] [--oa-only]
    [--sort relevance|citations|year] [-f text|json|bibtex|csv] [-o FILE] [-v]
```

### lookup - Look up papers by identifier

```bash
opencite lookup IDENTIFIER [IDENTIFIER ...] [--enrich] [--append-bib FILE]
    [-f text|json|bibtex] [-o FILE] [-v]
```

Accepts DOI, `pmid:X`, `pmc:X`, `arxiv:X`, S2 ID, or OpenAlex ID. Supports multiple IDs.

### cite - Citation graph

```bash
opencite cite IDENTIFIER [--direction citing|references|both] [--max N]
    [--sort citations|year] [--min-citations N] [-f text|json|bibtex] [-o FILE]
```

### canonical - Most-cited papers in a field

```bash
opencite canonical "topic" [--max N] [--year-from YYYY] [--min-citations N]
    [-f text|json|bibtex] [-o FILE]
```

### pdf - Download PDF

```bash
opencite pdf IDENTIFIER [-o PATH] [--filename NAME] [--convert]
    [--converter auto|markitdown|mistral]
```

`-o` accepts a file path (e.g., `paper.pdf`) or directory. With `--convert`, also generates a markdown file alongside the PDF.

### convert - PDF to markdown

```bash
opencite convert FILE.pdf [-o FILE] [--converter auto|markitdown|mistral]
    [--extract-images] [--images-dir DIR]
```

Auto mode uses markit-mistral when `MISTRAL_API_KEY` is set (better for math and complex layouts), otherwise falls back to markitdown (free, local).

### batch-fetch - Batch download PDFs

```bash
opencite batch-fetch FILE [-o DIR] [--convert] [--concurrency N] [--summary FILE]
opencite batch-fetch --from-json FILE [options]
opencite batch-fetch --from-stdin [options]
```

Downloads PDFs for multiple papers with controlled concurrency. Supports text files (one ID per line), JSON files (array of DOIs or opencite search results), and stdin.

Example workflow:

```bash
# Search and save as JSON, then batch download with conversion
opencite search "tDCS motor cortex" --max 30 -f json -o results.json
opencite batch-fetch --from-json results.json --convert --summary report.json -o ./papers
```

### ids - Convert between identifiers

```bash
opencite ids IDENTIFIER [IDENTIFIER ...] [-f text|json]
```

Converts between DOI, PMID, and PMCID using the NCBI ID Converter API.

### config - Manage configuration

```bash
opencite config init    # create ~/.opencite/config.toml template
opencite config show    # display resolved config (keys masked)
opencite config path    # show config file location
```

## Output Formats

All search/lookup/cite/canonical commands support `-f`/`--format`:

- `text` (default) - human-readable output
- `json` - structured JSON
- `bibtex` - BibTeX entries for citation managers
- `csv` - comma-separated values (search only)

Use `-o`/`--output FILE` to write to a file instead of stdout.

## License

MIT
