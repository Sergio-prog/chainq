import math
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


def _number(value: object) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError
    number = float(value)
    if not math.isfinite(number):
        raise ValueError
    return number


def reserve_row(market: dict, reserve: dict) -> dict | None:
    if not isinstance(market, dict) or not isinstance(reserve, dict):
        return None
    try:
        market_name = market.get("name")
        market_address = market.get("lendingMarket")
        symbol = reserve.get("liquidityToken")
        mint = reserve.get("liquidityTokenMint")
        reserve_address = reserve.get("reserve")
        if not all(isinstance(value, str) and value for value in (market_name, market_address, symbol, mint, reserve_address)):
            return None
        supplied_usd = _number(reserve.get("totalSupplyUsd"))
        borrowed_usd = _number(reserve.get("totalBorrowUsd"))
        return {
            "market": market_name,
            "market_address": market_address,
            "symbol": symbol,
            "mint": mint,
            "supply_apy_pct": _number(reserve.get("supplyApy")) * 100,
            "borrow_apy_pct": _number(reserve.get("borrowApy")) * 100,
            "supplied_usd": supplied_usd,
            "borrowed_usd": borrowed_usd,
            "utilization_pct": borrowed_usd / supplied_usd * 100 if supplied_usd else None,
            "max_ltv_pct": _number(reserve.get("maxLtv")) * 100,
            "reserve_address": reserve_address,
        }
    except (TypeError, ValueError, OverflowError):
        return None
