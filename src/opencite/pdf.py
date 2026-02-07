"""PDF retrieval pipeline."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from opencite.clients.id_converter import IDConverterClient
from opencite.models import IDType, Paper, parse_identifier

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

_PMC_OA_URL = "https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"


class PDFRetriever:
    """Download PDFs for academic papers.

    Retrieval priority:
    1. Paper's known PDF locations (OpenAlex, S2)
    2. PMC OA Service (if PMCID available or discoverable)
    3. DOI content negotiation
    """

    def __init__(self, config: Config):
        self.config = config
        self._id_converter = IDConverterClient(config)

    async def __aenter__(self) -> PDFRetriever:
        await self._id_converter.__aenter__()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._id_converter.__aexit__()

    async def download(
        self,
        identifier: str,
        output_dir: str = ".",
        filename: str | None = None,
        paper: Paper | None = None,
    ) -> Path | None:
        """Download the PDF for a paper.

        Returns the path to the downloaded file, or None if unavailable.
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # If no paper provided, try to get PDF URLs via lookup
        if paper is None:
            paper = await self._quick_lookup(identifier)

        urls = self._collect_urls(paper, identifier)

        if not urls:
            logger.warning("No PDF URLs found for %s", identifier)
            return None

        # Try each URL
        fname = filename or self._make_filename(paper, identifier)
        if not fname.endswith(".pdf"):
            fname += ".pdf"
        dest = out_dir / fname

        for url in urls:
            logger.debug("Trying PDF URL: %s", url)
            result = await self._try_download(url, dest)
            if result:
                return result

        logger.warning("All PDF download attempts failed for %s", identifier)
        return None

    async def _quick_lookup(self, identifier: str) -> Paper | None:
        """Quick lookup to get PDF locations without full enrichment."""
        from opencite.search import SearchOrchestrator

        async with SearchOrchestrator(self.config) as searcher:
            return await searcher.lookup(identifier, enrich=False)

    def _collect_urls(self, paper: Paper | None, identifier: str) -> list[str]:
        """Collect candidate PDF URLs in priority order."""
        urls: list[str] = []

        if paper:
            # Known PDF locations from APIs
            for loc in paper.pdf_locations:
                if loc.url and loc.url not in urls:
                    urls.append(loc.url)

            # PMC URL if PMCID known
            if paper.pmcid:
                pmc_url = _PMC_OA_URL.format(pmcid=paper.pmcid)
                if pmc_url not in urls:
                    urls.append(pmc_url)

            # DOI content negotiation
            if paper.doi:
                doi_url = f"https://doi.org/{paper.doi}"
                if doi_url not in urls:
                    urls.append(doi_url)
        else:
            # Fallback: try DOI content negotiation if identifier looks like DOI
            try:
                id_type, id_value = parse_identifier(identifier)
                if id_type == IDType.DOI:
                    urls.append(f"https://doi.org/{id_value}")
            except ValueError:
                pass

        return urls

    async def _try_download(self, url: str, dest: Path) -> Path | None:
        """Try downloading a PDF from a URL."""
        headers: dict[str, str] = {}
        if "doi.org" in url:
            headers["Accept"] = "application/pdf"

        try:
            async with httpx.AsyncClient(
                timeout=60.0, follow_redirects=True
            ) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "")
                if "pdf" not in content_type and resp.content[:5] != b"%PDF-":
                    logger.debug(
                        "Response is not PDF (content-type: %s)", content_type
                    )
                    return None

                dest.write_bytes(resp.content)
                logger.info("Downloaded PDF to %s (%d bytes)", dest, len(resp.content))
                return dest

        except Exception:
            logger.debug("Download failed from %s", url, exc_info=True)
            return None

    def _make_filename(self, paper: Paper | None, identifier: str) -> str:
        """Generate a filename from paper metadata."""
        if paper and paper.title:
            # first_author_year_firstwords
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

        # Fallback: sanitize identifier
        safe = re.sub(r"[^\w.-]", "_", identifier)
        return safe
