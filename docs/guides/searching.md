# Searching

The `search` command finds papers by keywords across every configured source,
deduplicates the results, and returns a single merged list.

## Basic search

```bash
opencite search "transformer attention mechanism"
```

By default the search fans out to all available sources concurrently. Each
source contributes its hits; OpenCite then merges duplicates (DOI match first,
then fuzzy title match) and tracks which APIs contributed to each paper.

## Choose your sources

Restrict the search to a single source with `--source`:

```bash
opencite search "AlphaFold protein" --source openalex
opencite search "EEG microstates" --source pubmed
```

Restricting sources is the fastest, most deterministic way to search, because
OpenCite no longer waits on slower upstreams. It is the right choice when you
know which database has the best coverage for your topic.

| `--source` value | Database |
| --- | --- |
| `all` (default) | Every configured source |
| `openalex` | OpenAlex |
| `s2` | Semantic Scholar |
| `pubmed` | PubMed |
| `arxiv` | arXiv |
| `biorxiv` | bioRxiv |
| `medrxiv` | medRxiv |
| `osf` | OSF Preprints |
| `zenodo` | Zenodo |
| `figshare` | Figshare |
| `crossref` | CrossRef |
| `core` | CORE |

## Filter and sort

```bash
opencite search "tDCS motor cortex" \
    --max 30 \
    --year-from 2020 \
    --year-to 2024 \
    --oa-only \
    --sort citations
```

- `--max N`: cap the number of results (applied after dedup and sort).
- `--year-from` / `--year-to`: restrict to a publication-year window.
- `--oa-only`: keep only open-access papers.
- `--sort relevance|citations|year`: order the merged list. `relevance` is the
  default; `citations` surfaces the most influential work; `year` shows the
  newest first.

## Canonical papers in a field

When you want the landmark papers rather than the most recent, use `canonical`.
It searches and ranks by citation count, with a floor you control:

```bash
opencite canonical "deep learning" --min-citations 5000
opencite canonical "diffusion models" --max 10 --year-from 2020
```

- `--min-citations N`: drop papers below this citation count.
- `--max N` and `--year-from` work as they do for `search`.

## Save results for later

Any search can be written to a file in your format of choice:

```bash
opencite search "spiking neural networks" --max 50 -f json -o snn.json
opencite search "spiking neural networks" --max 50 -f bibtex -o snn.bib
```

The JSON output is the natural input for [batch PDF downloads](pdf-and-conversion.md#batch-downloads).
See [Output Formats](output-formats.md) for the full list.
