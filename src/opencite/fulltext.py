"""Full-text retrieval pipeline using PMC BioC API."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from opencite.clients.id_converter import IDConverterClient
from opencite.clients.pmc import PMCClient
from opencite.models import IDType, Paper, parse_identifier
from opencite.pmc_convert import bioc_to_markdown, extract_figure_files

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)


class FullTextRetriever:
    """Retrieve full-text articles from PMC and convert to markdown.

    Uses the PMC BioC API for structured article content and downloads
    figure images when available. Only works for articles in the PMC
    Open Access subset.

    Retrieval flow:
    1. Resolve PMCID (from paper metadata or ID converter)
    2. Fetch structured text via BioC API
    3. Convert BioC passages to markdown
    4. Optionally download figure images
    5. Write markdown to output file
    """

    def __init__(self, config: Config):
        self.config = config
        self._pmc = PMCClient(config)
        self._id_converter = IDConverterClient(config)

    async def __aenter__(self) -> FullTextRetriever:
        await self._pmc.__aenter__()
        await self._id_converter.__aenter__()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._id_converter.__aexit__()
        await self._pmc.__aexit__()

    async def retrieve(
        self,
        identifier: str,
        output_dir: str = ".",
        paper: Paper | None = None,
        extract_images: bool = True,
        filename: str | None = None,
    ) -> Path | None:
        """Retrieve full-text markdown for a paper from PMC.

        Args:
            identifier: DOI, PMID, PMCID, or other paper identifier.
            output_dir: Directory to save the markdown file.
            paper: Pre-fetched Paper object (avoids extra lookup).
            extract_images: Whether to download figure images.
            filename: Custom filename (without extension) for the output.

        Returns:
            Path to the markdown file, or None if full text is not available.
        """
        # Step 1: Resolve PMCID
        pmcid = self._resolve_pmcid(identifier, paper)
        if not pmcid:
            pmcid = await self._lookup_pmcid(identifier)
        if not pmcid:
            logger.debug("No PMCID found for %s; full text not available", identifier)
            return None

        # Step 2: Fetch BioC full text
        document = await self._pmc.fetch_full_text(pmcid)
        if document is None:
            logger.debug("BioC full text not available for %s", pmcid)
            return None

        # Step 3: Set up output paths
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        fname = filename or self._make_filename(paper, identifier)
        if not fname.endswith(".md"):
            fname += ".md"
        md_path = out_dir / fname

        # Step 4: Optionally download images
        images_subdir: str | None = None
        if extract_images:
            figures = extract_figure_files(document)
            if figures:
                img_dir_name = Path(fname).stem
                img_dir = out_dir / "img" / img_dir_name
                images_subdir = f"img/{img_dir_name}"
                await self._download_images(pmcid, figures, img_dir)

        # Step 5: Convert to markdown
        md_text = bioc_to_markdown(document, images_dir=images_subdir)

        # Step 6: Write output
        md_path.write_text(md_text, encoding="utf-8")
        logger.info("Full text written to %s", md_path)
        return md_path

    def _resolve_pmcid(self, identifier: str, paper: Paper | None) -> str | None:
        """Try to get PMCID from paper metadata or identifier string."""
        if paper and paper.pmcid:
            return paper.pmcid

        # Check if identifier itself is a PMCID
        try:
            id_type, id_value = parse_identifier(identifier)
            if id_type == IDType.PMCID:
                return id_value
        except ValueError:
            pass

        # Check for bare PMC format
        stripped = identifier.strip().upper()
        if stripped.startswith("PMC") and stripped[3:].isdigit():
            return stripped

        return None

    async def _lookup_pmcid(self, identifier: str) -> str | None:
        """Look up PMCID via the NCBI ID Converter."""
        try:
            id_type, id_value = parse_identifier(identifier)
        except ValueError:
            return None

        if id_type == IDType.PMCID:
            return id_value

        # Convert DOI or PMID to PMCID
        try:
            id_sets = await self._id_converter.convert([identifier])
            for ids in id_sets:
                if ids.pmcid:
                    return ids.pmcid
        except Exception as e:
            logger.debug("ID conversion failed for %s: %s", identifier, e)

        return None

    async def _download_images(
        self,
        pmcid: str,
        figures: list[tuple[str, str]],
        img_dir: Path,
    ) -> None:
        """Download figure images for an article."""
        img_dir.mkdir(parents=True, exist_ok=True)
        for _fig_id, fig_file in figures:
            dest = img_dir / fig_file
            result = await self._pmc.fetch_image(pmcid, fig_file, dest)
            if result is None:
                logger.debug("Could not download image %s for %s", fig_file, pmcid)

    def _make_filename(self, paper: Paper | None, identifier: str) -> str:
        """Generate a filename from paper metadata."""
        if paper and paper.title:
            author = ""
            if paper.authors:
                a = paper.authors[0]
                author = a.family_name or a.name.split(",")[0].strip()
                author = re.sub(r"[^\w]", "", author)

            year = paper.year_str
            words = paper.title.split()[:3]
            title_part = "_".join(re.sub(r"[^\w]", "", w) for w in words)
            parts = [p for p in [author, year, title_part] if p]
            return "_".join(parts)

        safe = re.sub(r"[^\w.-]", "_", identifier)
        return safe
