# Plan: PMC Full-Text Retrieval (Issue #19)

## Goal

Add PMC BioC API integration to retrieve structured full-text articles from
the PMC Open Access subset and convert them directly to markdown, bypassing
the PDF download + conversion pipeline entirely.

## API Choice: BioC REST API

After evaluating PMC OA Web Service, OAI-PMH, efetch, and BioC APIs, the
**BioC API** is the best fit:

- **URL**: `https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{PMCID}/unicode`
- Returns structured JSON with typed passages (TITLE, ABSTRACT, INTRO, METHODS, RESULTS, DISCUSS, CONCL, FIG, TABLE, REF)
- Each passage has `section_type`, `type` (paragraph, title_1, title_2, fig_caption, table, etc.), and `text`
- Figure filenames embedded in passage `infons.file` (e.g., `WJR-9-27-g001.jpg`)
- No API key required; OA subset only; clear error for non-OA articles
- Supports batch queries with comma-separated IDs

**PMC OA Web Service** (`oa.fcgi`) will be used as a secondary check to
confirm OA status and retrieve image tgz when needed.

## Implementation Steps

### Step 1: Create `src/opencite/clients/pmc.py` -- PMC BioC Client

New client extending `BaseClient` with:

- `PMCClient(BaseClient)` with base URL `https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful`
- Rate limit: 3 req/sec (per PMC guidelines)
- `async fetch_full_text(pmcid: str) -> dict | None` -- fetch BioC JSON for one article
- `async check_oa_status(pmcid: str) -> bool` -- query OA Web Service to check if article is in OA subset
- `async fetch_image(pmcid: str, filename: str, dest: Path) -> Path | None` -- download a figure image from PMC

Image URL strategy: Use the OA tgz link from the OA API, or try
`https://pmc.ncbi.nlm.nih.gov/articles/instance/{pmcid}/bin/{filename}`

### Step 2: Create `src/opencite/pmc_convert.py` -- BioC JSON to Markdown

New module for converting BioC JSON to clean markdown:

- `bioc_to_markdown(bioc_data: dict, images_dir: Path | None = None) -> str`
  - Iterates over `documents[0].passages`
  - Maps section types to markdown structure:
    - TITLE -> `# Title`
    - ABSTRACT -> `## Abstract\n\ntext`
    - INTRO -> `## Introduction\n\ntext` (with `title_1`/`title_2` as sub-headers)
    - METHODS -> `## Methods\n\ntext`
    - RESULTS -> `## Results\n\ntext`
    - DISCUSS -> `## Discussion\n\ntext`
    - CONCL -> `## Conclusion\n\ntext`
    - FIG -> `![caption](images/filename)` with caption text
    - TABLE -> markdown table formatting (from `table` type passages)
    - REF -> `## References\n\n` with numbered references
  - `type` field within passages determines formatting:
    - `title_1` -> `## Section Title`
    - `title_2` -> `### Sub-section Title`
    - `paragraph` -> plain text block
    - `fig_caption` / `fig_title_caption` -> figure with image ref
    - `table_caption` / `table` -> table formatting
    - `ref` -> reference entry
  - Returns clean markdown string

- `extract_figure_files(bioc_data: dict) -> list[tuple[str, str]]`
  - Returns list of `(figure_id, filename)` pairs from passage infons

### Step 3: Create `src/opencite/fulltext.py` -- Full-Text Retriever

New module parallel to `pdf.py`, orchestrates PMC full-text retrieval:

- `FullTextRetriever` class (async context manager like PDFRetriever)
  - `__init__(config: Config)` -- creates PMCClient and IDConverterClient
  - `async retrieve(identifier: str, output_dir: str = ".", paper: Paper | None = None, extract_images: bool = True) -> Path | None`
    1. Resolve PMCID (from paper, or via ID converter if only DOI/PMID given)
    2. Check OA status via PMC OA API
    3. Fetch BioC JSON via PMC BioC API
    4. Convert to markdown via `bioc_to_markdown()`
    5. Optionally download figure images
    6. Write markdown file to output_dir
    7. Return path to markdown file, or None if not available

### Step 4: Integrate into PDF pipeline (`pdf.py`)

Modify `PDFRetriever.download()` to try full-text first when `--convert` is
the end goal:

- Add a new method `async retrieve_as_markdown(identifier, output_dir, paper) -> Path | None`
  that uses `FullTextRetriever` internally
- When the caller wants markdown (indicated by a new parameter), try PMC full
  text first, fall back to PDF download + conversion
- Keep existing PDF-only flow unchanged for users who just want the PDF

### Step 5: Update `batch.py`

Modify `batch_download()` to accept `prefer_fulltext: bool = True`:

- When `convert=True` and `prefer_fulltext=True`:
  1. Try PMC full-text retrieval first (no PDF needed)
  2. If successful, write markdown directly to `markdown/` dir
  3. If not available, fall back to PDF download + conversion
- Track fulltext_retrieved count in `BatchResult`
- Add `fulltext_retrieved: int = 0` field to `BatchResult`

### Step 6: Update CLI (`cli.py`)

- `pdf` subcommand with `--convert`: automatically try PMC full-text first,
  fall back to PDF. Add `--no-fulltext` flag to skip PMC and force PDF path.
- `batch-fetch` subcommand with `--convert`: same behavior. Add `--no-fulltext`.
- No new subcommand needed; the feature is transparent to the user.

### Step 7: Tests

Create `tests/test_pmc_client.py`:
- Test BioC JSON parsing (with sample fixture data)
- Test OA status check (OA vs non-OA responses)
- Test error handling (network errors, malformed responses)

Create `tests/test_pmc_convert.py`:
- Test `bioc_to_markdown()` with sample BioC JSON covering all section types
- Test figure extraction
- Test table handling
- Test edge cases (empty passages, missing fields)

Create `tests/test_fulltext.py`:
- Test PMCID resolution flow
- Test fallback when article is not OA
- Test integration with markdown output

Add integration tests (marked `@pytest.mark.integration`):
- Real PMC BioC API call with known OA article
- Real OA status check

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `src/opencite/clients/pmc.py` | CREATE | PMC BioC client |
| `src/opencite/pmc_convert.py` | CREATE | BioC JSON to markdown converter |
| `src/opencite/fulltext.py` | CREATE | Full-text retrieval orchestrator |
| `src/opencite/pdf.py` | MODIFY | Add markdown retrieval option |
| `src/opencite/batch.py` | MODIFY | Add fulltext preference to batch |
| `src/opencite/cli.py` | MODIFY | Add --no-fulltext flag |
| `tests/test_pmc_client.py` | CREATE | PMC client tests |
| `tests/test_pmc_convert.py` | CREATE | BioC to markdown tests |
| `tests/test_fulltext.py` | CREATE | Full-text retriever tests |

## Implementation Order

1. `clients/pmc.py` + `tests/test_pmc_client.py` (foundation)
2. `pmc_convert.py` + `tests/test_pmc_convert.py` (conversion logic)
3. `fulltext.py` + `tests/test_fulltext.py` (orchestration)
4. Integrate into `pdf.py`, `batch.py`, `cli.py`
5. Integration tests
6. Update CLAUDE.md architecture docs

## Open Questions

None; all APIs tested and verified working.
