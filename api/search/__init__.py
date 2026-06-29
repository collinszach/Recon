"""Search-provider registry + default query terms.

enabled_providers() returns only the providers whose credentials are set, so
turning a source on/off is purely a matter of supplying (or omitting) its key.
"""
from config import settings
from search.base import NormalizedRole, SearchProvider, SearchResult
from search.jsearch import JSearchProvider
from search.usajobs import USAJobsProvider

_PROVIDERS: list[SearchProvider] = [JSearchProvider(), USAJobsProvider()]


def enabled_providers() -> list[SearchProvider]:
    return [p for p in _PROVIDERS if p.enabled()]


def default_terms() -> list[str]:
    """Keyword terms to search. SEARCH_TERMS (.env) overrides; otherwise derive
    a small, free-tier-friendly set from the active tracks."""
    if settings.search_terms.strip():
        return [t.strip() for t in settings.search_terms.split(",") if t.strip()]
    mode = "intern" if settings.intern_only else settings.track_mode
    terms = ["technical product manager", "product manager"]
    if mode in ("intern", "both"):
        terms.append("product manager intern")
    if mode in ("ops", "both"):
        terms.append("strategy and operations")
    return terms


__all__ = ["enabled_providers", "default_terms", "SearchProvider", "SearchResult", "NormalizedRole"]
