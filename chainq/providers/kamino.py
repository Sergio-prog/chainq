import re

from chainq import cache, http
from chainq.errors import ChainqError

BASE_URL = "https://api.kamino.finance"
KLEND_PROGRAM_ID = "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD"

_BASE58_ADDRESS = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def _get(path: str, params: dict | None = None, ttl: float = 60) -> object:
    return cache.remember(
        ("kamino", path, params), ttl, lambda: http.fetch_json("Kamino API", f"{BASE_URL}{path}", params=params)
    )


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
