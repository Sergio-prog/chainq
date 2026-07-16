import httpx

from chainq import cache, http
from chainq.config import settings
from chainq.errors import ChainqError
from chainq.providers.coingecko_data import CONTRACT_LOOKUP_ORDER, PLATFORM_IDS, SYMBOL_TO_ID
from chainq.solana import looks_like_solana

BASE_URL = "https://api.coingecko.com/api/v3"


def _get(path: str, params: dict | None = None, ttl: float = 30, none_on_404: bool = False) -> dict | list | None:
    key = cache.key_for("coingecko", path, params)
    cached = cache.get(key)
    if cached is not None:
        return cached
    headers = {}
    if settings.coingecko_api_key:
        headers["x-cg-demo-api-key"] = settings.coingecko_api_key
    try:
        resp = http.get(f"{BASE_URL}{path}", params=params or {}, headers=headers, timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise ChainqError(f"CoinGecko request failed: {exc}") from exc
    if resp.status_code == 429:
        raise ChainqError("CoinGecko rate limit hit; retry in ~1 minute or set COINGECKO_API_KEY")
    if resp.status_code == 404 and none_on_404:
        return None
    if resp.status_code >= 400:
        raise ChainqError(f"CoinGecko returned HTTP {resp.status_code} for {path}")
    result = resp.json()
    cache.put(key, result, ttl)
    return result


def is_address(query: str) -> bool:
    return query.startswith("0x") and len(query) == 42


def is_solana_mint(query: str) -> bool:
    return not query.startswith("0x") and looks_like_solana(query)


def by_contract(address: str, network_key: str | None = None) -> dict | None:
    keys = (network_key,) if network_key else CONTRACT_LOOKUP_ORDER
    for key in keys:
        platform = PLATFORM_IDS.get(key)
        if platform is None:
            continue
        contract_address = address if platform == "solana" else address.lower()
        result = _get(f"/coins/{platform}/contract/{contract_address}", ttl=300, none_on_404=True)
        if result is not None:
            return result
    return None


def resolve_id(query: str) -> str:
    q = query.strip().lower()
    if q in SYMBOL_TO_ID:
        return SYMBOL_TO_ID[q]
    coins = _get("/search", {"query": q}, ttl=3600)["coins"]
    if not coins:
        raise ChainqError(f"no CoinGecko asset found for '{query}'")
    for c in coins:
        if c["id"] == q:
            return q
    return coins[0]["id"]


def markets(ids: list[str]) -> list[dict]:
    return _get(
        "/coins/markets",
        {"vs_currency": "usd", "ids": ",".join(ids), "price_change_percentage": "24h,7d"},
    )


def coin(coin_id: str) -> dict:
    return _get(
        f"/coins/{coin_id}",
        {
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "false",
        },
    )


def search(query: str) -> list[dict]:
    return _get("/search", {"query": query}, ttl=3600)["coins"]


def trending() -> list[dict]:
    return _get("/search/trending", ttl=300)["coins"]


def simple_price(ids: list[str]) -> dict:
    return _get("/simple/price", {"ids": ",".join(ids), "vs_currencies": "usd"})


OHLC_DAYS = (1, 7, 14, 30, 90, 180, 365)


def snap_ohlc_days(days: int) -> int:
    return next((d for d in OHLC_DAYS if d >= days), OHLC_DAYS[-1])


def ohlc(coin_id: str, days: int) -> list[list[float]]:
    return _get(f"/coins/{coin_id}/ohlc", {"vs_currency": "usd", "days": days}, ttl=300)


def history(coin_id: str, date_ddmmyyyy: str) -> dict:
    return _get(f"/coins/{coin_id}/history", {"date": date_ddmmyyyy, "localization": "false"}, ttl=3600)


def try_price_usd(coin_id: str | None) -> float | None:
    if not coin_id:
        return None
    try:
        data = simple_price([coin_id])
        return data.get(coin_id, {}).get("usd")
    except Exception:
        return None
