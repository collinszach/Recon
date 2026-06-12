"""Parser interface. Each ATS implements fetch() -> list[NormalizedRole]."""
from __future__ import annotations
import hashlib
import random
import time
from dataclasses import dataclass, field
import httpx
from config import settings


@dataclass
class NormalizedRole:
    ats_job_id: str
    title: str
    location: str | None = None
    remote_flag: bool = False
    department: str | None = None
    url: str | None = None
    description: str = ""
    description_hash: str = field(default="")

    def __post_init__(self):
        if not self.description_hash:
            blob = f"{self.title}|{self.location}|{self.department}|{self.description}"
            self.description_hash = hashlib.sha256(blob.encode()).hexdigest()[:32]


def polite_delay() -> None:
    time.sleep(random.uniform(settings.scan_min_delay_sec, settings.scan_max_delay_sec))


def client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": settings.scan_user_agent, "Accept": "application/json"},
        timeout=20.0,
        follow_redirects=True,
    )


class ATSParser:
    """Subclass and implement fetch()."""
    ats_name: str = "base"

    def fetch(self, token: str) -> list[NormalizedRole]:
        raise NotImplementedError
