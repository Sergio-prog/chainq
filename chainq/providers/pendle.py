from datetime import UTC, datetime

from chainq import cache, http

BASE_URL = "https://api-v2.pendle.finance/core/v1"


def _fetch_active_markets(chain_id: int) -> list[dict]:
    payload = http.fetch_json("Pendle API", f"{BASE_URL}/{chain_id}/markets/active", missing_ok=True)
    return (payload or {}).get("markets") or []


def active_markets(chain_id: int) -> list[dict]:
    return cache.remember(("pendle-markets", chain_id), 60, lambda: _fetch_active_markets(chain_id))


def market_row(market: dict) -> dict:
    details = market.get("details") or {}
    expiry = market.get("expiry")
    days = None
    if expiry:
        expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        days = (expiry_dt - datetime.now(UTC)).days
    apy = details.get("impliedApy")
    aggregated = details.get("aggregatedApy")
    return {
        "name": market.get("name"),
        "expiry": str(expiry)[:10] if expiry else None,
        "days_to_expiry": days,
        "implied_apy_pct": apy * 100 if apy is not None else None,
        "aggregated_apy_pct": aggregated * 100 if aggregated is not None else None,
        "liquidity_usd": details.get("liquidity"),
        "prime": market.get("isPrime"),
        "address": market.get("address"),
        "categories": market.get("categoryIds") or [],
    }
