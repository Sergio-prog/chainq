from chainq import cache, http

BASE_URL = "https://api-v2.pendle.finance/core/v1"


def _fetch_active_markets(chain_id: int) -> list[dict]:
    payload = http.fetch_json("Pendle API", f"{BASE_URL}/{chain_id}/markets/active", missing_ok=True)
    return (payload or {}).get("markets") or []


def active_markets(chain_id: int) -> list[dict]:
    return cache.remember(("pendle-markets", chain_id), 60, lambda: _fetch_active_markets(chain_id))
