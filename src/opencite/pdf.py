"""PDF retrieval pipeline."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from opencite.clients.id_converter import IDConverterClient
from opencite.clients.unpaywall import UnpaywallClient
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

# Known DOI prefixes and their publishers -- used for informational hints
# when PDF retrieval fails, to guide users toward the right access method.
# Sources: CrossRef prefix registry.
PUBLISHER_INFO: dict[str, str] = {
    # Publishers with authenticated API access (see _PUBLISHER_MAP above)
    "10.1016": "Elsevier/ScienceDirect (set elsevier_api_key for TDM access)",
    "10.1002": "Wiley (set wiley_tdm_token for TDM access)",
    "10.1007": "Springer (set springer_api_key for OA access)",
    "10.1038": "Springer Nature (set springer_api_key for OA access)",
    # Major publishers without direct API -- rely on Unpaywall, OA repos, or DOI
    "10.1109": "IEEE (PDFs often via Unpaywall or institutional access)",
    "10.1145": "ACM (PDFs often via Unpaywall or ACM Open TOC)",
    "10.1126": "Science/AAAS (PDFs via Unpaywall or institutional access)",
    "10.1093": "Oxford University Press (check Unpaywall for OA copies)",
    "10.1080": "Taylor & Francis (check Unpaywall for OA copies)",
    "10.1177": "SAGE Publications (check Unpaywall for OA copies)",
    "10.1371": "PLOS (open access -- should always have free PDF)",
    "10.3389": "Frontiers (open access -- should always have free PDF)",
    "10.7554": "eLife (open access -- should always have free PDF)",
    "10.1523": "J. Neuroscience (check Unpaywall, many are OA after embargo)",
    "10.1101": "bioRxiv/medRxiv (always open access)",
    "10.48550": "arXiv (always open access)",
    "10.1136": "BMJ (check Unpaywall for OA copies)",
    "10.1001": "JAMA Network (check Unpaywall for OA copies)",
    "10.1056": "NEJM (check Unpaywall for OA copies)",
    "10.1161": "AHA Journals (check Unpaywall for OA copies)",
    "10.1073": "PNAS (OA after 6 months, check Unpaywall)",
    "10.1172": "JCI (open access)",
    "10.1242": "Company of Biologists (check Unpaywall for OA copies)",
    "10.1113": "J. Physiology (check Unpaywall for OA copies)",
}


class PDFRetriever:
    """Download PDFs for academic papers.

    Retrieval priority:
    1. Publisher-authenticated URLs (if tokens available)
    2. Paper's known PDF locations (OpenAlex, S2)
    3. Direct arXiv/bioRxiv/medRxiv PDF URLs
    4. PMC OA Service (if PMCID available or discoverable)
    5. DOI content negotiation

    When the caller wants markdown (retrieve_as_markdown), the retriever
    first tries PMC full-text retrieval to skip the PDF step entirely.
    """

    def __init__(self, config: Config):
        self.config = config
        self._id_converter = IDConverterClient(config)
        self._unpaywall = UnpaywallClient(config)

    async def __aenter__(self) -> PDFRetriever:
        await self._id_converter.__aenter__()
        await self._unpaywall.__aenter__()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._id_converter.__aexit__()
        await self._unpaywall.__aexit__()

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

        urls = await self._collect_urls(paper, identifier)

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

    async def _collect_urls(self, paper: Paper | None, identifier: str) -> list[str]:
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

            # Priority 3a: Direct arXiv PDF (always works for OA preprints)
            arxiv_id = paper.ids.arxiv_id
            if arxiv_id:
                arxiv_pdf = f"https://arxiv.org/pdf/{arxiv_id}"
                if arxiv_pdf not in urls:
                    urls.append(arxiv_pdf)

            # Priority 3b: PMC URL if PMCID known
            if paper.pmcid:
                pmc_url = _PMC_OA_URL.format(pmcid=paper.pmcid)
                if pmc_url not in urls:
                    urls.append(pmc_url)

        # Priority 4: Unpaywall -- finds OA copies across 50k+ repositories
        if doi:
            try:
                unpaywall_locs = await self._unpaywall.lookup_doi(doi)
                for loc in unpaywall_locs:
                    if loc.url and loc.url not in urls:
                        urls.append(loc.url)
            except Exception as e:
                logger.debug("Unpaywall lookup failed for %s: %s", doi, e)

        # Priority 5a: Direct bioRxiv/medRxiv PDF for 10.1101/ DOIs
        if doi and doi.startswith("10.1101/"):
            preprint_server = "biorxiv"
            if paper and (
                "medrxiv" in paper.data_sources
                or (paper.source_venue and "medrxiv" in paper.source_venue.name.lower())
            ):
                preprint_server = "medrxiv"
            preprint_pdf = f"https://www.{preprint_server}.org/content/{doi}v1.full.pdf"
            if preprint_pdf not in urls:
                urls.append(preprint_pdf)

        # Priority 5b: DOI content negotiation
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
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
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
        """Report detailed failure summary.

        Uses print() to stderr for user-visible messages so failures
        are always reported regardless of log level (fixes #21).
        """
        import sys

        if not failures:
            print(
                f"PDF download failed for {identifier}: no sources attempted.",
                file=sys.stderr,
            )
            return

        summary_parts = []
        for url, reason in failures:
            # Shorten URL for display
            short = url.split("//", 1)[-1][:60]
            summary_parts.append(f"  {short}: {reason}")

        summary = "\n".join(summary_parts)
        print(
            f"PDF download failed for {identifier}. "
            f"Tried {len(failures)} source(s):\n{summary}",
            file=sys.stderr,
        )

        # Suggest institutional access and Unpaywall
        doi = paper.doi if paper else None
        if not doi:
            try:
                id_type, id_value = parse_identifier(identifier)
                if id_type == IDType.DOI:
                    doi = id_value
            except ValueError:
                pass

        if doi:
            hints = [f"  Institutional access: https://doi.org/{doi}"]
            if not self.config.contact_email:
                hints.append(
                    "  Tip: Set contact_email in config to enable Unpaywall "
                    "(finds OA copies from 50k+ repositories)"
                )
            # Check for unconfigured publisher tokens
            prefix = doi.split("/")[0] if "/" in doi else ""
            pub_info = _PUBLISHER_MAP.get(prefix)
            if pub_info:
                name, _url, config_key = pub_info
                if not getattr(self.config, config_key, ""):
                    hints.append(
                        f"  Tip: Set {config_key} in config for authenticated "
                        f"{name} downloads"
                    )
            # Show publisher-specific guidance
            publisher_hint = PUBLISHER_INFO.get(prefix)
            if publisher_hint:
                hints.append(f"  Publisher: {publisher_hint}")
            if hints:
                print("\n".join(hints), file=sys.stderr)

    async def retrieve_as_markdown(
        self,
        identifier: str,
        output_dir: str = ".",
        paper: Paper | None = None,
        extract_images: bool = True,
        converter: str = "auto",
        filename: str | None = None,
    ) -> Path | None:
        """Try PMC full-text first, then fall back to PDF download + convert.

        Args:
            identifier: DOI or other paper identifier.
            output_dir: Directory to save output (markdown and optional images).
            paper: Pre-fetched Paper object.
            extract_images: Whether to extract/download images.
            converter: Converter for PDF fallback ("auto", "markitdown", "mistral").
            filename: Custom base filename (without extension).

        Returns:
            Path to the markdown file, or None if all methods fail.
        """
        from opencite.fulltext import FullTextRetriever

        # If no paper provided, try to get metadata
        if paper is None:
            paper = await self._quick_lookup(identifier)

        # Try PMC full-text first
        async with FullTextRetriever(self.config) as ft:
            md_path = await ft.retrieve(
                identifier=identifier,
                output_dir=output_dir,
                paper=paper,
                extract_images=extract_images,
                filename=filename,
            )
            if md_path:
                logger.info("Retrieved full text from PMC for %s", identifier)
                return md_path

        # Fall back to PDF download + conversion
        logger.debug("PMC full text not available for %s, trying PDF", identifier)
        pdf_path = await self.download(
            identifier=identifier,
            output_dir=output_dir,
            paper=paper,
            filename=filename,
        )

        if pdf_path is None:
            return None

        # Convert PDF to markdown
        from opencite.convert import convert_pdf

        md_out = pdf_path.with_suffix(".md")
        try:
            convert_pdf(
                str(pdf_path),
                output_path=str(md_out),
                converter=converter,
                extract_images=extract_images,
                mistral_api_key=self.config.mistral_api_key,
            )
            return md_out
        except (OSError, ValueError, ImportError) as e:
            logger.warning("PDF conversion failed for %s: %s", identifier, e)
            return None

    def _make_filename(self, paper: Paper | None, identifier: str) -> str:
        """Generate a filename from paper metadata."""
        from opencite.utils import make_paper_filename

        return make_paper_filename(paper, identifier)
