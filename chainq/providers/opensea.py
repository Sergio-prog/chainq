from chainq import cache, http
from chainq.config import settings
from chainq.errors import ChainqError
from chainq.http import UpstreamError

BASE_URL = "https://api.opensea.io/api/v2"
KEY_HINT = "get a key at https://docs.opensea.io and run `chainq config set opensea-api-key <key>`"


def _error_message(resp) -> str:
    try:
        errors = resp.json().get("errors") or []
    except (ValueError, AttributeError):
        errors = []
    return "; ".join(str(e) for e in errors) or f"HTTP {resp.status_code}"


def _fetch(path: str, params: dict | None, slug: str | None) -> dict:
    headers = {"accept": "application/json"}
    if settings.opensea_api_key:
        headers["x-api-key"] = settings.opensea_api_key
    try:
        return http.fetch_json("OpenSea", f"{BASE_URL}{path}", params=params or {}, headers=headers)
    except UpstreamError as exc:
        if exc.response is None:
            raise
        message = _error_message(exc.response)
        if "api key" in message.lower():
            slug_hint = f" (or '{slug}' is not a valid collection slug; check the opensea.io URL)" if slug else ""
            raise ChainqError(f"OpenSea: {message}; {KEY_HINT}{slug_hint}") from exc
        if exc.status == 404:
            raise ChainqError(f"OpenSea: not found ({message}); collection slugs come from opensea.io URLs") from exc
        if exc.status == 429:
            raise ChainqError("OpenSea rate limit hit; retry shortly") from exc
        raise ChainqError(f"OpenSea: {message}") from exc


def _get(path: str, params: dict | None = None, ttl: float = 60, slug: str | None = None) -> dict:
    return cache.remember(("opensea", path, params), ttl, lambda: _fetch(path, params, slug))


def collection(slug: str) -> dict:
    slug = slug.strip().lower()
    return _get(f"/collections/{slug}", ttl=300, slug=slug)


def stats(slug: str) -> dict:
    slug = slug.strip().lower()
    return _get(f"/collections/{slug}/stats", ttl=60, slug=slug)


def top_collections(order_by: str, limit: int) -> list[dict]:
    payload = _get("/collections", {"order_by": order_by, "limit": min(max(limit, 1), 100)}, ttl=120)
    return payload.get("collections") or []
