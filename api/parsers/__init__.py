"""Registry mapping ats_name -> parser instance."""
from .base import ATSParser, NormalizedRole
from .greenhouse import GreenhouseParser
from .ashby import AshbyParser
from .lever import LeverParser

REGISTRY: dict[str, ATSParser] = {
    "greenhouse": GreenhouseParser(),
    "ashby": AshbyParser(),
    "lever": LeverParser(),
    # "workday": WorkdayParser(),   # Phase 4
    # "manual":  handled out-of-band via add_role_manually
}


def get_parser(ats_name: str) -> ATSParser | None:
    return REGISTRY.get((ats_name or "").lower())


__all__ = ["REGISTRY", "get_parser", "NormalizedRole", "ATSParser"]
