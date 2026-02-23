"""PDF to markdown conversion."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def convert_pdf(
    pdf_path: str | Path,
    output_path: str | Path | None = None,
    converter: str = "auto",
    extract_images: bool = False,
    images_dir: str | Path | None = None,
    mistral_api_key: str = "",
) -> str:
    """Convert a PDF file to markdown.

    Args:
        pdf_path: Path to the PDF file.
        output_path: Optional path for the output markdown file.
        converter: Which converter to use: "markitdown", "mistral", or "auto".
            Auto uses mistral if MISTRAL_API_KEY is set, otherwise markitdown.
        extract_images: Whether to extract images (mistral only).
        images_dir: Directory for extracted images (defaults to output_path parent).
        mistral_api_key: Mistral API key (falls back to env var).

    Returns:
        The markdown text.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if converter == "auto":
        converter = _pick_converter(mistral_api_key)

    if converter == "mistral":
        md_text = _convert_with_mistral(
            pdf_path,
            output_path=output_path,
            extract_images=extract_images,
            images_dir=images_dir,
            api_key=mistral_api_key,
        )
    else:
        md_text = _convert_with_markitdown(pdf_path)

    if output_path and not (extract_images and converter == "mistral"):
        # When extract_images with mistral, markit-mistral handles output writing
        out = Path(output_path)
        out.write_text(md_text, encoding="utf-8")
        logger.info("Markdown written to %s", out)

    return md_text


def _pick_converter(api_key: str = "") -> str:
    """Auto-select converter based on available API keys."""
    import os

    if api_key or os.environ.get("MISTRAL_API_KEY"):
        return "mistral"
    return "markitdown"


def _convert_with_markitdown(pdf_path: Path) -> str:
    """Convert using markitdown (local, free)."""
    try:
        from markitdown import MarkItDown
    except ImportError as e:
        raise ImportError(
            "markitdown is required for PDF conversion. "
            "Install with: pip install opencite"
        ) from e

    converter = MarkItDown()
    result = converter.convert(str(pdf_path))
    return result.text_content


def _convert_with_mistral(
    pdf_path: Path,
    output_path: str | Path | None = None,
    extract_images: bool = False,
    images_dir: str | Path | None = None,
    api_key: str = "",
) -> str:
    """Convert using markit-mistral (API-based, better for complex layouts)."""
    try:
        from markit_mistral import MarkItMistral
    except ImportError as e:
        raise ImportError(
            "markit-mistral>=0.2.0 is required for Mistral PDF conversion. "
            "Install with: pip install opencite"
        ) from e

    kwargs: dict[str, object] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if extract_images:
        kwargs["include_images"] = True

    converter = MarkItMistral(**kwargs)

    if extract_images and output_path:
        # Use convert_file for full output with images
        out = Path(output_path)
        output_dir = Path(images_dir) if images_dir else out.parent
        converter.convert_file(
            pdf_path,
            output_path=out,
            output_dir=output_dir,
        )
        if not out.exists():
            raise RuntimeError(
                f"Conversion produced no output for {pdf_path}. "
                "Check that the PDF is valid and the Mistral API key is correct."
            )
        return out.read_text(encoding="utf-8")

    return converter.convert(str(pdf_path))
