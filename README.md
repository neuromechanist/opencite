# OpenCite

Academic literature search, citation management, and PDF retrieval CLI.

Searches Semantic Scholar, OpenAlex, and PubMed in parallel, deduplicates results, and supports BibTeX output, citation graph traversal, PDF retrieval, and PDF-to-markdown conversion.

## Installation

```bash
uv pip install -e .
```

With PDF conversion support:

```bash
uv pip install -e ".[convert]"
```

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

Set API keys in a `.env` file or as environment variables:

```
SEMANTIC_SCHOLAR_API_KEY=your_key
PUBMED_API_KEY=your_key
OPENALEX_API_KEY=your_key
MISTRAL_API_KEY=your_key          # for PDF-to-markdown via Mistral OCR
```
