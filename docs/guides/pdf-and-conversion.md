# PDFs & Conversion

OpenCite can retrieve PDFs, convert them to markdown, and download many papers
at once.

!!! warning "Requires the `[pdf]` extra"
    PDF retrieval and conversion depend on extra packages. Install them with
    `pip install 'opencite[pdf]'` (or `uv pip install 'opencite[pdf]'`). This
    extra also powers preprint HTML full-text shortcuts (arXiv ar5iv,
    bioRxiv/medRxiv `.full`).

## Download a single PDF

```bash
opencite pdf 10.1038/nature12345 -o paper.pdf
```

`-o` accepts either a file path (`paper.pdf`) or a directory. OpenCite tries
sources in priority order:

1. Publisher APIs (when you have configured publisher tokens)
2. OpenAlex / Semantic Scholar PDF locations
3. PMC open-access
4. Direct arXiv / bioRxiv URLs
5. DOI content negotiation

### Convert to markdown at the same time

```bash
opencite pdf 10.1038/nature12345 -o paper.pdf --convert
```

With `--convert`, OpenCite also writes a markdown file next to the PDF. When the
paper is in the PMC open-access subset, it uses the PMC BioC structured
full-text (sections, figures, tables, references) instead of converting the PDF,
which produces cleaner markdown.

Pick a converter explicitly:

```bash
opencite pdf 10.1038/nature12345 --convert --converter mistral
```

- `auto` (default): use markit-mistral when `MISTRAL_API_KEY` is set (better for
  math and complex layouts), otherwise fall back to markitdown (free, local).
- `markitdown`: always use the free local converter.
- `mistral`: always use markit-mistral (requires `MISTRAL_API_KEY`).

## Convert a PDF you already have

```bash
opencite convert paper.pdf -o paper.md
opencite convert paper.pdf --extract-images --images-dir ./img
```

The same `--converter auto|markitdown|mistral` choice applies. `--extract-images`
pulls figures out into an images directory.

## Batch downloads

Download PDFs for many papers with controlled concurrency. `batch-fetch` reads
from a text file (one identifier per line), a JSON file, or stdin.

```bash
# One DOI per line
opencite batch-fetch dois.txt -o ./papers --convert

# From a saved search (JSON array of results or DOIs)
opencite batch-fetch --from-json results.json --convert -o ./papers

# From stdin
cat dois.txt | opencite batch-fetch --from-stdin -o ./papers
```

Useful options:

- `--concurrency N`: how many downloads run in parallel.
- `--summary report.json`: write a machine-readable report of what succeeded.
- `--convert`: also produce markdown; output is organized into `pdf/`,
  `markdown/`, and `markdown/img/` subdirectories.

### A complete workflow

Search, save as JSON, then batch download and convert:

```bash
opencite search "tDCS motor cortex" --max 30 -f json -o results.json
opencite batch-fetch --from-json results.json \
    --convert \
    --summary report.json \
    -o ./papers
```

!!! note "Be deliberate about redistribution"
    PDFs you retrieve carry licenses. Before committing downloaded bytes to a
    public repository, read [Redistribution & Licensing](licensing.md), which
    explains the per-PDF license sidecar OpenCite writes.
