"""News-provider registry. NEWS_PROVIDER=auto picks GNews when its key is set,
else GDELT, which needs no key — so news works on a fresh checkout."""
from config import settings
from news.base import Article, NewsProvider
from news.gdelt import GdeltProvider
from news.gnews import GNewsProvider

_PROVIDERS: dict[str, NewsProvider] = {"gnews": GNewsProvider(), "gdelt": GdeltProvider()}


def active_provider() -> NewsProvider | None:
    choice = settings.news_provider.lower()
    if choice == "auto":
        return next((p for p in (_PROVIDERS["gnews"], _PROVIDERS["gdelt"]) if p.enabled()), None)
    p = _PROVIDERS.get(choice)
    return p if p and p.enabled() else None



