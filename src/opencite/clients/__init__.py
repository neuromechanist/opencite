"""API clients for academic data sources."""

from opencite.clients.arxiv import ArXivClient
from opencite.clients.biorxiv import BioRxivClient
from opencite.clients.figshare import FigshareClient
from opencite.clients.medrxiv import MedRxivClient
from opencite.clients.osf import OSFClient
from opencite.clients.preprint_base import FulltextRoute, PreprintClient
from opencite.clients.zenodo import ZenodoClient

__all__ = [
    "ArXivClient",
    "BioRxivClient",
    "FigshareClient",
    "FulltextRoute",
    "MedRxivClient",
    "OSFClient",
    "PreprintClient",
    "ZenodoClient",
]
