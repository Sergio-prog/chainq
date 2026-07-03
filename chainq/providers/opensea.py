import httpx

from chainq import cache, http
from chainq.config import settings
from chainq.errors import ChainqError

BASE_URL = "https://api.opensea.io/api/v2"
KEY_HINT = "get a key at https://docs.opensea.io and run `chainq config set opensea-api-key <key>`"

TOP_SORTS = ("one_day_volume", "seven_day_volume", "market_cap", "num_owners")


def _get(path: str, params: dict | None = None, ttl: float = 60, slug: str | None = None) -> dict:
    key = cache.key_for("opensea", path, params)
    cached = cache.get(key)
    if cached is not None:
        return cached
    headers = {"accept": "application/json"}
    if settings.opensea_api_key:
        headers["x-api-key"] = settings.opensea_api_key
    try:
        resp = http.get(f"{BASE_URL}{path}", params=params or {}, headers=headers, timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise ChainqError(f"OpenSea request failed: {exc}") from exc
    if resp.status_code >= 400:
        try:
            errors = resp.json().get("errors") or []
        except Exception:
            errors = []
        message = "; ".join(str(e) for e in errors) or f"HTTP {resp.status_code}"
        if "api key" in message.lower():
            slug_hint = f" (or '{slug}' is not a valid collection slug — check the opensea.io URL)" if slug else ""
            raise ChainqError(f"OpenSea: {message} — {KEY_HINT}{slug_hint}")
        if resp.status_code == 404:
            raise ChainqError(f"OpenSea: not found ({message}); collection slugs come from opensea.io URLs")
        if resp.status_code == 429:
            raise ChainqError("OpenSea rate limit hit; retry shortly")
        raise ChainqError(f"OpenSea: {message}")
    result = resp.json()
    cache.put(key, result, ttl)
    return result


def collection(slug: str) -> dict:
    slug = slug.strip().lower()
    return _get(f"/collections/{slug}", ttl=300, slug=slug)


def stats(slug: str) -> dict:
    slug = slug.strip().lower()
    return _get(f"/collections/{slug}/stats", ttl=60, slug=slug)


def top_collections(order_by: str, limit: int) -> list[dict]:
    payload = _get("/collections", {"order_by": order_by, "limit": min(max(limit, 1), 100)}, ttl=120)
    return payload.get("collections") or []
