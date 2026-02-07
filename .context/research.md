# OpenCite API Research

Comprehensive analysis of the three academic APIs for building the OpenCite CLI.

## Capability Matrix

| Capability | OpenAlex | Semantic Scholar | PubMed/PMC |
|---|---|---|---|
| **Keyword search** | Yes (title, abstract, fulltext) | Yes (relevance + bulk/boolean) | Yes (field tags, MeSH) |
| **DOI lookup** | `/works/doi:X` | `/paper/DOI:X` | `X[lid]` or `X[aid]` search |
| **PMID lookup** | `/works/pmid:X` | `/paper/PMID:X` | Native (efetch by ID) |
| **PMCID lookup** | `/works/pmcid:X` | `/paper/PMCID:X` | Native (efetch by ID) |
| **ArXiv lookup** | No direct | `/paper/ARXIV:X` | No |
| **Batch lookup** | 50 IDs via filter pipe | POST 500 IDs `/paper/batch` | POST thousands via epost |
| **Citing papers** | `filter=cites:W123` | `/paper/{id}/citations` | elink `pubmed_pubmed_citedin` |
| **References** | `referenced_works` field or `filter=cited_by:W123` | `/paper/{id}/references` | elink `pubmed_pubmed_refs` |
| **Related papers** | `related_works` field | Recommendations API | elink `pubmed_pubmed` (similarity) |
| **PDF URLs** | `best_oa_location.pdf_url`, `locations[].pdf_url` | `openAccessPdf.url` | PMC OA Service |
| **Full-text download** | `content_url` (100 credits) | No hosted content | PMC efetch XML, BioC API, FTP |
| **BibTeX** | No native | `citationStyles` field | No native (parse XML) |
| **TLDR summaries** | No | `tldr` field (~60M papers) | No |
| **Paper embeddings** | No | SPECTER v1/v2 | No |
| **Author search** | `/authors?search=X` | `/author/search?query=X` | `smith j[au]` |
| **Author profiles** | h-index, i10-index, works_count | h-index, paperCount, citationCount | No profiles |
| **ORCID support** | `author.orcid` | `externalIds.ORCID` | No |
| **MeSH terms** | `mesh` field (PubMed-indexed) | No | Native, hierarchical |
| **Topics/concepts** | Topics (domain>field>subfield) | `s2FieldsOfStudy` | MeSH hierarchy |
| **Publication types** | `type` field | `publicationTypes` | 70+ pub types via `[pt]` |
| **Retraction status** | `is_retracted` (Retraction Watch) | No | `"retracted publication"[pt]` |
| **Funder/grants** | `grants.funder`, `grants.award_id` | No | `[gr]` field tag |
| **ID conversion** | Implicit (accepts pmid, pmcid, doi) | Implicit (accepts all) | Dedicated ID Converter API |
| **Autocomplete** | `/autocomplete/{entity}` | `/paper/autocomplete` | No |
| **Aggregations** | `group_by` parameter | No | No |
| **Rate limit (no key)** | Not allowed (key required as of Feb 2026) | Shared pool, unreliable | 3 req/sec |
| **Rate limit (with key)** | 100 req/sec, 100K credits/day | 1 req/sec | 10 req/sec |
| **Pagination max** | Unlimited (cursor) | 1K (relevance), 10M (bulk) | 10K per search |

## PDF Retrieval Strategy

### Tier 1: Direct PDF URLs (fastest)

**OpenAlex** is the richest source for PDF URLs:
- `best_oa_location.pdf_url` -- algorithmically chosen best OA copy
- `locations[].pdf_url` -- all known PDF locations
- Priority: published version > accepted > submitted
- `content_url` field for OpenAlex-hosted PDFs (costs 100 credits)
- Filter: `has_content.pdf:true` or `is_oa:true`

**Semantic Scholar**:
- `openAccessPdf.url` -- direct PDF link when available
- `isOpenAccess` -- boolean flag
- Can filter search results: `openAccessPdf` parameter

### Tier 2: PMC Full Text

**PMC OA Web Service** (`https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi`):
- Query by PMCID: `?id=PMC5334499`
- Returns PDF and tgz (XML + images) download links
- Only works for PMC Open Access Subset (~3M articles)
- Filter by format: `&format=pdf`

**PMC BioC API** (structured full text):
- `https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{PMID}/unicode`
- Returns structured JSON with sections, paragraphs, annotations
- Good for text extraction without PDF parsing

**PMC efetch** (full text XML):
- `efetch.fcgi?db=pmc&id=PMC1234567&retmode=xml`
- Returns JATS XML for OA articles

### Tier 3: DOI Content Negotiation (fallback)

Already implemented in current code:
- `GET https://doi.org/{doi}` with `Accept: application/x-bibtex` for BibTeX
- Can also request `Accept: application/pdf` for PDFs (publisher-dependent)

