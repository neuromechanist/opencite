"""Tests for opencite.convert."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from opencite.convert import _pick_converter, convert_pdf


class TestPickConverter:
    def test_defaults_to_markitdown(self, monkeypatch):
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        assert _pick_converter() == "markitdown"

    def test_mistral_when_env_set(self, monkeypatch):
        monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
        assert _pick_converter() == "mistral"

    def test_mistral_when_api_key_passed(self, monkeypatch):
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        assert _pick_converter(api_key="explicit-key") == "mistral"

    def test_api_key_param_takes_priority(self, monkeypatch):
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        assert _pick_converter(api_key="key") == "mistral"


class TestConvertPdf:
    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="PDF not found"):
            convert_pdf("/nonexistent/paper.pdf")

    def test_markitdown_import_error(self, monkeypatch):
        """When markitdown is not installed, helpful error is raised."""
        import opencite.convert as conv

        def mock_convert(_pdf_path):
            raise ImportError("markitdown is required")

        monkeypatch.setattr(conv, "_convert_with_markitdown", mock_convert)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 fake")
            f.flush()
            with pytest.raises(ImportError, match="markitdown"):
                convert_pdf(f.name, converter="markitdown")

    def test_mistral_import_error(self, monkeypatch):
        """When markit-mistral is not installed, helpful error is raised."""
        import opencite.convert as conv

        def mock_convert(_pdf_path, **_kwargs):
            raise ImportError("markit-mistral>=0.2.0 is required")

        monkeypatch.setattr(conv, "_convert_with_mistral", mock_convert)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 fake")
            f.flush()
            with pytest.raises(ImportError, match="markit-mistral"):
                convert_pdf(f.name, converter="mistral")

    def test_auto_selects_markitdown_without_key(self, monkeypatch):
        """Auto mode selects markitdown when no Mistral key available."""
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        import opencite.convert as conv

        called_with = {}

        def mock_markitdown(_pdf_path):
            called_with["converter"] = "markitdown"
            return "# Mock output"

        monkeypatch.setattr(conv, "_convert_with_markitdown", mock_markitdown)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 fake")
            f.flush()
            result = convert_pdf(f.name, converter="auto")

        assert called_with["converter"] == "markitdown"
        assert result == "# Mock output"

    def test_output_written_to_file(self, monkeypatch):
        """Output is written to file when output_path specified."""
        import opencite.convert as conv

        monkeypatch.setattr(conv, "_convert_with_markitdown", lambda _p: "# Content")

        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "test.pdf"
            pdf.write_bytes(b"%PDF-1.4 fake")
            out = Path(tmp) / "test.md"

            convert_pdf(str(pdf), output_path=str(out), converter="markitdown")

            assert out.exists()
            assert out.read_text() == "# Content"
