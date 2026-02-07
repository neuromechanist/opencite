#!/usr/bin/env python3
"""Literature search engine for grant proposal research.

Searches Semantic Scholar, OpenAlex, and PubMed in parallel,
deduplicates results, and optionally outputs BibTeX entries.

Usage:
    uv run --with httpx --with pyalex scripts/lit_search.py "query"
    uv run --with httpx --with pyalex scripts/lit_search.py "query" --bibtex
    uv run --with httpx --with pyalex scripts/lit_search.py --citing DOI
    uv run --with httpx --with pyalex scripts/lit_search.py --doi DOI --bibtex
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
ENV_FILE = SCRIPT_DIR / ".env"

# Load .env file
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
PUBMED_API_KEY = os.environ.get("PUBMED_API_KEY", "")

SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
PUBMED_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Paper:
    title: str
    authors: str  # "Last1, Last2, ..."
    year: str
    doi: str
    abstract: str
    url: str
    source: str  # "openalex", "semanticscholar", "pubmed"
    citation_count: int = 0
    journal: str = ""
    pmid: str = ""
    external_id: str = ""
    bibtex: str = ""
    keywords: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# OpenAlex search
# ---------------------------------------------------------------------------


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    if not inverted_index:
        return ""
    max_pos = 0
    for positions in inverted_index.values():
        if positions:
            max_pos = max(max_pos, max(positions))
    words = [""] * (max_pos + 1)
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    return " ".join(w for w in words if w)


async def search_openalex(query: str, max_results: int = 20) -> list[Paper]:
    """Search OpenAlex for papers matching query."""
    try:
        from pyalex import Works
    except ImportError:
        print("Warning: pyalex not installed, skipping OpenAlex", file=sys.stderr)
        return []

    papers = []
    try:
        works_query = Works().search(query).select([
            "id",
            "title",
            "abstract_inverted_index",
            "publication_date",
            "doi",
            "primary_location",
            "cited_by_count",
            "authorships",
        ])
        results = list(works_query.get(per_page=min(max_results, 200)))

        for work in results[:max_results]:
            title = work.get("title") or ""
            if not title:
                continue
            abstract = _reconstruct_abstract(
                work.get("abstract_inverted_index")
            )
            doi_raw = work.get("doi") or ""
            doi = doi_raw.replace("https://doi.org/", "").strip()
            year_str = (work.get("publication_date") or "")[:4]

            # Extract authors
            authorships = work.get("authorships") or []
            author_names = []
            for a in authorships[:10]:
                author = a.get("author", {})
                name = author.get("display_name", "")
                if name:
                    author_names.append(name)
            authors = "; ".join(author_names)
            if len(authorships) > 10:
                authors += " et al."

            # URL
            url = f"https://doi.org/{doi}" if doi else work.get("id", "")

            # Journal
            loc = work.get("primary_location") or {}
            source_info = loc.get("source") or {}
            journal = source_info.get("display_name", "")

            papers.append(Paper(
                title=title,
                authors=authors,
                year=year_str,
                doi=doi,
                abstract=abstract[:500],
                url=url,
                source="openalex",
                citation_count=work.get("cited_by_count", 0),
                journal=journal,
                external_id=work.get("id", ""),
            ))
    except Exception as e:
        print(f"Warning: OpenAlex search failed: {e}", file=sys.stderr)

    return papers


async def search_openalex_citing(doi: str, max_results: int = 50) -> list[Paper]:
    """Find papers citing a specific DOI using OpenAlex."""
    try:
        from pyalex import Works
        import pyalex
        pyalex.config.email = "grant-search@example.com"
    except ImportError:
        print("Warning: pyalex not installed, skipping citation search", file=sys.stderr)
        return []

    papers = []
    try:
        # Resolve DOI to OpenAlex ID (cites filter needs OA ID)
        work = Works()[f"https://doi.org/{doi}"]
        oa_id = work.get("id", "")
        if not oa_id:
            print(f"Warning: Could not resolve DOI {doi} to OpenAlex ID", file=sys.stderr)
            return []

        works_query = (
            Works()
            .filter(cites=oa_id)
            .select([
                "id",
                "title",
                "abstract_inverted_index",
                "publication_date",
                "doi",
                "primary_location",
                "cited_by_count",
                "authorships",
            ])
            .sort(cited_by_count="desc")
        )
        results = list(works_query.get(per_page=min(max_results, 200)))

        for work in results[:max_results]:
            title = work.get("title") or ""
            if not title:
                continue
            abstract = _reconstruct_abstract(
                work.get("abstract_inverted_index")
            )
            doi_raw = work.get("doi") or ""
            work_doi = doi_raw.replace("https://doi.org/", "").strip()
            year_str = (work.get("publication_date") or "")[:4]

            authorships = work.get("authorships") or []
            author_names = []
            for a in authorships[:10]:
                author = a.get("author", {})
                name = author.get("display_name", "")
                if name:
                    author_names.append(name)
            authors = "; ".join(author_names)
            if len(authorships) > 10:
                authors += " et al."

            url = f"https://doi.org/{work_doi}" if work_doi else work.get("id", "")
            loc = work.get("primary_location") or {}
            source_info = loc.get("source") or {}
            journal = source_info.get("display_name", "")

            papers.append(Paper(
                title=title,
                authors=authors,
                year=year_str,
                doi=work_doi,
                abstract=abstract[:500],
                url=url,
                source="openalex",
                citation_count=work.get("cited_by_count", 0),
                journal=journal,
                external_id=work.get("id", ""),
            ))
    except Exception as e:
        print(f"Warning: OpenAlex citation search failed: {e}", file=sys.stderr)

    return papers


# ---------------------------------------------------------------------------
# Semantic Scholar search
# ---------------------------------------------------------------------------


async def search_semantic_scholar(
    query: str, max_results: int = 20, api_key: str = ""
) -> list[Paper]:
    """Search Semantic Scholar for papers matching query."""
    papers = []
    params = {
        "query": query,
        "limit": min(max_results, 100),
        "fields": "paperId,title,abstract,year,url,openAccessPdf,citationCount,externalIds,authors,journal",
    }
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                SEMANTIC_SCHOLAR_URL, params=params, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        print(f"Warning: Semantic Scholar search failed: {e}", file=sys.stderr)
        return []

    for paper in data.get("data", []):
        title = paper.get("title") or ""
        if not title:
            continue

        paper_id = paper.get("paperId", "")
        paper_url = paper.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}"

        # DOI from externalIds
        ext_ids = paper.get("externalIds") or {}
        doi = ext_ids.get("DOI", "")
        pmid = ext_ids.get("PubMed", "")

        # Open access PDF
        oa = paper.get("openAccessPdf")
        if oa and oa.get("url"):
            paper_url = oa["url"]

        # Authors
        ss_authors = paper.get("authors") or []
        author_names = [a.get("name", "") for a in ss_authors[:10] if a.get("name")]
        authors = "; ".join(author_names)
        if len(ss_authors) > 10:
            authors += " et al."

        # Journal
        journal_info = paper.get("journal") or {}
        journal = journal_info.get("name", "")

        papers.append(Paper(
            title=title,
            authors=authors,
            year=str(paper.get("year", "")),
            doi=doi,
            abstract=(paper.get("abstract") or "")[:500],
            url=paper_url,
            source="semanticscholar",
            citation_count=paper.get("citationCount", 0),
            journal=journal,
            pmid=pmid,
            external_id=paper_id,
        ))

    return papers


# ---------------------------------------------------------------------------
# PubMed search
# ---------------------------------------------------------------------------


async def search_pubmed(
    query: str, max_results: int = 20, api_key: str = ""
) -> list[Paper]:
    """Search PubMed using eutils (esearch + efetch)."""
    papers = []

    # Step 1: esearch for PMIDs
    search_params: dict = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
    }
    if api_key:
        search_params["api_key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(PUBMED_SEARCH_URL, params=search_params)
            resp.raise_for_status()
            search_data = resp.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        print(f"Warning: PubMed search failed: {e}", file=sys.stderr)
        return []

    id_list = search_data.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return []

    # Step 2: efetch for full details
    fetch_params: dict = {
        "db": "pubmed",
        "id": ",".join(id_list),
        "retmode": "xml",
    }
    if api_key:
        fetch_params["api_key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(PUBMED_FETCH_URL, params=fetch_params)
            resp.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        print(f"Warning: PubMed fetch failed: {e}", file=sys.stderr)
        return []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        print(f"Warning: PubMed XML parse error: {e}", file=sys.stderr)
        return []

    for article in root.findall(".//PubmedArticle"):
        pmid_elem = article.find(".//PMID")
        title_elem = article.find(".//ArticleTitle")
        if pmid_elem is None or title_elem is None:
            continue

        pmid = pmid_elem.text or ""
        title = title_elem.text or ""

        # Abstract
        abstract_parts = []
        for abs_elem in article.findall(".//AbstractText"):
            if abs_elem.text:
                abstract_parts.append(abs_elem.text)
        abstract = " ".join(abstract_parts)[:500]

        # Year
        year = ""
        year_elem = article.find(".//PubDate/Year")
        if year_elem is not None and year_elem.text:
            year = year_elem.text
        else:
            medline_year = article.find(".//PubDate/MedlineDate")
            if medline_year is not None and medline_year.text:
                match = re.search(r"(\d{4})", medline_year.text)
                if match:
                    year = match.group(1)

        # DOI
        doi = ""
        for id_elem in article.findall(".//ArticleId"):
            if id_elem.get("IdType") == "doi" and id_elem.text:
                doi = id_elem.text
                break

        # Authors
        author_names = []
        for author_elem in article.findall(".//Author"):
            last = author_elem.find("LastName")
            first = author_elem.find("ForeName")
            if last is not None and last.text:
                name = last.text
                if first is not None and first.text:
                    name = f"{last.text}, {first.text}"
                author_names.append(name)
        authors = "; ".join(author_names[:10])
        if len(author_names) > 10:
            authors += " et al."

        # Journal
        journal = ""
        journal_elem = article.find(".//Journal/Title")
        if journal_elem is not None and journal_elem.text:
            journal = journal_elem.text

        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

        # Keywords
        kw_list = []
        for kw_elem in article.findall(".//Keyword"):
            if kw_elem.text:
                kw_list.append(kw_elem.text)

        papers.append(Paper(
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            abstract=abstract,
            url=url,
            source="pubmed",
            pmid=pmid,
            journal=journal,
            external_id=pmid,
            keywords=kw_list,
        ))

    return papers


# ---------------------------------------------------------------------------
# BibTeX generation
# ---------------------------------------------------------------------------


async def fetch_bibtex_from_doi(doi: str) -> str:
    """Fetch official BibTeX from doi.org using content negotiation."""
    if not doi:
        return ""
    url = f"https://doi.org/{doi}"
    headers = {"Accept": "application/x-bibtex; charset=utf-8"}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            bib = resp.text.strip()
            if bib.startswith("@"):
                return bib
    except Exception:
        pass
    return ""


def generate_bibtex(paper: Paper) -> str:
    """Generate a BibTeX entry from a Paper object."""
    # Citation key: firstauthor_lastnameYEAR_firstword
    first_author = paper.authors.split(";")[0].strip() if paper.authors else "unknown"
    last_name = first_author.split(",")[0].strip().lower()
    last_name = re.sub(r"[^a-z]", "", last_name)
    first_word = re.sub(r"[^a-z]", "", paper.title.split()[0].lower()) if paper.title else "paper"
    cite_key = f"{last_name}{paper.year}{first_word}"

    # Format authors for BibTeX: "Last1, First1 and Last2, First2"
    bib_authors = " and ".join(
        a.strip() for a in paper.authors.split(";") if a.strip()
    )

    entry_type = "article"
    fields = []
    fields.append(f"  title={{{paper.title}}}")
    fields.append(f"  author={{{bib_authors}}}")
    if paper.journal:
        fields.append(f"  journal={{{paper.journal}}}")
    if paper.year:
        fields.append(f"  year={{{paper.year}}}")
    if paper.doi:
        fields.append(f"  doi={{{paper.doi}}}")
    if paper.url:
        fields.append(f"  url={{{paper.url}}}")

    return f"@{entry_type}{{{cite_key},\n" + ",\n".join(fields) + "\n}"


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def _normalize_title(title: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", title).lower()
    normalized = re.sub(r"[^\w\s]", "", normalized)
    return {w for w in normalized.split() if len(w) >= 3}


def _titles_similar(t1: set[str], t2: set[str], threshold: float = 0.7) -> bool:
    if not t1 or not t2:
        return False
    intersection = len(t1 & t2)
    union = len(t1 | t2)
    return (intersection / union) >= threshold if union > 0 else False


def deduplicate(papers: list[Paper]) -> list[Paper]:
    """Deduplicate papers by DOI and fuzzy title matching."""
    seen_dois: set[str] = set()
    seen_titles: list[set[str]] = []
    unique = []

    for p in papers:
        # DOI dedup
        if p.doi:
            doi_lower = p.doi.lower()
            if doi_lower in seen_dois:
                continue
            seen_dois.add(doi_lower)

        # Fuzzy title dedup
        title_words = _normalize_title(p.title)
        if any(_titles_similar(title_words, seen) for seen in seen_titles):
            continue
        seen_titles.append(title_words)
        unique.append(p)

    return unique


# ---------------------------------------------------------------------------
# Combined search
# ---------------------------------------------------------------------------


async def search_all(
    query: str,
    max_results: int = 20,
    sources: list[str] | None = None,
) -> list[Paper]:
    """Search all sources in parallel and deduplicate."""
    if sources is None:
        sources = ["openalex", "semanticscholar", "pubmed"]

    tasks = []
    if "openalex" in sources:
        tasks.append(search_openalex(query, max_results))
    if "semanticscholar" in sources:
        tasks.append(
            search_semantic_scholar(query, max_results, SEMANTIC_SCHOLAR_API_KEY)
        )
    if "pubmed" in sources:
        tasks.append(search_pubmed(query, max_results, PUBMED_API_KEY))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_papers = []
    for r in results:
        if isinstance(r, list):
            all_papers.extend(r)
        elif isinstance(r, Exception):
            print(f"Warning: Search source failed: {r}", file=sys.stderr)

    # Deduplicate
    unique = deduplicate(all_papers)

    # Sort by citation count descending, then year descending
    unique.sort(key=lambda p: (p.citation_count, int(p.year) if p.year and p.year.isdigit() else 0), reverse=True)

    return unique[:max_results]


async def search_citing(doi: str, max_results: int = 50) -> list[Paper]:
    """Find papers citing a specific DOI."""
    papers = await search_openalex_citing(doi, max_results)
    return deduplicate(papers)


async def lookup_doi(doi: str) -> Paper | None:
    """Look up a single paper by DOI using Semantic Scholar direct DOI endpoint."""
    # Use Semantic Scholar's direct DOI lookup (not search)
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
    params = {
        "fields": "paperId,title,abstract,year,url,openAccessPdf,citationCount,externalIds,authors,journal",
    }
    headers = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            paper = resp.json()
            ext_ids = paper.get("externalIds") or {}
            ss_authors = paper.get("authors") or []
            author_names = [a.get("name", "") for a in ss_authors[:10] if a.get("name")]
            authors = "; ".join(author_names)
            journal_info = paper.get("journal") or {}
            return Paper(
                title=paper.get("title", ""),
                authors=authors,
                year=str(paper.get("year", "")),
                doi=ext_ids.get("DOI", doi),
                abstract=(paper.get("abstract") or "")[:500],
                url=paper.get("url", f"https://doi.org/{doi}"),
                source="semanticscholar",
                citation_count=paper.get("citationCount", 0),
                journal=journal_info.get("name", ""),
                pmid=ext_ids.get("PubMed", ""),
                external_id=paper.get("paperId", ""),
            )
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def format_author_short(authors: str) -> str:
    """Convert 'Last, First; Last2, First2' to 'Last et al.'."""
    parts = [a.strip() for a in authors.split(";") if a.strip()]
    if not parts:
        return "Unknown"
    first = parts[0].split(",")[0].strip()
    if len(parts) == 1:
        return first
    if len(parts) == 2:
        second = parts[1].split(",")[0].strip()
        return f"{first} & {second}"
    return f"{first} et al."


def print_results(papers: list[Paper], verbose: bool = False) -> None:
    """Print papers in a readable format."""
    if not papers:
        print("No results found.")
        return

    print(f"\n{'='*80}")
    print(f"  {len(papers)} results")
    print(f"{'='*80}\n")

    for i, p in enumerate(papers, 1):
        author_short = format_author_short(p.authors)
        year_str = f" ({p.year})" if p.year else ""
        cited = f" | Cited: {p.citation_count}" if p.citation_count else ""
        doi_str = f" | DOI: {p.doi}" if p.doi else ""

        print(f"[{i}] {author_short}{year_str} {p.title}")
        print(f"    Source: {p.source}{doi_str}{cited}")
        if p.journal:
            print(f"    Journal: {p.journal}")
        print(f"    {p.url}")
        if verbose and p.abstract:
            abstract_display = p.abstract[:300]
            if len(p.abstract) > 300:
                abstract_display += "..."
            print(f"    Abstract: {abstract_display}")
        print()


async def print_bibtex(papers: list[Paper]) -> None:
    """Print BibTeX entries, fetching from DOI when possible."""
    for p in papers:
        if p.doi:
            bib = await fetch_bibtex_from_doi(p.doi)
            if bib:
                print(bib)
                print()
                continue
        # Fallback to generated BibTeX
        print(generate_bibtex(p))
        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Search academic literature across Semantic Scholar, OpenAlex, and PubMed",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s "Natural Scenes Dataset fMRI encoding"
  %(prog)s "NSD iEEG" --source pubmed
  %(prog)s "studyforrest annotation" --bibtex
  %(prog)s --citing "10.1038/s41593-021-00962-x"
  %(prog)s --doi "10.1038/s41593-021-00962-x" --bibtex
  %(prog)s --dois "10.1038/..." "10.1016/..." --bibtex
  %(prog)s --dois "10.1038/..." --append-bib refs.bib
  %(prog)s "naturalistic neuroimaging" --output results.json
""",
    )
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--source", choices=["openalex", "semanticscholar", "pubmed"],
                        help="Search only this source")
    parser.add_argument("--max", type=int, default=20, help="Max results (default: 20)")
    parser.add_argument("--bibtex", action="store_true", help="Output BibTeX entries")
    parser.add_argument("--output", "-o", help="Save results to JSON file")
    parser.add_argument("--citing", metavar="DOI",
                        help="Find papers citing this DOI")
    parser.add_argument("--doi", metavar="DOI", help="Look up a specific DOI")
    parser.add_argument("--dois", metavar="DOI", nargs="+",
                        help="Look up multiple DOIs (batch mode)")
    parser.add_argument("--append-bib", metavar="FILE",
                        help="Append BibTeX entries to a .bib file (implies --bibtex)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show abstracts in output")

    args = parser.parse_args()

    if args.append_bib:
        args.bibtex = True

    if not args.query and not args.citing and not args.doi and not args.dois:
        parser.error("Provide a query, --citing DOI, --doi DOI, or --dois DOI1 DOI2 ...")

    async def run():
        papers: list[Paper] = []

        if args.dois:
            # Batch DOI lookup
            print(f"Looking up {len(args.dois)} DOIs...", file=sys.stderr)
            tasks = [lookup_doi(d) for d in args.dois]
            results = await asyncio.gather(*tasks)
            for doi, p in zip(args.dois, results):
                if p:
                    papers.append(p)
                else:
                    print(f"  Could not find: {doi}", file=sys.stderr)
            print(f"Found {len(papers)}/{len(args.dois)} papers", file=sys.stderr)

        elif args.doi:
            # Single DOI lookup
            p = await lookup_doi(args.doi)
            if p:
                papers = [p]
            else:
                print(f"Could not find paper for DOI: {args.doi}", file=sys.stderr)
                return

        elif args.citing:
            # Citation search
            print(f"Searching for papers citing {args.citing}...", file=sys.stderr)
            papers = await search_citing(args.citing, args.max)

        else:
            # Query search
            sources = [args.source] if args.source else None
            print(f"Searching: {args.query}...", file=sys.stderr)
            papers = await search_all(args.query, args.max, sources)

        if args.append_bib:
            # Collect BibTeX and append to file
            bib_entries = []
            for p in papers:
                if p.doi:
                    bib = await fetch_bibtex_from_doi(p.doi)
                    if bib:
                        bib_entries.append(bib)
                    else:
                        bib_entries.append(generate_bibtex(p))
                else:
                    bib_entries.append(generate_bibtex(p))
            bib_text = "\n\n".join(bib_entries) + "\n"
            with open(args.append_bib, "a") as f:
                f.write("\n" + bib_text)
            print(f"Appended {len(bib_entries)} BibTeX entries to {args.append_bib}", file=sys.stderr)
            # Also print to stdout for visibility
            print(bib_text)
        elif args.output:
            # JSON output
            data = [asdict(p) for p in papers]
            Path(args.output).write_text(json.dumps(data, indent=2))
            print(f"Saved {len(papers)} results to {args.output}", file=sys.stderr)
        elif args.bibtex:
            await print_bibtex(papers)
        else:
            print_results(papers, verbose=args.verbose)

    asyncio.run(run())


if __name__ == "__main__":
    main()
