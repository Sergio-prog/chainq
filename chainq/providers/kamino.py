import re

import httpx

from chainq import cache, http
from chainq.config import settings
from chainq.errors import ChainqError

BASE_URL = "https://api.kamino.finance"
KLEND_PROGRAM_ID = "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD"

_BASE58_ADDRESS = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def _get(path: str, params: dict | None = None, ttl: float = 60) -> object:
    key = cache.key_for("kamino", path, params)
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        response = http.get(f"{BASE_URL}{path}", params=params, timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise ChainqError(f"Kamino API request failed: {exc}") from exc
    if response.status_code >= 400:
        raise ChainqError(f"Kamino API returned HTTP {response.status_code}")
    try:
        result = response.json()
    except ValueError as exc:
        raise ChainqError("Kamino API returned invalid JSON") from exc
    cache.put(key, result, ttl=ttl)
    return result


def market_configs() -> list[dict]:
    result = _get("/kamino-market", {"programId": KLEND_PROGRAM_ID}, ttl=300)
    if not isinstance(result, list):
        raise ChainqError("Kamino API returned an invalid market list")
    return [
        market
        for market in result
        if isinstance(market, dict)
        and isinstance(market.get("lendingMarket"), str)
        and _BASE58_ADDRESS.fullmatch(market["lendingMarket"])
    ]


def reserve_metrics(market: str) -> list[dict]:
    result = _get(f"/kamino-market/{market}/reserves/metrics", {"env": "mainnet-beta"})
    if not isinstance(result, list):
        raise ChainqError("Kamino API returned an invalid reserve list")
    return result
