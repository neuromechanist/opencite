"""Preprint full-text retrieval pipeline.

Sits between :class:`opencite.fulltext.FullTextRetriever` (PMC BioC) and the
PDF download path. For OA preprints, fetches the server-native HTML/JATS
representation and converts it to markdown so the user does not pay the
quality and bandwidth cost of a PDF round-trip.

Phase 2 ships the arXiv (ar5iv HTML5) and bioRxiv/medRxiv (`.full` HTML)
routes; Phase 3 will plug in OSF/PsyArXiv, Zenodo, and Figshare.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from opencite.clients.arxiv import ArXivClient
from opencite.clients.biorxiv import BioRxivClient
from opencite.clients.figshare import FigshareClient
from opencite.clients.medrxiv import MedRxivClient
from opencite.clients.osf import OSFClient
from opencite.clients.preprint_base import FulltextRoute, PreprintClient
from opencite.clients.zenodo import ZenodoClient
from opencite.utils import make_paper_filename

if TYPE_CHECKING:
    from opencite.config import Config
    from opencite.models import Paper

logger = logging.getLogger(__name__)


class PreprintFullTextRetriever:
    """Retrieve preprint full text via the matching `PreprintClient`.

    Picks the right client for a paper using two signals, in order:

    1. ``paper.data_sources`` matches a client's ``name`` (e.g. ``"arxiv"``).
    2. ``paper.doi`` prefix matches a known preprint DOI prefix
       (``10.48550/arXiv.`` -> arxiv; ``10.1101/`` -> biorxiv then medrxiv).

    Mirrors the shape of :class:`opencite.fulltext.FullTextRetriever` so
    callers in `pdf.py` and `batch.py` can chain them with parallel structure.
    """

    def __init__(
        self,
        config: Config,
        clients: list[PreprintClient] | None = None,
    ) -> None:
        self.config = config
        # Default fan-out covers all preprint servers shipped through Phase 3.
        if clients is None:
            self._clients: list[PreprintClient] = [
                ArXivClient(config),
                BioRxivClient(config),
                MedRxivClient(config),
                OSFClient(config),
                ZenodoClient(config),
                FigshareClient(config),
            ]
        else:
            if not clients:
                raise ValueError(
                    "PreprintFullTextRetriever requires at least one client"
                )
            self._clients = clients
        names = [c.name for c in self._clients]
        if len(set(names)) != len(names):
            raise ValueError(
                f"PreprintFullTextRetriever client names must be unique: {names!r}"
            )
        self._by_name: dict[str, PreprintClient] = {c.name: c for c in self._clients}

    async def __aenter__(self) -> PreprintFullTextRetriever:
        entered: list[PreprintClient] = []
        try:
            for client in self._clients:
                await client.__aenter__()
                entered.append(client)
        except Exception:
            # Roll back the partial enter so we don't leak open httpx clients
            # for the subset that successfully opened.
            for c in reversed(entered):
                try:
                    await c.__aexit__()
                except Exception:
                    logger.warning(
                        "Failed to roll back %s during retriever init", c.name
                    )
            raise
        return self

    async def __aexit__(self, *args: object) -> None:
        for client in self._clients:
            try:
                await client.__aexit__(*args)
            except Exception:
                logger.warning("Error closing preprint client %s", client.name)

    def _pick_client(self, paper: Paper) -> PreprintClient | None:
        """Return the preprint client that can serve *paper*, or None."""
        # 1. Direct attribution on the paper. Strip the optional
        #    ``provider:`` sub-slug used by OSF (``osf:psyarxiv``) so the
        #    lookup hits the canonical client name.
        for src in paper.data_sources:
            base = src.split(":", 1)[0]
            client = self._by_name.get(base)
            if client is not None:
                return client

        # 2. arXiv ID -> arXiv client (covers bare arXiv IDs and ``arxiv:`` URLs
        #    where no DOI is on the paper yet).
        if paper.ids.arxiv_id:
            client = self._by_name.get("arxiv")
            if client is not None:
                return client

        # 3. DOI-prefix routing.
        doi = (paper.doi or "").strip().lower()
        if not doi:
            return None
        if doi.startswith("10.48550/arxiv."):
            return self._by_name.get("arxiv")
        if OSFClient.is_osf_doi(doi):
            return self._by_name.get("osf")
        if doi.startswith("10.5281/zenodo."):
            return self._by_name.get("zenodo")
        if doi.startswith("10.6084/m9.figshare."):
            return self._by_name.get("figshare")
        if doi.startswith("10.1101/"):
            # bioRxiv first; medRxiv as fallback. Both will return None for
            # the wrong server, so the orchestrator above us would have to
            # try multiple. Here we pick ONE client to fetch full text from
            # and rely on the .full URL succeeding. bioRxiv fronting is fine
            # because bioRxiv mirrors medRxiv content URLs cross-domain in
            # practice; if it 404s we return None and the caller falls back
            # to PDF.
            return self._by_name.get("biorxiv") or self._by_name.get("medrxiv")
        return None

    async def retrieve(
        self,
        paper: Paper,
        output_dir: str | Path = ".",
        identifier: str | None = None,
        filename: str | None = None,
    ) -> Path | None:
        """Fetch full text for *paper* and write markdown to disk.

        Args:
            paper: The paper to retrieve. Must carry a DOI or arXiv ID.
            output_dir: Directory for the markdown file (created if missing).
            identifier: Original CLI identifier, used for filename fallback.
            filename: Custom base filename (without extension).

        Returns:
            Path to the written markdown file, or None when no preprint
            route applies / fetch fails / conversion fails.
        """
        ident_for_log = identifier or paper.doi or paper.ids.arxiv_id or "<unknown>"

        client = self._pick_client(paper)
        if client is None:
            logger.debug(
                "no preprint client for %s (doi=%s, arxiv_id=%s, sources=%s)",
                ident_for_log,
                paper.doi,
                paper.ids.arxiv_id,
                paper.data_sources,
            )
            return None

        route = client.fulltext_route(paper)
        if route in (FulltextRoute.NONE, FulltextRoute.PDF):
            logger.debug(
                "preprint route %s for %s via %s -> skip",
                route,
                ident_for_log,
                client.name,
            )
            return None

        md_text = await client.fetch_fulltext(paper)
        if not md_text:
            logger.debug(
                "preprint fetch returned empty markdown for %s via %s",
                ident_for_log,
                client.name,
            )
            return None

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        ident_for_name = identifier or paper.doi or paper.ids.arxiv_id or ""
        fname = filename or make_paper_filename(paper, ident_for_name)
        if not fname.endswith(".md"):
            fname += ".md"
        md_path = out_dir / fname
        md_path.write_text(md_text, encoding="utf-8")
        logger.info(
            "Preprint full text written to %s via %s (%s)",
            md_path,
            client.name,
            route,
        )
        return md_path

    async def retrieve_for_identifier(
        self,
        identifier: str,
        output_dir: str | Path = ".",
        filename: str | None = None,
    ) -> Path | None:
        """Identifier-only entry point: parses the identifier, retrieves full text.

        Accepts any identifier `parse_identifier` understands -- bare DOIs,
        ``arxiv:XXXX.YYYYY``, ``pmid:XXXXX``, full URLs to arXiv/bioRxiv, etc.
        Maps it to the right `IDSet` field so `_pick_client` can route by
        either ``arxiv_id`` or ``doi``. Used by `batch.py` and the `pdf` CLI
        subcommand when only a free-form identifier is available.
        """
        from opencite.models import IDSet, IDType, parse_identifier
        from opencite.models import Paper as PaperModel

        ids: IDSet
        try:
            id_type, id_value = parse_identifier(identifier)
        except ValueError:
            ids = IDSet(doi=identifier)
        else:
            if id_type == IDType.ARXIV:
                ids = IDSet(arxiv_id=id_value)
            elif id_type == IDType.DOI:
                ids = IDSet(doi=id_value)
            elif id_type == IDType.PMID:
                ids = IDSet(pmid=id_value)
            elif id_type == IDType.PMCID:
                ids = IDSet(pmcid=id_value)
            else:
                ids = IDSet(doi=identifier)

        paper = PaperModel(title="", ids=ids)
        return await self.retrieve(
            paper,
            output_dir=output_dir,
            identifier=identifier,
            filename=filename,
        )
