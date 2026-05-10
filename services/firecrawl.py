import requests
import logging

logger = logging.getLogger(__name__)


def scrape_article(url: str) -> str | None:
    """Return markdown content for a URL via Firecrawl, or None on failure."""
    from config import settings

    if not settings.FIRECRAWL_API_KEY:
        logger.warning("FIRECRAWL_API_KEY not set, skipping Firecrawl scrape")
        return None

    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}"},
            json={"url": url, "formats": ["markdown"]},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("markdown") or None
    except Exception as e:
        logger.error(f"Firecrawl error for {url}: {e}")
        return None
