"""opencite: Academic literature search, citation management, and PDF retrieval."""

__version__ = "0.5.3"

from .config import Config
from .models import (
    Author,
    CitationResult,
    IDSet,
    Paper,
    PDFLocation,
    SearchResult,
    Source,
)

__all__ = [
    "Config",
    "Author",
    "CitationResult",
    "IDSet",
    "Paper",
    "PDFLocation",
    "SearchResult",
    "Source",
]
