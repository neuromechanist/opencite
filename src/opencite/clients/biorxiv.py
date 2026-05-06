"""bioRxiv preprint client.

Search routes through CrossRef (`prefix:10.1101,type:posted-content`,
filtered to bioRxiv container-titles); DOI lookups go to the bioRxiv
Content API at ``api.biorxiv.org/details/biorxiv/{doi}``.

The shared logic for bioRxiv-style preprint servers (bioRxiv, medRxiv) lives
in :mod:`opencite.clients._biorxiv_like`. Both subclasses share the same DOI
prefix, the same Content API base URL, and the same parsing -- only the
``server`` segment differs.
"""

from __future__ import annotations

from typing import ClassVar

from opencite.clients._biorxiv_like import _BiorxivLikePreprintClient


class BioRxivClient(_BiorxivLikePreprintClient):
    """Client for the bioRxiv preprint server."""

    name: ClassVar[str] = "biorxiv"
    server: ClassVar[str] = "biorxiv"
