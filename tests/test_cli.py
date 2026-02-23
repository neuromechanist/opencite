"""Tests for CLI argument parsing and command dispatch."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from tests.conftest import skip_without_all_keys


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

    def test_no_command_returns_zero(self, monkeypatch):
        from opencite.cli import main

        monkeypatch.setattr("sys.argv", ["opencite"])
        result = main()
        assert result == 0

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
            [
                "batch-fetch",
                "dois.txt",
                "-o",
                "./papers",
                "--convert",
                "--concurrency",
                "5",
            ]
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

    def test_config_show(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["config", "show"])
        assert args.config_action == "show"

    def test_config_path(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["config", "path"])
        assert args.config_action == "path"

    def test_debug_and_quiet_flags(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["--debug", "--quiet", "search", "test"])
        assert args.debug is True
        assert args.quiet is True

    def test_batch_fetch_summary_flag(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(
            ["batch-fetch", "dois.txt", "--summary", "report.json"]
        )
        assert args.summary == "report.json"

    def test_convert_extract_images(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(
            [
                "convert",
                "paper.pdf",
                "--extract-images",
                "--images-dir",
                "/tmp/images",
            ]
        )
        assert args.extract_images is True
        assert args.images_dir == "/tmp/images"

    def test_pdf_filename_option(self):
        from opencite.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["pdf", "10.1234/test", "--filename", "custom.pdf"])
        assert args.filename == "custom.pdf"


class TestCmdConfig:
    def test_config_show(self, capsys):
        from opencite.cli import _cmd_config, create_parser

        parser = create_parser()
        args = parser.parse_args(["config", "show"])
        result = _cmd_config(args)
        assert result == 0
        captured = capsys.readouterr()
        assert "Resolved configuration" in captured.out

    def test_config_path(self, capsys):
        from opencite.cli import _cmd_config, create_parser

        parser = create_parser()
        args = parser.parse_args(["config", "path"])
        result = _cmd_config(args)
        assert result == 0
        captured = capsys.readouterr()
        assert "config.toml" in captured.out

    def test_config_no_subcommand(self, capsys):
        from opencite.cli import _cmd_config, create_parser

        parser = create_parser()
        args = parser.parse_args(["config"])
        result = _cmd_config(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "Usage" in captured.out

    def test_config_init(self, capsys, tmp_path, monkeypatch):
        from opencite.cli import _cmd_config, create_parser

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))

        parser = create_parser()
        args = parser.parse_args(["config", "init"])
        result = _cmd_config(args)
        assert result == 0
        captured = capsys.readouterr()
        assert "Created config file" in captured.out


class TestWriteOutput:
    def test_write_to_file(self, tmp_path, capsys):
        from opencite.cli import _write_output

        outfile = tmp_path / "output.txt"
        _write_output("hello world", str(outfile))
        assert outfile.read_text() == "hello world\n"
        captured = capsys.readouterr()
        assert "Output written to" in captured.err

    def test_write_to_stdout(self, capsys):
        from opencite.cli import _write_output

        _write_output("hello stdout", None)
        captured = capsys.readouterr()
        assert "hello stdout" in captured.out


class TestMainErrorHandling:
    def test_no_command_prints_help(self, monkeypatch):
        from opencite.cli import main

        monkeypatch.setattr("sys.argv", ["opencite"])
        result = main()
        assert result == 0

    def test_config_show_via_main(self, capsys, monkeypatch):
        """main() dispatches config show correctly."""
        from opencite.cli import main

        monkeypatch.setattr("sys.argv", ["opencite", "config", "show"])
        result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "Resolved" in captured.out

    def test_config_path_via_main(self, capsys, monkeypatch):
        """main() dispatches config path correctly."""
        from opencite.cli import main

        monkeypatch.setattr("sys.argv", ["opencite", "config", "path"])
        result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "config.toml" in captured.out

    def test_debug_flag_is_accepted(self, monkeypatch):
        """main() accepts --debug flag without crashing."""
        from opencite.cli import main

        monkeypatch.setattr("sys.argv", ["opencite", "--debug", "config", "show"])
        result = main()
        assert result == 0

    def test_config_init_via_main(self, capsys, tmp_path, monkeypatch):
        """main() dispatches config init correctly."""
        from opencite.cli import main

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
        monkeypatch.setattr("sys.argv", ["opencite", "config", "init"])
        result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "Created config file" in captured.out

    def test_convert_file_not_found(self, capsys, monkeypatch):
        """main() convert subcommand handles FileNotFoundError."""
        from opencite.cli import main

        monkeypatch.setattr(
            "sys.argv", ["opencite", "convert", "/nonexistent/paper.pdf"]
        )
        result = main()
        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_convert_to_stdout(self, capsys, tmp_path, monkeypatch):
        """main() convert subcommand outputs to stdout without -o."""
        import opencite.convert as conv
        from opencite.cli import main

        monkeypatch.setattr(conv, "convert_pdf", lambda *_a, **_kw: "# Output")

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake content")

        monkeypatch.setattr("sys.argv", ["opencite", "convert", str(pdf)])
        result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "# Output" in captured.out

    def test_convert_to_file(self, capsys, tmp_path, monkeypatch):
        """main() convert subcommand writes to file with -o."""
        import opencite.convert as conv
        from opencite.cli import main

        monkeypatch.setattr(conv, "convert_pdf", lambda *_a, **_kw: "# File Output")

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake content")
        out = tmp_path / "test.md"

        monkeypatch.setattr(
            "sys.argv", ["opencite", "convert", str(pdf), "-o", str(out)]
        )
        result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "Converted" in captured.err

    def test_batch_fetch_file_not_found(self, capsys, monkeypatch):
        """batch-fetch with nonexistent file returns error."""
        from opencite.cli import main

        monkeypatch.setattr(
            "sys.argv", ["opencite", "batch-fetch", "/nonexistent/dois.txt"]
        )
        result = main()
        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_batch_fetch_empty_file(self, capsys, tmp_path, monkeypatch):
        """batch-fetch with empty file returns 'no identifiers'."""
        from opencite.cli import main

        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        monkeypatch.setattr("sys.argv", ["opencite", "batch-fetch", str(empty_file)])
        result = main()
        assert result == 1
        captured = capsys.readouterr()
        assert "No identifiers" in captured.err

    def test_batch_fetch_invalid_json(self, capsys, tmp_path, monkeypatch):
        """batch-fetch with invalid JSON returns error."""
        from opencite.cli import main

        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{{{invalid")

        monkeypatch.setattr(
            "sys.argv", ["opencite", "batch-fetch", "--from-json", str(bad_json)]
        )
        result = main()
        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err


@pytest.mark.integration
@skip_without_all_keys
class TestCLIIntegration:
    """Integration tests that run CLI subcommands via subprocess."""

    def test_search_openalex(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "opencite",
                "search",
                "AlphaFold protein",
                "--max",
                "3",
                "--source",
                "openalex",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0

    def test_search_json_format(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "opencite",
                "search",
                "transformer",
                "--max",
                "3",
                "-f",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_lookup_doi(self):
        result = subprocess.run(
            [sys.executable, "-m", "opencite", "lookup", "10.1038/s41586-021-03819-2"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0
        assert (
            "protein" in result.stdout.lower() or "alphafold" in result.stdout.lower()
        )

    def test_canonical_search(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "opencite",
                "canonical",
                "deep learning",
                "--max",
                "3",
                "--min-citations",
                "5000",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0

    def test_cite_citing(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "opencite",
                "cite",
                "10.1038/s41586-021-03819-2",
                "--max",
                "3",
                "--direction",
                "citing",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0
