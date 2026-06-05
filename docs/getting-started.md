# Getting Started

This page takes you from a clean machine to your first search in a few minutes.

## Install

=== "uv (recommended)"

    ```bash
    uv pip install opencite              # core
    uv pip install 'opencite[pdf]'       # + PDF download and markdown conversion
    ```

=== "pip"

    ```bash
    pip install opencite                 # core
    pip install 'opencite[pdf]'          # + PDF download and markdown conversion
    ```

=== "uvx (no install)"

    ```bash
    uvx opencite --version
    uvx opencite search "spiking neural networks"
    ```

The core install keeps dependencies light. Install the `[pdf]` extra when you
need `opencite pdf`, `opencite convert`, `opencite batch-fetch --convert`, or
preprint HTML full-text (arXiv ar5iv, bioRxiv/medRxiv `.full`).

## Set up API keys

OpenCite needs keys for the three primary metadata sources. Generate them from
each provider, then make them available to OpenCite.

```bash
export SEMANTIC_SCHOLAR_API_KEY=your_key
export PUBMED_API_KEY=your_key
export OPENALEX_API_KEY=your_key
```

!!! note "OpenAlex now requires a key"
    OpenAlex requires an API key as of February 2026. Searches that include the
    OpenAlex source will fail without `OPENALEX_API_KEY`.

Prefer a config file? Create one and OpenCite will read it automatically:

```bash
opencite config init     # writes ~/.opencite/config.toml
opencite config show     # prints the resolved config with keys masked
opencite config path     # prints the config file location
```

See [Configuration](guides/configuration.md) for the full precedence rules,
publisher tokens, and the optional `MISTRAL_API_KEY` for PDF conversion.

## Your first search

```bash
opencite search "transformer attention mechanism"
```

Narrow it down and write BibTeX straight to a file:

```bash
opencite search "tDCS motor cortex" \
    --max 20 \
    --year-from 2020 \
    --sort citations \
    -f bibtex \
    -o refs.bib
```

## Look up a known paper

```bash
opencite lookup 10.1038/nature12345
opencite lookup 10.1038/nature12345 --enrich   # merge data from all sources
```

Identifiers can be a DOI, `pmid:X`, `pmc:X`, `arxiv:X`, a Semantic Scholar ID,
or an OpenAlex ID. You can pass several at once.

## Explore citations

```bash
opencite cite 10.1038/nature12345 --direction citing       # who cites it
opencite cite 10.1038/nature12345 --direction references   # what it cites
opencite canonical "deep learning" --min-citations 5000    # field landmarks
```

## Retrieve a PDF

```bash
# Requires the [pdf] extra
opencite pdf 10.1038/nature12345 -o paper.pdf --convert
```

With `--convert`, OpenCite also writes a markdown rendering next to the PDF
(using PMC structured full-text when available, otherwise converting the PDF).

## Where to go next

- [Searching](guides/searching.md): sources, filters, sorting, canonical papers.
- [Lookup & Citations](guides/lookup-and-citations.md): identifiers, enrichment, citation graphs.
- [PDFs & Conversion](guides/pdf-and-conversion.md): retrieval, conversion, batch downloads.
- [Output Formats](guides/output-formats.md): text, JSON, BibTeX, CSV.
- [API Reference](api/index.md): use OpenCite as a Python library.
