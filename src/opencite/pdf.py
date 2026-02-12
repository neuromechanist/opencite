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

# DOI prefix -> (publisher name, API URL template, config key for token)
_PUBLISHER_MAP: dict[str, tuple[str, str, str]] = {
    "10.1016": (
        "Elsevier",
        "https://api.elsevier.com/content/article/doi/{doi}",
        "elsevier_api_key",
    ),
    "10.1002": (
        "Wiley",
        "https://api.wiley.com/onlinelibrary/tdm/v1/articles/{doi}",
        "wiley_tdm_token",
    ),
    "10.1007": (
        "Springer",
        "https://api.springernature.com/openaccess/jats/doi/{doi}",
        "springer_api_key",
    ),
    "10.1038": (
        "Springer Nature",
        "https://api.springernature.com/openaccess/jats/doi/{doi}",
        "springer_api_key",
    ),
}


class PDFRetriever:
    """Download PDFs for academic papers.

    Retrieval priority:
    1. Publisher-authenticated URLs (if tokens available)
    2. Paper's known PDF locations (OpenAlex, S2)
    3. PMC OA Service (if PMCID available or discoverable)
    4. DOI content negotiation
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
        output_path: str | None = None,
    ) -> Path | None:
        """Download the PDF for a paper.

        Args:
            identifier: DOI or other paper identifier.
            output_dir: Directory to save the PDF (used if output_path not set).
            filename: Custom filename (without path).
            paper: Pre-fetched Paper object (avoids extra lookup).
            output_path: Exact file path for output (overrides output_dir/filename).

        Returns the path to the downloaded file, or None if unavailable.
        """
        # Determine destination
        if output_path:
            dest = Path(output_path)
            if not dest.suffix:
                dest = dest.with_suffix(".pdf")
            dest.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            fname = filename or self._make_filename(paper, identifier)
            if not fname.endswith(".pdf"):
                fname += ".pdf"
            dest = out_dir / fname

        # If no paper provided, try to get PDF URLs via lookup
        if paper is None:
            paper = await self._quick_lookup(identifier)

        urls = self._collect_urls(paper, identifier)

        if not urls:
            logger.warning("No PDF URLs found for %s", identifier)
            return None

        # Try each URL, track failures
        failures: list[tuple[str, str]] = []
        for url in urls:
            logger.debug("Trying PDF URL: %s", url)
            result = await self._try_download(url, dest, failures)
            if result:
                return result

        # Report failures
        self._report_failures(identifier, failures, paper)
        return None

    async def _quick_lookup(self, identifier: str) -> Paper | None:
        """Quick lookup to get PDF locations without full enrichment."""
        from opencite.search import SearchOrchestrator

        async with SearchOrchestrator(self.config) as searcher:
            return await searcher.lookup(identifier, enrich=False)

    def _collect_urls(self, paper: Paper | None, identifier: str) -> list[str]:
        """Collect candidate PDF URLs in priority order."""
        urls: list[str] = []

        # Determine DOI for publisher lookup
        doi = paper.doi if paper else None
        if not doi:
            try:
                id_type, id_value = parse_identifier(identifier)
                if id_type == IDType.DOI:
                    doi = id_value
            except ValueError:
                pass

        # Priority 1: Publisher-authenticated URLs
        if doi:
            self._add_publisher_urls(doi, urls)

        if paper:
            # Priority 2: Known PDF locations from APIs
            for loc in paper.pdf_locations:
                if loc.url and loc.url not in urls:
                    urls.append(loc.url)

            # Priority 3: PMC URL if PMCID known
            if paper.pmcid:
                pmc_url = _PMC_OA_URL.format(pmcid=paper.pmcid)
                if pmc_url not in urls:
                    urls.append(pmc_url)

        # Priority 4: DOI content negotiation
        if doi:
            doi_url = f"https://doi.org/{doi}"
            if doi_url not in urls:
                urls.append(doi_url)

        return urls

    def _add_publisher_urls(self, doi: str, urls: list[str]) -> None:
        """Add publisher-authenticated download URLs if tokens are available."""
        prefix = doi.split("/")[0] if "/" in doi else ""
        publisher_info = _PUBLISHER_MAP.get(prefix)
        if not publisher_info:
            return

        _name, url_template, config_key = publisher_info
        token = getattr(self.config, config_key, "")
        if not token:
            return

        pub_url = url_template.format(doi=doi)
        if pub_url not in urls:
            urls.insert(0, pub_url)  # Highest priority

    async def _try_download(
        self,
        url: str,
        dest: Path,
        failures: list[tuple[str, str]],
    ) -> Path | None:
        """Try downloading a PDF from a URL."""
        headers: dict[str, str] = {}

        # Add publisher auth headers
        if "api.elsevier.com" in url:
            token = self.config.elsevier_api_key
            if token:
                headers["X-ELS-APIKey"] = token
                headers["Accept"] = "application/pdf"
        elif "api.wiley.com" in url:
            token = self.config.wiley_tdm_token
            if token:
                headers["Wiley-TDM-Client-Token"] = token
                headers["Accept"] = "application/pdf"
        elif "api.springernature.com" in url:
            token = self.config.springer_api_key
            if token:
                headers["Accept"] = "application/pdf"
                headers["X-ApiKey"] = token
        elif "doi.org" in url:
            headers["Accept"] = "application/pdf"

        try:
            async with httpx.AsyncClient(
                timeout=60.0, follow_redirects=True
            ) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "")
                if "pdf" not in content_type and resp.content[:5] != b"%PDF-":
                    failures.append((url, f"not PDF (content-type: {content_type})"))
                    return None

                dest.write_bytes(resp.content)
                logger.info("Downloaded PDF to %s (%d bytes)", dest, len(resp.content))
                return dest

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in (401, 403):
                failures.append((url, f"{status} Forbidden/Unauthorized"))
            elif status == 404:
                failures.append((url, f"{status} Not Found"))
            else:
                failures.append((url, f"HTTP {status}"))
            return None
        except httpx.TimeoutException:
            failures.append((url, "timeout"))
            return None
        except Exception as e:
            failures.append((url, str(e)))
            return None

    def _report_failures(
        self,
        identifier: str,
        failures: list[tuple[str, str]],
        paper: Paper | None,
    ) -> None:
        """Report detailed failure summary."""
        if not failures:
            logger.warning("All PDF download attempts failed for %s", identifier)
            return

        summary_parts = []
        for url, reason in failures:
            # Shorten URL for display
            short = url.split("//", 1)[-1][:60]
            summary_parts.append(f"  {short}: {reason}")

        summary = "\n".join(summary_parts)
        logger.warning(
            "PDF download failed for %s. Tried %d source(s):\n%s",
            identifier,
            len(failures),
            summary,
        )

        # Suggest institutional access
        doi = paper.doi if paper else None
        if not doi:
            try:
                id_type, id_value = parse_identifier(identifier)
                if id_type == IDType.DOI:
                    doi = id_value
            except ValueError:
                pass

        if doi:
            logger.info(
                "Paper may be available via institutional access: https://doi.org/%s",
                doi,
            )

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
