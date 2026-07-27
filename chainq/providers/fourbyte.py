import httpx

from chainq import cache, http
from chainq.config import settings

BASE_URL = "https://www.4byte.directory/api/v1/signatures/"


def signature(selector: str) -> str | None:
    key = cache.key_for("4byte", selector)
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        resp = http.get(BASE_URL, params={"hex_signature": selector, "ordering": "created_at"}, timeout=settings.http_timeout)
    except httpx.HTTPError:
        return None
    if resp.status_code >= 400:
        return None
    try:
        results = resp.json().get("results") or []
        text_signature = results[0]["text_signature"]
    except Exception:
        return None
    if not isinstance(text_signature, str):
        return None
    cache.put(key, text_signature, ttl=86400)
    return text_signature
