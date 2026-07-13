"""Registry mapping ats_name -> parser instance."""
from .base import ATSParser, NormalizedRole
from .greenhouse import GreenhouseParser
from .ashby import AshbyParser
from .lever import LeverParser
from .workday import WorkdayParser
from .amazon import AmazonParser

REGISTRY: dict[str, ATSParser] = {
    "greenhouse": GreenhouseParser(),
    "ashby": AshbyParser(),
    "lever": LeverParser(),
    "workday": WorkdayParser(),
    "amazon": AmazonParser(),
    # "jsearch_company": no parser — handled by scan.search_runner's company sweep
    # "manual":  context-only; drop one-off roles via POST /api/roles or MCP add_role
}


def get_parser(ats_name: str) -> ATSParser | None:
    return REGISTRY.get((ats_name or "").lower())


__all__ = ["REGISTRY", "get_parser", "NormalizedRole", "ATSParser"]
