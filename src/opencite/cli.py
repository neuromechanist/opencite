"""Command-line interface for opencite."""

from __future__ import annotations

import argparse
import asyncio
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

    from opencite.config import Config

    config = Config.from_env()

    if args.debug:
        config = Config.from_env()
        config.log_level = "DEBUG"
    config.setup_logging()

    dispatch = {
        "search": _cmd_search,
        "lookup": _cmd_lookup,
        "cite": _cmd_cite,
        "canonical": _cmd_canonical,
        "ids": _cmd_ids,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        print(f"Command '{args.command}' not yet implemented.", file=sys.stderr)
        return 1

    try:
        return asyncio.run(handler(args, config))
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        if args.debug:
            raise
        print(f"Error: {e}", file=sys.stderr)
        return 1


async def _cmd_search(args: argparse.Namespace, config: object) -> int:
    """Handle the 'search' subcommand."""
    from opencite.config import Config
    from opencite.formatters import get_formatter
    from opencite.search import SearchOrchestrator

    assert isinstance(config, Config)

    sources = None
    if args.source != "all":
        sources = [args.source]

    async with SearchOrchestrator(config) as searcher:
        result = await searcher.search(
            query=args.query,
            max_results=args.max,
            sources=sources,
            year_from=args.year_from,
            year_to=args.year_to,
            oa_only=args.oa_only,
            sort=args.sort,
        )

    formatter = get_formatter(args.format)
    output = formatter.format_papers(result.papers, verbose=args.verbose)

    if not args.quiet and args.format == "text":
        dedup_msg = ""
        if result.deduplicated_count > 0:
            dedup_msg = f" ({result.deduplicated_count} duplicates removed)"
        source_info = ", ".join(
            f"{k}: {v}" for k, v in sorted(result.total_by_source.items())
        )
        print(f"Sources: {source_info}{dedup_msg}", file=sys.stderr)

    _write_output(output, args.output)
    return 0


async def _cmd_lookup(args: argparse.Namespace, config: object) -> int:
    """Handle the 'lookup' subcommand."""
    from opencite.config import Config
    from opencite.formatters import get_formatter
    from opencite.search import SearchOrchestrator

    assert isinstance(config, Config)

    async with SearchOrchestrator(config) as searcher:
        if len(args.id) == 1:
            paper = await searcher.lookup(args.id[0], enrich=args.enrich)
            if paper is None:
                print(f"Paper not found: {args.id[0]}", file=sys.stderr)
                return 1
            papers = [paper]
        else:
            papers = await searcher.batch_lookup(args.id, enrich=args.enrich)
            if not papers:
                print("No papers found.", file=sys.stderr)
                return 1

    formatter = get_formatter(args.format)
    output = formatter.format_papers(papers, verbose=args.verbose)
    _write_output(output, args.output)
    return 0


async def _cmd_cite(args: argparse.Namespace, config: object) -> int:
    """Handle the 'cite' subcommand."""
    from opencite.citations import CitationExplorer
    from opencite.config import Config
    from opencite.formatters import get_formatter

    assert isinstance(config, Config)

    async with CitationExplorer(config) as explorer:
        if args.direction == "both":
            citing = await explorer.citing_papers(
                args.id, max_results=args.max, sort=args.sort,
                min_citations=args.min_citations,
            )
            refs = await explorer.references(args.id, max_results=args.max)
            papers = citing.papers + refs.papers
        elif args.direction == "references":
            result = await explorer.references(args.id, max_results=args.max)
            papers = result.papers
        else:
            result = await explorer.citing_papers(
                args.id, max_results=args.max, sort=args.sort,
                min_citations=args.min_citations,
            )
            papers = result.papers

    formatter = get_formatter(args.format)
    output = formatter.format_papers(papers, verbose=args.verbose)
    _write_output(output, args.output)
    return 0


async def _cmd_canonical(args: argparse.Namespace, config: object) -> int:
    """Handle the 'canonical' subcommand."""
    from opencite.citations import CitationExplorer
    from opencite.config import Config
    from opencite.formatters import get_formatter

    assert isinstance(config, Config)

    async with CitationExplorer(config) as explorer:
        papers = await explorer.canonical_papers(
            query=args.query,
            max_results=args.max,
            year_from=args.year_from,
            min_citations=args.min_citations,
        )

    formatter = get_formatter(args.format)
    output = formatter.format_papers(papers, verbose=args.verbose)
    _write_output(output, args.output)
    return 0


async def _cmd_ids(args: argparse.Namespace, config: object) -> int:
    """Handle the 'ids' subcommand."""
    import json

    from opencite.clients.id_converter import IDConverterClient
    from opencite.config import Config

    assert isinstance(config, Config)

    async with IDConverterClient(config) as converter:
        id_sets = await converter.convert(args.id)

    if not id_sets:
        print("No IDs could be resolved.", file=sys.stderr)
        return 1

    if args.format == "json":
        data = [
            {"doi": ids.doi, "pmid": ids.pmid, "pmcid": ids.pmcid}
            for ids in id_sets
        ]
        print(json.dumps(data, indent=2))
    else:
        for ids in id_sets:
            parts = []
            if ids.doi:
                parts.append(f"DOI: {ids.doi}")
            if ids.pmid:
                parts.append(f"PMID: {ids.pmid}")
            if ids.pmcid:
                parts.append(f"PMCID: {ids.pmcid}")
            print(" | ".join(parts))

    return 0


def _write_output(output: str, filepath: str | None) -> None:
    """Write output to file or stdout."""
    if filepath:
        with open(filepath, "w") as f:
            f.write(output)
            f.write("\n")
        print(f"Output written to {filepath}", file=sys.stderr)
    else:
        print(output)
