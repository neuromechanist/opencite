"""Command-line interface for opencite."""

from __future__ import annotations

import argparse
import sys

from opencite import __version__


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="opencite",
        description="Academic literature search, citation management, and PDF retrieval",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="suppress progress messages"
    )
    parser.add_argument("--debug", action="store_true", help="enable debug logging")

    subparsers = parser.add_subparsers(dest="command")

    # -- search --
    search_p = subparsers.add_parser("search", help="search for papers by keywords")
    search_p.add_argument("query", help="search query string")
    search_p.add_argument(
        "--source",
        choices=["openalex", "s2", "pubmed", "all"],
        default="all",
        help="search source (default: all)",
    )
    search_p.add_argument(
        "--max", type=int, default=20, help="max results (default: 20)"
    )
    search_p.add_argument(
        "--year-from", type=int, metavar="YYYY", help="published after"
    )
    search_p.add_argument(
        "--year-to", type=int, metavar="YYYY", help="published before"
    )
    search_p.add_argument("--oa-only", action="store_true", help="open access only")
    search_p.add_argument(
        "--sort",
        choices=["citations", "year", "relevance"],
        default="relevance",
        help="sort order (default: relevance)",
    )
    search_p.add_argument(
        "-f",
        "--format",
        choices=["text", "json", "bibtex", "csv"],
        default="text",
        help="output format (default: text)",
    )
    search_p.add_argument("-o", "--output", metavar="FILE", help="write output to file")
    search_p.add_argument("-v", "--verbose", action="store_true", help="show abstracts")

    # -- lookup --
    lookup_p = subparsers.add_parser(
        "lookup", help="look up papers by DOI, PMID, or other ID"
    )
    lookup_p.add_argument("id", nargs="+", help="DOI, pmid:X, pmc:X, arxiv:X, or S2 ID")
    lookup_p.add_argument(
        "-f",
        "--format",
        choices=["text", "json", "bibtex"],
        default="text",
    )
    lookup_p.add_argument("-o", "--output", metavar="FILE")
    lookup_p.add_argument("--enrich", action="store_true", help="fetch from all APIs")
    lookup_p.add_argument(
        "--append-bib", metavar="FILE", help="append BibTeX to .bib file"
    )
    lookup_p.add_argument("-v", "--verbose", action="store_true")

    # -- cite --
    cite_p = subparsers.add_parser(
        "cite", help="citation graph: papers citing or cited by a paper"
    )
    cite_p.add_argument("id", help="DOI or other identifier of the seed paper")
    cite_p.add_argument(
        "--direction",
        choices=["citing", "references", "both"],
        default="citing",
    )
    cite_p.add_argument("--max", type=int, default=50)
    cite_p.add_argument("--sort", choices=["citations", "year"], default="citations")
    cite_p.add_argument("--min-citations", type=int, default=0)
    cite_p.add_argument(
        "-f", "--format", choices=["text", "json", "bibtex"], default="text"
    )
    cite_p.add_argument("-o", "--output", metavar="FILE")
    cite_p.add_argument("-v", "--verbose", action="store_true")

    # -- canonical --
    canon_p = subparsers.add_parser(
        "canonical", help="find the most-cited papers in a field"
    )
    canon_p.add_argument("query", help="topic or field description")
    canon_p.add_argument("--max", type=int, default=10)
    canon_p.add_argument("--year-from", type=int, metavar="YYYY")
    canon_p.add_argument("--min-citations", type=int, default=100)
    canon_p.add_argument(
        "-f", "--format", choices=["text", "json", "bibtex"], default="text"
    )
    canon_p.add_argument("-o", "--output", metavar="FILE")
    canon_p.add_argument("-v", "--verbose", action="store_true")

    # -- pdf --
    pdf_p = subparsers.add_parser("pdf", help="download PDF for a paper")
    pdf_p.add_argument("id", help="DOI or other identifier")
    pdf_p.add_argument("-o", "--output-dir", default=".", metavar="DIR")
    pdf_p.add_argument("--filename", metavar="NAME", help="custom filename")
    pdf_p.add_argument(
        "--convert", action="store_true", help="also convert to markdown"
    )
    pdf_p.add_argument(
        "--converter",
        choices=["markitdown", "mistral", "auto"],
        default="auto",
    )

    # -- convert --
    convert_p = subparsers.add_parser("convert", help="convert a PDF to markdown")
    convert_p.add_argument("file", help="path to PDF file")
    convert_p.add_argument(
        "-o", "--output", metavar="FILE", help="output markdown file"
    )
    convert_p.add_argument(
        "--converter",
        choices=["markitdown", "mistral"],
        default="markitdown",
    )

    # -- ids --
    ids_p = subparsers.add_parser("ids", help="convert between PMID, PMCID, and DOI")
    ids_p.add_argument("id", nargs="+", help="identifiers to convert")
    ids_p.add_argument("-f", "--format", choices=["text", "json"], default="text")

    return parser


def main() -> int:
    """Main entry point for the opencite CLI."""
    parser = create_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    # Commands will be dispatched here in Phase 4
    print(f"Command '{args.command}' not yet implemented.", file=sys.stderr)
    return 1
