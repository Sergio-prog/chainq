from chainq import cache, http
from chainq.errors import ChainqError

BASE_URL = "https://www.4byte.directory/api/v1/signatures/"


def _fetch_signature(selector: str) -> str | None:
    try:
        payload = http.fetch_json("4byte", BASE_URL, params={"hex_signature": selector, "ordering": "created_at"})
    except ChainqError:
        return None
    results = payload.get("results") if isinstance(payload, dict) else None
    text_signature = results[0].get("text_signature") if results and isinstance(results[0], dict) else None
    return text_signature if isinstance(text_signature, str) else None


def signature(selector: str) -> str | None:
    return cache.remember(("4byte", selector), 86400, lambda: _fetch_signature(selector))
