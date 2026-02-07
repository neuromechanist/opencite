# OpenCite

Academic literature search, citation management, and PDF retrieval CLI.

Searches Semantic Scholar, OpenAlex, and PubMed in parallel, deduplicates results, and supports BibTeX output, citation graph traversal, PDF retrieval, and PDF-to-markdown conversion.

## Installation

```bash
pip install opencite
```

With PDF conversion support:

```bash
pip install opencite[convert]
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
opencite pdf 10.1038/nature12345 -o papers/
```

## Configuration

OpenCite needs API keys for the academic databases. You have two options:

**Option 1: Environment variables** (recommended for general use)

Add to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
export SEMANTIC_SCHOLAR_API_KEY=your_key
export PUBMED_API_KEY=your_key
export OPENALEX_API_KEY=your_key
export MISTRAL_API_KEY=your_key   # optional, for PDF-to-markdown via Mistral OCR
```

**Option 2: `.env` file** (convenient for development)

Copy the template and fill in your keys:

```bash
cp .env.example .env
# edit .env with your keys
```

OpenCite looks for `.env` in the current working directory.
