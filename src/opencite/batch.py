"""Batch PDF download and conversion pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from opencite.pdf import PDFRetriever

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    """Summary of a batch operation."""

    total: int = 0
    downloaded: int = 0
    converted: int = 0
    fulltext_retrieved: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)
    conversion_failed: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "downloaded": self.downloaded,
            "converted": self.converted,
            "fulltext_retrieved": self.fulltext_retrieved,
            "failed": [{"id": id_, "reason": reason} for id_, reason in self.failed],
            "conversion_failed": [
                {"id": id_, "reason": reason} for id_, reason in self.conversion_failed
            ],
        }


def read_ids_from_file(path: str | Path) -> list[str]:
    """Read identifiers from a text file (one per line)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {p}")
    ids = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            ids.append(line)
    return ids


def read_ids_from_json(path: str | Path) -> list[str]:
    """Read DOIs from a JSON file (search results or array of DOIs)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {p}")

    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {p}: {e}") from e

    if isinstance(data, list):
        # Array of strings (DOIs) or array of paper objects
        ids = []
        for item in data:
            if isinstance(item, str):
                ids.append(item)
            elif isinstance(item, dict):
                doi = item.get("doi") or item.get("DOI") or item.get("id", "")
                if doi:
                    ids.append(doi)
        return ids

    if isinstance(data, dict) and "papers" in data:
        # opencite search result format
        return [
            id_
            for paper in data["papers"]
            if (id_ := paper.get("doi") or paper.get("id", ""))
        ]

    raise ValueError("Unrecognized JSON format. Expected array or {papers: [...]}.")


def read_ids_from_stdin() -> list[str]:
    """Read identifiers from stdin (one per line)."""
    ids = []
    for line in sys.stdin:
        line = line.strip()
        if line and not line.startswith("#"):
            ids.append(line)
    return ids


def prepare_output_dirs(
    output_dir: str | Path, convert: bool
) -> tuple[Path, Path | None, Path | None]:
    """Create output directories for batch download.

    When convert is True, creates pdf/, markdown/, and markdown/img/
    subdirectories. When False, uses output_dir directly.

    Returns:
        Tuple of (pdf_dir, md_dir, img_dir). md_dir and img_dir are
        None when convert is False.
    """
    out = Path(output_dir)

    if convert:
        pdf_dir = out / "pdf"
        md_dir = out / "markdown"
        img_dir = md_dir / "img"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        md_dir.mkdir(parents=True, exist_ok=True)
        img_dir.mkdir(parents=True, exist_ok=True)
        return pdf_dir, md_dir, img_dir

    out.mkdir(parents=True, exist_ok=True)
    return out, None, None


async def batch_download(
    ids: list[str],
    config: Config,
    output_dir: str = "./papers",
    convert: bool = False,
    converter: str = "auto",
    concurrency: int = 3,
    prefer_fulltext: bool = True,
) -> BatchResult:
    """Download PDFs for multiple papers with controlled concurrency.

    When convert=True and prefer_fulltext=True, tries PMC full-text
    retrieval first (bypassing PDF entirely). Falls back to PDF download
    + conversion if full text is not available.

    Args:
        ids: List of DOIs or other identifiers.
        config: opencite configuration.
        output_dir: Directory to save PDFs.
        convert: Whether to also convert to markdown.
        converter: Converter to use for markdown conversion.
        concurrency: Max concurrent downloads.
        prefer_fulltext: Try PMC full-text before PDF when converting.

    Returns:
        BatchResult with summary statistics.
    """
    result = BatchResult(total=len(ids))
    semaphore = asyncio.Semaphore(concurrency)
    pdf_dir, md_dir, img_dir = prepare_output_dirs(output_dir, convert)

    # Determine if image extraction is available (mistral only)
    use_extract_images = False
    if convert:
        from opencite.convert import _pick_converter

        effective = (
            converter
            if converter != "auto"
            else _pick_converter(config.mistral_api_key)
        )
        use_extract_images = effective == "mistral"
        if not use_extract_images and img_dir is not None:
            logger.info(
                "Image extraction requires markit-mistral (MISTRAL_API_KEY). "
                "Using markitdown; images will not be extracted."
            )

    async def _process_one(identifier: str, retriever: PDFRetriever) -> None:
        async with semaphore:
            try:
                # When converting, try PMC full-text first
                if convert and prefer_fulltext and md_dir is not None:
                    md_path = await retriever.retrieve_as_markdown(
                        identifier=identifier,
                        output_dir=str(md_dir),
                        extract_images=True,
                        converter=converter,
                    )
                    if md_path:
                        result.fulltext_retrieved += 1
                        result.converted += 1
                        print(
                            f"  OK (fulltext): {identifier} -> {md_path.name}",
                            file=sys.stderr,
                        )
                        return

                # PDF-only download (or fulltext failed/disabled)
                path = await retriever.download(
                    identifier=identifier,
                    output_dir=str(pdf_dir),
                )

                if path is None:
                    result.failed.append((identifier, "no PDF source found"))
                    print(f"  FAIL: {identifier}", file=sys.stderr)
                    return

                result.downloaded += 1
                print(f"  OK: {identifier} -> {path.name}", file=sys.stderr)

                if convert and md_dir is not None:
                    try:
                        from opencite.convert import convert_pdf

                        md_out = md_dir / path.with_suffix(".md").name
                        # Per-paper image dir to avoid filename collisions
                        paper_img_dir = None
                        if use_extract_images and img_dir is not None:
                            paper_img_dir = img_dir / path.stem
                            paper_img_dir.mkdir(parents=True, exist_ok=True)

                        convert_pdf(
                            str(path),
                            output_path=str(md_out),
                            converter=converter,
                            extract_images=use_extract_images,
                            images_dir=str(paper_img_dir) if paper_img_dir else None,
                            mistral_api_key=config.mistral_api_key,
                        )
                        result.converted += 1
                    except Exception as e:
                        logger.debug(
                            "Conversion error for %s", identifier, exc_info=True
                        )
                        result.conversion_failed.append((identifier, str(e)))
                        print(
                            f"  CONVERT FAIL: {identifier} ({e})",
                            file=sys.stderr,
                        )

            except Exception as e:
                logger.debug("Batch download error for %s", identifier, exc_info=True)
                result.failed.append((identifier, str(e)))
                print(f"  FAIL: {identifier} ({e})", file=sys.stderr)

    async with PDFRetriever(config) as retriever:
        tasks = [asyncio.create_task(_process_one(id_, retriever)) for id_ in ids]
        await asyncio.gather(*tasks)

    return result
