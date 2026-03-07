"""PMC BioC and OA Web Service client."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path  # noqa: TC003 - used at runtime in fetch_image
from typing import TYPE_CHECKING, Any

import httpx

from opencite.clients.base import BaseClient
from opencite.exceptions import APIError

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

_BIOC_BASE = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful"
_OA_BASE = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
_PMC_IMG_BASE = "https://pmc.ncbi.nlm.nih.gov/articles/instance"


class PMCClient(BaseClient):
    """Client for PMC BioC REST API and OA Web Service.

    BioC API returns structured full-text JSON for PMC Open Access articles.
    OA Web Service checks OA status and provides download links.
    No API key required. Rate limit: 3 req/sec per PMC guidelines.
    """

    def __init__(self, config: Config):
        super().__init__(
            config=config,
            base_url=_BIOC_BASE,
            rate_limit=3.0,
            burst=3,
        )
        self._oa_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> PMCClient:
        await super().__aenter__()
        self._oa_client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._oa_client:
            await self._oa_client.aclose()
            self._oa_client = None
        await super().__aexit__(*args)

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
        }
        if self.config.pubmed_api_key:
            headers["api_key"] = self.config.pubmed_api_key
        return headers

    @staticmethod
    def _normalize_pmcid(pmcid: str) -> str:
        """Ensure PMCID has the PMC prefix."""
        pmcid = pmcid.strip()
        if not pmcid.upper().startswith("PMC"):
            pmcid = f"PMC{pmcid}"
        return pmcid

    async def fetch_full_text(self, pmcid: str) -> dict | None:
        """Fetch structured full-text from the BioC API.

        Args:
            pmcid: PubMed Central ID (e.g. "PMC5334499").

        Returns:
            BioC document dict with passages, or None if not available.
        """
        pmcid = self._normalize_pmcid(pmcid)
        path = f"/pmcoa.cgi/BioC_json/{pmcid}/unicode"

        try:
            resp = await self.get(path)
            data = resp.json()
        except APIError as e:
            logger.debug("BioC API error for %s: %s", pmcid, e)
            return None
        except Exception as e:
            logger.debug("BioC fetch failed for %s: %s", pmcid, e)
            return None

        if not isinstance(data, list) or not data:
            logger.debug("BioC returned empty or non-list for %s", pmcid)
            return None

        collection = data[0]
        documents = collection.get("documents", [])
        if not documents:
            logger.debug("BioC returned no documents for %s", pmcid)
            return None

        return documents[0]

    async def check_oa_status(self, pmcid: str) -> dict | None:
        """Check if an article is in the PMC Open Access subset.

        Args:
            pmcid: PubMed Central ID (e.g. "PMC5334499").

        Returns:
            Dict with keys: id, citation, license, retracted, links (list of
            dicts with format, href, updated). None if not OA.
        """
        if self._oa_client is None:
            raise RuntimeError("Client not initialized. Use 'async with'.")

        pmcid = self._normalize_pmcid(pmcid)
        url = f"{_OA_BASE}?id={pmcid}"

        try:
            resp = await self._oa_client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.debug("OA status check failed for %s: %s", pmcid, e)
            return None

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError:
            logger.debug("Failed to parse OA XML for %s", pmcid)
            return None

        error = root.find("error")
        if error is not None:
            logger.debug("OA API: %s (%s)", error.text, error.get("code", ""))
            return None

        records = root.find("records")
        if records is None:
            return None

        record = records.find("record")
        if record is None:
            return None

        links = []
        for link_el in record.findall("link"):
            links.append(
                {
                    "format": link_el.get("format", ""),
                    "href": link_el.get("href", ""),
                    "updated": link_el.get("updated", ""),
                }
            )

        return {
            "id": record.get("id", pmcid),
            "citation": record.get("citation", ""),
            "license": record.get("license", ""),
            "retracted": record.get("retracted", "no") == "yes",
            "links": links,
        }

    async def fetch_image(
        self,
        pmcid: str,
        filename: str,
        dest: Path,
    ) -> Path | None:
        """Download a figure image from a PMC article.

        Tries the PMC instance URL pattern for article images.

        Args:
            pmcid: PubMed Central ID.
            filename: Image filename from BioC data (e.g. "WJR-9-27-g001.jpg").
            dest: Local path to save the image.

        Returns:
            Path to saved image, or None if download fails.
        """
        if self._oa_client is None:
            raise RuntimeError("Client not initialized. Use 'async with'.")

        pmcid = self._normalize_pmcid(pmcid)
        url = f"{_PMC_IMG_BASE}/{pmcid}/bin/{filename}"

        try:
            resp = await self._oa_client.get(url, follow_redirects=True)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type and "octet-stream" not in content_type:
                logger.debug(
                    "PMC image response not an image: %s (%s)",
                    filename,
                    content_type,
                )
                return None

            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            logger.debug("Downloaded PMC image: %s -> %s", filename, dest)
            return dest

        except httpx.HTTPError as e:
            logger.debug("PMC image download failed for %s: %s", filename, e)
            return None
