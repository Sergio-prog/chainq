import httpx

from chainq import cache
from chainq.config import settings
from chainq.errors import ChainqError

BASE_URL = "https://api-v2.pendle.finance/core/v1"


def active_markets(chain_id: int) -> list[dict]:
    key = cache.key_for("pendle-markets", chain_id)
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        resp = httpx.get(f"{BASE_URL}/{chain_id}/markets/active", timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise ChainqError(f"Pendle API request failed: {exc}") from exc
    if resp.status_code == 404:
        return []
    if resp.status_code >= 400:
        raise ChainqError(f"Pendle API returned HTTP {resp.status_code}")
    result = resp.json().get("markets") or []
    cache.put(key, result, ttl=60)
    return result
