# CLI Reference

Every OpenCite command and its options. Run `opencite --help` or
`opencite <command> --help` at any time for the authoritative, version-specific
listing.

## Global options

```text
opencite [--version] [--quiet] [--debug] <command> ...
```

- `--version`: print the installed version and exit.
- `--quiet`: suppress progress messages.
- `--debug`: enable debug logging.

| Command | Purpose |
| --- | --- |
| [`search`](#search) | Search for papers by keywords |
| [`lookup`](#lookup) | Look up papers by DOI, PMID, or other ID |
| [`cite`](#cite) | Citation graph: papers citing or cited by a paper |
| [`canonical`](#canonical) | Most-cited papers in a field |
| [`pdf`](#pdf) | Download a PDF for a paper |
| [`convert`](#convert) | Convert a PDF to markdown |
| [`ids`](#ids) | Convert between PMID, PMCID, and DOI |
| [`batch-fetch`](#batch-fetch) | Download PDFs for multiple papers |
| [`config`](#config) | Manage configuration |

---

## search

Find papers by keywords across all sources, deduplicated and merged.

```bash
opencite search "query" [--max N] [--source all|openalex|s2|pubmed|...]
    [--year-from YYYY] [--year-to YYYY] [--oa-only]
    [--sort relevance|citations|year] [-f text|json|bibtex|csv] [-o FILE] [-v]
```

| Option | Description |
| --- | --- |
| `--max N` | Maximum results (after dedup and sort) |
| `--source` | Restrict to one source; default `all` |
| `--year-from` / `--year-to` | Publication-year window |
| `--oa-only` | Open-access papers only |
| `--sort` | `relevance` (default), `citations`, or `year` |
| `-f`, `--format` | `text` (default), `json`, `bibtex`, `csv` |
| `-o`, `--output` | Write to a file instead of stdout |
| `-v`, `--verbose` | Include extra fields (PDF locations, license, version) |

See [Searching](../guides/searching.md).

---

## lookup

Look up one or more papers by identifier.

```bash
opencite lookup IDENTIFIER [IDENTIFIER ...] [--enrich] [--append-bib FILE]
    [-f text|json|bibtex] [-o FILE] [-v]
```

Accepts a DOI, `pmid:X`, `pmc:X`, `arxiv:X`, a Semantic Scholar ID, or an
OpenAlex ID. Multiple identifiers are allowed.

| Option | Description |
| --- | --- |
| `--enrich` | Fetch from all sources and merge into one record |
| `--append-bib FILE` | Append the BibTeX entry to an existing `.bib` file |
| `-f`, `--format` | `text` (default), `json`, `bibtex` |
| `-o`, `--output` | Write to a file instead of stdout |
| `-v`, `--verbose` | Include extra fields |

See [Lookup & Citations](../guides/lookup-and-citations.md).

---

## cite

Traverse the citation graph around a paper.

```bash
opencite cite IDENTIFIER [--direction citing|references|both] [--max N]
    [--sort citations|year] [--min-citations N] [-f text|json|bibtex] [-o FILE]
```

| Option | Description |
| --- | --- |
| `--direction` | `citing`, `references`, or `both` |
| `--max N` | Maximum neighbours to return |
| `--sort` | `citations` or `year` |
| `--min-citations N` | Keep only neighbours above this citation count |
| `-f`, `--format` | `text` (default), `json`, `bibtex` |
| `-o`, `--output` | Write to a file instead of stdout |

---

## canonical

Find the most-cited papers in a field.

```bash
opencite canonical "topic" [--max N] [--year-from YYYY] [--min-citations N]
    [-f text|json|bibtex] [-o FILE]
```

| Option | Description |
| --- | --- |
| `--max N` | Maximum results |
| `--year-from YYYY` | Earliest publication year |
| `--min-citations N` | Citation-count floor |
| `-f`, `--format` | `text` (default), `json`, `bibtex` |
| `-o`, `--output` | Write to a file instead of stdout |

---

## pdf

Download a PDF for a paper. **Requires the `[pdf]` extra.**

```bash
opencite pdf IDENTIFIER [-o PATH] [--filename NAME] [--convert]
    [--converter auto|markitdown|mistral]
```

| Option | Description |
| --- | --- |
| `-o`, `--output PATH` | Output file path or directory |
| `--filename NAME` | Override the output filename |
| `--convert` | Also write a markdown rendering next to the PDF |
| `--converter` | `auto` (default), `markitdown`, or `mistral` |

See [PDFs & Conversion](../guides/pdf-and-conversion.md).

---

## convert

Convert a local PDF to markdown. **Requires the `[pdf]` extra.**

```bash
opencite convert FILE.pdf [-o FILE] [--converter auto|markitdown|mistral]
    [--extract-images] [--images-dir DIR]
```

| Option | Description |
| --- | --- |
| `-o`, `--output FILE` | Output markdown path |
| `--converter` | `auto` (default), `markitdown`, or `mistral` |
| `--extract-images` | Extract figures into an images directory |
| `--images-dir DIR` | Where to place extracted images |

---

## ids

Convert between DOI, PMID, and PMCID using the NCBI ID Converter API.

```bash
opencite ids IDENTIFIER [IDENTIFIER ...] [-f text|json]
```

---

## batch-fetch

Download PDFs for many papers with controlled concurrency. **Requires the
`[pdf]` extra.**

```bash
opencite batch-fetch FILE [-o DIR] [--convert] [--concurrency N] [--summary FILE]
opencite batch-fetch --from-json FILE [options]
opencite batch-fetch --from-stdin [options]
```

| Option | Description |
| --- | --- |
| `FILE` | Text file with one identifier per line |
| `--from-json FILE` | JSON array of DOIs or opencite search results |
| `--from-stdin` | Read identifiers from stdin |
| `-o`, `--output DIR` | Output directory |
| `--convert` | Also produce markdown (organized into `pdf/`, `markdown/`, `markdown/img/`) |
| `--concurrency N` | Number of parallel downloads |
| `--summary FILE` | Write a machine-readable report |

---

## config

Manage configuration.

```bash
opencite config init    # create ~/.opencite/config.toml template
opencite config show    # display resolved config (keys masked)
opencite config path    # show config file location
```

See [Configuration](../guides/configuration.md).
