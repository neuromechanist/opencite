"""PDF to markdown conversion."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def convert_pdf(
    pdf_path: str | Path,
    output_path: str | Path | None = None,
    converter: str = "auto",
) -> str:
    """Convert a PDF file to markdown.

    Args:
        pdf_path: Path to the PDF file.
        output_path: Optional path for the output markdown file.
        converter: Which converter to use: "markitdown", "mistral", or "auto".
            Auto uses mistral if MISTRAL_API_KEY is set, otherwise markitdown.

    Returns:
        The markdown text.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if converter == "auto":
        converter = _pick_converter()

    if converter == "mistral":
        md_text = _convert_with_mistral(pdf_path)
    else:
        md_text = _convert_with_markitdown(pdf_path)

    if output_path:
        out = Path(output_path)
        out.write_text(md_text, encoding="utf-8")
        logger.info("Markdown written to %s", out)

    return md_text


def _pick_converter() -> str:
    """Auto-select converter based on available API keys."""
    import os

    if os.environ.get("MISTRAL_API_KEY"):
        return "mistral"
    return "markitdown"


def _convert_with_markitdown(pdf_path: Path) -> str:
    """Convert using markitdown (local, free)."""
    try:
        from markitdown import MarkItDown
    except ImportError as e:
        raise ImportError(
            "markitdown is required for PDF conversion. "
            "Install with: uv pip install opencite[convert]"
        ) from e

    converter = MarkItDown()
    result = converter.convert(str(pdf_path))
    return result.text_content


def _convert_with_mistral(pdf_path: Path) -> str:
    """Convert using markit-mistral (API-based, better for complex layouts)."""
    try:
        from markit_mistral import MarkitMistral
    except ImportError as e:
        raise ImportError(
            "markit-mistral is required for Mistral PDF conversion. "
            "Install with: uv pip install opencite[convert]"
        ) from e

    converter = MarkitMistral()
    return converter.convert(str(pdf_path))
