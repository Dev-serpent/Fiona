"""API Catalog — discoverable registry of public APIs.

Provides offline search and metadata retrieval for the
public-apis/public-apis curated API collection.
"""

from fiona.apicatalog.models import ApiCategory, ApiEntry, SearchResult
from fiona.apicatalog.catalog import ApiCatalog

__all__ = [
    "ApiCatalog",
    "ApiEntry",
    "SearchResult",
    "ApiCategory",
]
