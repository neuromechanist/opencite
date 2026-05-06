"""medRxiv preprint client.

Mirrors :class:`opencite.clients.biorxiv.BioRxivClient` but routes to the
medRxiv server. Search filters CrossRef ``prefix:10.1101,type:posted-content``
results to medRxiv container-titles; DOI lookups go to
``api.biorxiv.org/details/medrxiv/{doi}``.

Shares all parsing logic via :mod:`opencite.clients._biorxiv_like`.
"""

from __future__ import annotations

from typing import ClassVar

from opencite.clients._biorxiv_like import _BiorxivLikePreprintClient


class MedRxivClient(_BiorxivLikePreprintClient):
    """Client for the medRxiv preprint server."""

    name: ClassVar[str] = "medrxiv"
    server: ClassVar[str] = "medrxiv"
