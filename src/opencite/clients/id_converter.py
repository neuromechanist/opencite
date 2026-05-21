"""PMC ID Converter API client."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, ClassVar

from opencite.clients.base import BaseClient
from opencite.models import IDSet

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1"


class IDConverterClient(BaseClient):
    """Client for the PMC ID Converter API.

    Converts between PMID, PMCID, DOI, and Manuscript IDs.
    Up to 200 IDs per request, but all IDs must be the same type.

    Shares the NCBI eutils rate limiter with `PubMedClient`.
    """

    shared_limiter_key: ClassVar[str | None] = "ncbi_eutils"

    def __init__(self, config: Config):
        super().__init__(
            config=config,
            base_url=BASE_URL,
            rate_limit=config.pubmed_rate_limit,
            burst=3,
        )

    def _default_headers(self) -> dict[str, str]:
        return {}

    async def convert(self, ids: list[str]) -> list[IDSet]:
        """Convert a list of IDs (PMID, PMCID, DOI) to IDSets.

        Groups IDs by type since the API requires homogeneous ID types
        per request.
        """
        groups = _group_ids_by_type(ids)
        results: list[IDSet] = []
        for group in groups.values():
            chunk_results = await self._convert_chunk(group)
            results.extend(chunk_results)
        return results

    async def _convert_chunk(self, ids: list[str]) -> list[IDSet]:
        """Convert a homogeneous chunk of IDs."""
        results: list[IDSet] = []
        for i in range(0, len(ids), 200):
            chunk = ids[i : i + 200]
            params: dict[str, Any] = {
                "ids": ",".join(chunk),
                "format": "json",
                "tool": "opencite",
            }
            if self.config.contact_email:
                params["email"] = self.config.contact_email
            try:
                resp = await self.get("/articles/", params=params)
                data = resp.json()
                for record in data.get("records", []):
                    if record.get("status") == "error":
                        continue
                    results.append(
                        IDSet(
                            doi=str(record.get("doi", "") or ""),
                            pmid=str(record.get("pmid", "") or ""),
                            pmcid=str(record.get("pmcid", "") or ""),
                        )
                    )
            except Exception:
                logger.warning("ID conversion failed for chunk at %d", i)
        return results


def _group_ids_by_type(ids: list[str]) -> dict[str, list[str]]:
    """Group IDs by their type for homogeneous API requests."""
    groups: dict[str, list[str]] = {}
    for raw_id in ids:
        id_type = _detect_id_type(raw_id)
        groups.setdefault(id_type, []).append(raw_id)
    return groups


def _detect_id_type(raw_id: str) -> str:
    """Detect ID type: pmid, pmcid, or doi."""
    s = raw_id.strip()
    if re.match(r"^\d+$", s):
        return "pmid"
    if s.upper().startswith("PMC"):
        return "pmcid"
    return "doi"
