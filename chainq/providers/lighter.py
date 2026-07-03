import httpx

from chainq import cache, http
from chainq.config import settings
from chainq.errors import ChainqError

BASE_URL = "https://mainnet.zklighter.elliot.ai/api/v1"


def _get(path: str, params: dict | None = None, ttl: float = 15) -> dict:
    key = cache.key_for("lighter", path, params)
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        resp = http.get(f"{BASE_URL}{path}", params=params or {}, timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise ChainqError(f"Lighter API request failed: {exc}") from exc
    payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if resp.status_code >= 400 or payload.get("code") not in (200, None):
        message = payload.get("message") or f"HTTP {resp.status_code}"
        raise ChainqError(f"Lighter API error: {message}")
    cache.put(key, payload, ttl)
    return payload


def markets() -> list[dict]:
    details = _get("/orderBookDetails").get("order_book_details") or []
    rows = []
    for m in details:
        if m.get("status") != "active":
            continue
        last = float(m.get("last_trade_price") or 0)
        oi = float(m.get("open_interest") or 0)
        rows.append(
            {
                "coin": m.get("symbol"),
                "market_id": m.get("market_id"),
                "last_price": last,
                "change_24h_pct": float(m.get("daily_price_change") or 0),
                "volume_24h_usd": float(m.get("daily_quote_token_volume") or 0),
                "open_interest": oi,
                "open_interest_usd": oi * last,
                "trades_24h": m.get("daily_trades_count"),
            }
        )
    return rows


def funding_rates() -> dict[str, float]:
    rates = _get("/funding-rates").get("funding_rates") or []
    return {r["symbol"]: float(r["rate"]) for r in rates if r.get("exchange") == "lighter"}


def account(l1_address: str) -> dict:
    payload = _get("/account", {"by": "l1_address", "value": l1_address}, ttl=5)
    accounts = payload.get("accounts") or []
    if not accounts:
        raise ChainqError(f"no Lighter account found for {l1_address}")
    return accounts[0]
