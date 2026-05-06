"""API clients for academic data sources."""

from opencite.clients.arxiv import ArXivClient
from opencite.clients.biorxiv import BioRxivClient
from opencite.clients.medrxiv import MedRxivClient
from opencite.clients.preprint_base import FulltextRoute, PreprintClient

__all__ = [
    "ArXivClient",
    "BioRxivClient",
    "FulltextRoute",
    "MedRxivClient",
    "PreprintClient",
]