### Recommended PDF Retrieval Pipeline

```
1. Check OpenAlex best_oa_location.pdf_url
2. Check Semantic Scholar openAccessPdf.url
3. If PMCID available, try PMC OA Service for PDF
4. If PMCID available, try BioC API for structured text
5. Fall back to DOI content negotiation
6. If all fail, return landing page URL for manual download
```

### ID Conversion for Cross-API Lookup

To maximize PDF retrieval, convert between ID types:
- **PMC ID Converter**: `https://pmc.ncbi.nlm.nih.gov/tools/id-converter-api/?tool=opencite&email=X&ids=PMID1,PMID2&format=json`
- Up to 200 IDs per request
- Converts PMID <-> PMCID <-> DOI <-> Manuscript ID
- OpenAlex also accepts `/works/pmid:X` and `/works/pmcid:X` directly

## Search Strategy by Use Case

### Keyword Search
Best approach: query all three in parallel (current design is good)
- **OpenAlex**: Broadest coverage (~250M works), fulltext search available
- **Semantic Scholar**: Good relevance ranking, TLDR summaries, boolean bulk search
- **PubMed**: Best for biomedical, MeSH term precision, structured field tags

### DOI Lookup
- **Semantic Scholar** `/paper/DOI:X` is fastest for single lookups
- **OpenAlex** `/works/doi:X` provides richest metadata (locations, topics, grants)
- Use both; merge results

### Citation Graph Traversal
- **OpenAlex**: `filter=cites:W123` returns citing works with full filtering/sorting
- **Semantic Scholar**: `/paper/{id}/citations` with up to 1K results, includes `influentialCitationCount`
- **PubMed**: elink `pubmed_pubmed_citedin` for biomedical citation chains

### Batch DOI Lookup
- **Semantic Scholar** POST `/paper/batch` with up to 500 IDs is most efficient
- **OpenAlex** filter pipe: up to 50 DOIs per request
- **PubMed** epost + efetch: thousands of PMIDs

## BibTeX Generation Strategy

```
1. Semantic Scholar citationStyles field (if available)
2. DOI content negotiation: GET doi.org/{doi} Accept: application/x-bibtex
3. Generate from metadata (current fallback, already implemented)
```

## PDF-to-Markdown Conversion

Two backends available:

### markit-mistral (Mistral AI OCR)
- Location: `../markit-mistral`
- CLI: `markit-mistral document.pdf -o output.md`
- Python: `MarkItMistral(api_key=KEY).convert_file("doc.pdf")`
- Strengths: math/LaTeX preservation, complex layouts, tables
- Requires: `MISTRAL_API_KEY`
- Cost: API usage fees

### markitdown (Microsoft, open source)
- Repo: https://github.com/microsoft/markitdown
- CLI: `markitdown document.pdf -o output.md`
- Strengths: free, no API key, good for simple documents
- Weaknesses: less accurate on math, complex layouts

### Recommended Strategy
```
1. Try markitdown first (free, no API costs)
2. If document has math/complex layout, use markit-mistral
3. Let user choose via CLI flag: --converter markitdown|mistral
```

## Rate Limit Management

| API | Strategy |
|---|---|
| OpenAlex | 100 req/sec is generous; batch via filter pipes; use `select` to reduce payload |
| Semantic Scholar | 1 req/sec is the bottleneck; use batch endpoint for multi-ID lookups; queue requests |
| PubMed | 10 req/sec is reasonable; use History Server for large jobs; batch efetch up to 500 records |

### Recommended: Async with per-API rate limiters
```python
# Per-API semaphores
openalex_limiter = AsyncLimiter(100, 1)    # 100/sec
s2_limiter = AsyncLimiter(1, 1)            # 1/sec
pubmed_limiter = AsyncLimiter(10, 1)       # 10/sec
```

## Unique Strengths Per API

### OpenAlex -- Use for:
- Broadest coverage (250M+ works)
- PDF URL discovery (best_oa_location)
- Rich filtering (90+ filters)
- Funder/grant information
- Aggregations/analytics (group_by)
- Institution and country-level analysis
- Retraction status (Retraction Watch)

### Semantic Scholar -- Use for:
- TLDR auto-summaries
- Paper embeddings (SPECTER v2) for similarity
- Recommendations API
- Influential citation count
- Boolean bulk search (10M results)
- Batch lookup (500 IDs at once)
- ArXiv paper lookup
- BibTeX via citationStyles field

### PubMed/PMC -- Use for:
- Biomedical literature (gold standard)
- MeSH term searching (hierarchical, exploded)
- PMC full-text access (XML, PDF, BioC)
- Publication type precision (70+ types)
- Proximity searching ("term1 term2"[tiab:~3])
- ID conversion service (PMID/PMCID/DOI)
- Free full text filter
- Clinical trial and systematic review filters
