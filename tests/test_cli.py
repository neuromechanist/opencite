"""Tests for CLI argument parsing and command dispatch."""

from __future__ import annotations

import subprocess
import sys


class TestCLIVersion:
    def test_version_flag(self):
        result = subprocess.run(
            [sys.executable, "-m", "opencite", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "opencite" in result.stdout

    def test_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "opencite", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "search" in result.stdout
        assert "lookup" in result.stdout
        assert "cite" in result.stdout
        assert "pdf" in result.stdout
        assert "convert" in result.stdout
        assert "ids" in result.stdout


class TestCLIArgParsing:
    def test_search_parser(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["search", "fMRI encoding", "--max", "5"])
        assert args.command == "search"
        assert args.query == "fMRI encoding"
        assert args.max == 5
        assert args.source == "all"
        assert args.format == "text"

    def test_search_all_options(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(
            [
                "search",
                "query",
                "--source",
                "openalex",
                "--max",
                "10",
                "--year-from",
                "2020",
                "--year-to",
                "2024",
                "--oa-only",
                "--sort",
                "citations",
                "-f",
                "json",
                "-o",
                "out.json",
                "-v",
            ]
        )
        assert args.source == "openalex"
        assert args.year_from == 2020
        assert args.year_to == 2024
        assert args.oa_only is True
        assert args.sort == "citations"
        assert args.format == "json"
        assert args.output == "out.json"
        assert args.verbose is True

    def test_lookup_parser(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["lookup", "10.1234/test"])
        assert args.command == "lookup"
        assert args.id == ["10.1234/test"]
        assert args.enrich is False

    def test_lookup_multiple_ids(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["lookup", "10.1234/a", "pmid:123", "--enrich"])
        assert args.id == ["10.1234/a", "pmid:123"]
        assert args.enrich is True

    def test_lookup_append_bib(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["lookup", "10.1234/test", "--append-bib", "refs.bib"])
        assert args.append_bib == "refs.bib"

    def test_cite_parser(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["cite", "10.1234/test", "--direction", "both"])
        assert args.command == "cite"
        assert args.id == "10.1234/test"
        assert args.direction == "both"

    def test_canonical_parser(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(
            [
                "canonical",
                "deep learning",
                "--max",
                "5",
                "--min-citations",
                "500",
            ]
        )
        assert args.command == "canonical"
        assert args.query == "deep learning"
        assert args.max == 5
        assert args.min_citations == 500

    def test_pdf_parser(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(
            [
                "pdf",
                "10.1234/test",
                "-o",
                "/tmp/papers",
                "--convert",
                "--converter",
                "mistral",
            ]
        )
        assert args.command == "pdf"
        assert args.id == "10.1234/test"
        assert args.output == "/tmp/papers"
        assert args.convert is True
        assert args.converter == "mistral"

    def test_convert_parser(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["convert", "paper.pdf", "-o", "paper.md"])
        assert args.command == "convert"
        assert args.file == "paper.pdf"
        assert args.output == "paper.md"

    def test_ids_parser(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["ids", "12345", "PMC67890", "-f", "json"])
        assert args.command == "ids"
        assert args.id == ["12345", "PMC67890"]
        assert args.format == "json"

    def test_no_command_returns_zero(self):
        from opencite.cli import main

        sys_argv_backup = sys.argv
        sys.argv = ["opencite"]
        try:
            result = main()
            assert result == 0
        finally:
            sys.argv = sys_argv_backup

    def test_bibtex_format_in_search(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["search", "test", "-f", "bibtex"])
        assert args.format == "bibtex"

    def test_csv_format_in_search(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["search", "test", "-f", "csv"])
        assert args.format == "csv"

    def test_batch_fetch_parser_file(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(
            ["batch-fetch", "dois.txt", "-o", "./papers", "--convert", "--concurrency", "5"]
        )
        assert args.command == "batch-fetch"
        assert args.file == "dois.txt"
        assert args.output_dir == "./papers"
        assert args.convert is True
        assert args.concurrency == 5

    def test_batch_fetch_parser_json(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["batch-fetch", "--from-json", "results.json"])
        assert args.from_json == "results.json"
        assert args.file is None

    def test_batch_fetch_parser_stdin(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["batch-fetch", "--from-stdin"])
        assert args.from_stdin is True

    def test_config_parser(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["config", "init"])
        assert args.command == "config"
        assert args.config_action == "init"
