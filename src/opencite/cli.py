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
        choices=[
            "openalex",
            "s2",
            "pubmed",
            "arxiv",
            "biorxiv",
            "medrxiv",
            "crossref",
            "core",
            "all",
        ],
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
    pdf_p.add_argument(
        "-o",
        "--output",
        default=".",
        metavar="PATH",
        help="output file path (.pdf) or directory (default: .)",
    )
    pdf_p.add_argument("--filename", metavar="NAME", help="custom filename")
    pdf_p.add_argument(
        "--convert", action="store_true", help="also convert to markdown"
    )
    pdf_p.add_argument(
        "--converter",
        choices=["markitdown", "mistral", "auto"],
        default="auto",
    )
    pdf_p.add_argument(
        "--no-fulltext",
        action="store_true",
        help="skip PMC full-text retrieval, force PDF download",
    )

    # -- convert --
    convert_p = subparsers.add_parser("convert", help="convert a PDF to markdown")
    convert_p.add_argument("file", help="path to PDF file")
    convert_p.add_argument(
        "-o", "--output", metavar="FILE", help="output markdown file"
    )
    convert_p.add_argument(
        "--converter",
        choices=["markitdown", "mistral", "auto"],
        default="auto",
    )
    convert_p.add_argument(
        "--extract-images",
        action="store_true",
        help="extract images from PDF (mistral only)",
    )
    convert_p.add_argument(
        "--images-dir", metavar="DIR", help="directory for extracted images"
    )

    # -- ids --
    ids_p = subparsers.add_parser("ids", help="convert between PMID, PMCID, and DOI")
    ids_p.add_argument("id", nargs="+", help="identifiers to convert")
    ids_p.add_argument("-f", "--format", choices=["text", "json"], default="text")

    # -- batch-fetch --
    batch_p = subparsers.add_parser(
        "batch-fetch", help="download PDFs for multiple papers"
    )
    batch_input = batch_p.add_mutually_exclusive_group(required=True)
    batch_input.add_argument(
        "file", nargs="?", help="text file with IDs (one per line)"
    )
    batch_input.add_argument(
        "--from-json", metavar="FILE", help="JSON file with DOIs or search results"
    )
    batch_input.add_argument(
        "--from-stdin", action="store_true", help="read IDs from stdin"
    )
    batch_p.add_argument(
        "-o", "--output-dir", default="./papers", metavar="DIR", help="output directory"
    )
    batch_p.add_argument(
        "--convert", action="store_true", help="also convert PDFs to markdown"
    )
    batch_p.add_argument(
        "--converter",
        choices=["markitdown", "mistral", "auto"],
        default="auto",
    )
    batch_p.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="max concurrent downloads (default: 3)",
    )
    batch_p.add_argument(
        "--summary", metavar="FILE", help="write JSON summary report to file"
    )
    batch_p.add_argument(
        "--no-fulltext",
        action="store_true",
        help="skip PMC full-text retrieval, force PDF download",
    )

    # -- config --
    config_p = subparsers.add_parser("config", help="manage opencite configuration")
    config_sub = config_p.add_subparsers(dest="config_action")
    config_sub.add_parser("init", help="create default ~/.opencite/config.toml")
    config_sub.add_parser("show", help="show resolved configuration")
    config_sub.add_parser("path", help="show config file location")

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

    # Config command doesn't need full config loading
    if args.command == "config":
        return _cmd_config(args)

    dispatch = {
        "search": _cmd_search,
        "lookup": _cmd_lookup,
        "cite": _cmd_cite,
        "canonical": _cmd_canonical,
        "ids": _cmd_ids,
        "pdf": _cmd_pdf,
        "convert": _cmd_convert,
        "batch-fetch": _cmd_batch_fetch,
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

    if args.append_bib:
        from opencite.bibtex import generate_bibtex

        entries = []
        for p in papers:
            entries.append(p._bibtex if p._bibtex else generate_bibtex(p))
        with open(args.append_bib, "a") as f:
            f.write("\n\n")
            f.write("\n\n".join(entries))
            f.write("\n")
        print(f"BibTeX appended to {args.append_bib}", file=sys.stderr)

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
                args.id,
                max_results=args.max,
                sort=args.sort,
                min_citations=args.min_citations,
            )
            refs = await explorer.references(args.id, max_results=args.max)
            papers = citing.papers + refs.papers
        elif args.direction == "references":
            result = await explorer.references(args.id, max_results=args.max)
            papers = result.papers
        else:
            result = await explorer.citing_papers(
                args.id,
                max_results=args.max,
                sort=args.sort,
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
            {"doi": ids.doi, "pmid": ids.pmid, "pmcid": ids.pmcid} for ids in id_sets
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


async def _cmd_pdf(args: argparse.Namespace, config: object) -> int:
    """Handle the 'pdf' subcommand."""
    from opencite.config import Config
    from opencite.pdf import PDFRetriever

    assert isinstance(config, Config)

    # Determine if -o is a file path or directory
    output_val = args.output
    output_path = None
    output_dir = "."
    if output_val.endswith(".pdf"):
        output_path = output_val
    else:
        output_dir = output_val

    # When --convert is used and --no-fulltext is not set, try PMC full-text
    # first then fall back to PDF download + convert (all handled inside
    # retrieve_as_markdown).
    if args.convert and not args.no_fulltext:
        async with PDFRetriever(config) as retriever:
            md_path = await retriever.retrieve_as_markdown(
                identifier=args.id,
                output_dir=output_dir,
                extract_images=True,
                converter=args.converter,
                filename=args.filename,
            )
        if md_path:
            print(f"Retrieved: {md_path}", file=sys.stderr)
            return 0
        print("Could not retrieve full text or PDF.", file=sys.stderr)
        return 1

    # PDF-only download (no conversion, or --no-fulltext with conversion)
    async with PDFRetriever(config) as retriever:
        path = await retriever.download(
            identifier=args.id,
            output_dir=output_dir,
            filename=args.filename,
            output_path=output_path,
        )

    if path is None:
        print("Could not download PDF.", file=sys.stderr)
        return 1

    print(f"Downloaded: {path}", file=sys.stderr)

    if args.convert:
        from opencite.convert import convert_pdf

        md_out = path.with_suffix(".md")
        try:
            convert_pdf(
                str(path),
                output_path=str(md_out),
                converter=args.converter,
                mistral_api_key=config.mistral_api_key,
            )
            print(f"Converted: {md_out}", file=sys.stderr)
        except Exception as e:
            print(f"Conversion failed: {e}", file=sys.stderr)
            return 1

    return 0


async def _cmd_convert(args: argparse.Namespace, config: object) -> int:
    """Handle the 'convert' subcommand."""
    from opencite.config import Config
    from opencite.convert import convert_pdf

    assert isinstance(config, Config)

    output_path = args.output
    try:
        md_text = convert_pdf(
            args.file,
            output_path=output_path,
            converter=args.converter,
            extract_images=args.extract_images,
            images_dir=args.images_dir,
            mistral_api_key=config.mistral_api_key,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ImportError as e:
        print(f"Missing dependency: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Conversion failed: {e}", file=sys.stderr)
        return 1

    if not output_path:
        print(md_text)
    else:
        print(f"Converted: {output_path}", file=sys.stderr)

    return 0


async def _cmd_batch_fetch(args: argparse.Namespace, config: object) -> int:
    """Handle the 'batch-fetch' subcommand."""
    import json

    from opencite.batch import (
        batch_download,
        read_ids_from_file,
        read_ids_from_json,
        read_ids_from_stdin,
    )
    from opencite.config import Config

    assert isinstance(config, Config)

    # Read identifiers from the specified source
    try:
        if args.from_stdin:
            ids = read_ids_from_stdin()
        elif args.from_json:
            ids = read_ids_from_json(args.from_json)
        else:
            ids = read_ids_from_file(args.file)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not ids:
        print("No identifiers provided.", file=sys.stderr)
        return 1

    print(f"Batch downloading {len(ids)} paper(s)...", file=sys.stderr)

    result = await batch_download(
        ids=ids,
        config=config,
        output_dir=args.output_dir,
        convert=args.convert,
        converter=args.converter,
        concurrency=args.concurrency,
        prefer_fulltext=not args.no_fulltext,
    )

    # Print summary
    total_ok = result.downloaded + result.fulltext_retrieved
    print(
        f"\nDone: {total_ok}/{result.total} retrieved",
        file=sys.stderr,
        end="",
    )
    if result.fulltext_retrieved:
        print(
            f" ({result.fulltext_retrieved} via PMC full text,"
            f" {result.downloaded} via PDF)",
            file=sys.stderr,
            end="",
        )
    if args.convert:
        print(f", {result.converted} converted", file=sys.stderr, end="")
    if result.conversion_failed:
        print(
            f", {len(result.conversion_failed)} conversion(s) failed",
            file=sys.stderr,
            end="",
        )
    if result.failed:
        print(f", {len(result.failed)} failed", file=sys.stderr)
    else:
        print(file=sys.stderr)

    # Write summary report if requested
    if args.summary:
        summary_path = args.summary
        try:
            with open(summary_path, "w") as f:
                json.dump(result.to_dict(), f, indent=2)
            print(f"Summary written to {summary_path}", file=sys.stderr)
        except OSError as e:
            print(
                f"Warning: could not write summary to {summary_path}: {e}",
                file=sys.stderr,
            )

    return 1 if result.failed else 0


def _cmd_config(args: argparse.Namespace) -> int:
    """Handle the 'config' subcommand (sync, no async needed)."""
    from opencite.config import Config, _resolve_config_path, create_default_config

    if args.config_action == "init":
        path = create_default_config()
        print(f"Created config file: {path}")
        print("Edit it to add your API keys.")
        return 0

    if args.config_action == "show":
        config = Config.from_env()
        print("Resolved configuration:")
        print(config.show())
        return 0

    if args.config_action == "path":
        print(_resolve_config_path())
        return 0

    # No subcommand given
    print("Usage: opencite config {init,show,path}")
    return 1


def _write_output(output: str, filepath: str | None) -> None:
    """Write output to file or stdout."""
    if filepath:
        with open(filepath, "w") as f:
            f.write(output)
            f.write("\n")
        print(f"Output written to {filepath}", file=sys.stderr)
    else:
        print(output)
