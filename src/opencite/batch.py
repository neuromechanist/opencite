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
    failed: list[tuple[str, str]] = field(default_factory=list)
    conversion_failed: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "downloaded": self.downloaded,
            "converted": self.converted,
            "failed": [{"id": id_, "reason": reason} for id_, reason in self.failed],
            "conversion_failed": [
                {"id": id_, "reason": reason}
                for id_, reason in self.conversion_failed
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


async def batch_download(
    ids: list[str],
    config: Config,
    output_dir: str = "./papers",
    convert: bool = False,
    converter: str = "auto",
    concurrency: int = 3,
) -> BatchResult:
    """Download PDFs for multiple papers with controlled concurrency.

    Args:
        ids: List of DOIs or other identifiers.
        config: opencite configuration.
        output_dir: Directory to save PDFs.
        convert: Whether to also convert to markdown.
        converter: Converter to use for markdown conversion.
        concurrency: Max concurrent downloads.

    Returns:
        BatchResult with summary statistics.
    """
    result = BatchResult(total=len(ids))
    semaphore = asyncio.Semaphore(concurrency)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    async def _process_one(
        identifier: str, retriever: PDFRetriever
    ) -> None:
        async with semaphore:
            try:
                path = await retriever.download(
                    identifier=identifier,
                    output_dir=output_dir,
                )

                if path is None:
                    result.failed.append((identifier, "no PDF source found"))
                    print(f"  FAIL: {identifier}", file=sys.stderr)
                    return

                result.downloaded += 1
                print(f"  OK: {identifier} -> {path.name}", file=sys.stderr)

                if convert:
                    try:
                        from opencite.convert import convert_pdf

                        md_out = path.with_suffix(".md")
                        convert_pdf(
                            str(path),
                            output_path=str(md_out),
                            converter=converter,
                            mistral_api_key=config.mistral_api_key,
                        )
                        result.converted += 1
                    except Exception as e:
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
        tasks = [
            asyncio.create_task(_process_one(id_, retriever)) for id_ in ids
        ]
        await asyncio.gather(*tasks)

    return result
