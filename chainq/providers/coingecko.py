import httpx

from chainq.config import settings
from chainq.errors import ChainqError

BASE_URL = "https://api.coingecko.com/api/v3"

SYMBOL_TO_ID = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "sol": "solana",
    "usdt": "tether",
    "usdc": "usd-coin",
    "bnb": "binancecoin",
    "xrp": "ripple",
    "ada": "cardano",
    "doge": "dogecoin",
    "avax": "avalanche-2",
    "dot": "polkadot",
    "link": "chainlink",
    "pol": "polygon-ecosystem-token",
    "matic": "polygon-ecosystem-token",
    "arb": "arbitrum",
    "op": "optimism",
    "uni": "uniswap",
    "aave": "aave",
    "ldo": "lido-dao",
    "mkr": "maker",
    "sky": "sky",
    "ena": "ethena",
    "usde": "ethena-usde",
    "hype": "hyperliquid",
    "sui": "sui",
    "apt": "aptos",
    "ton": "the-open-network",
    "trx": "tron",
    "ltc": "litecoin",
    "near": "near",
    "atom": "cosmos",
    "fil": "filecoin",
    "inj": "injective",
    "tia": "celestia",
    "sei": "sei-network",
    "pepe": "pepe",
    "shib": "shiba-inu",
    "wbtc": "wrapped-bitcoin",
    "weth": "weth",
    "steth": "staked-ether",
    "dai": "dai",
    "crv": "curve-dao-token",
    "gho": "gho",
    "xdai": "xdai",
    "jup": "jupiter-exchange-solana",
    "wif": "dogwifcoin",
    "bonk": "bonk",
}


def _get(path: str, params: dict | None = None) -> dict | list:
    headers = {}
    if settings.coingecko_api_key:
        headers["x-cg-demo-api-key"] = settings.coingecko_api_key
    try:
        resp = httpx.get(f"{BASE_URL}{path}", params=params or {}, headers=headers, timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise ChainqError(f"CoinGecko request failed: {exc}") from exc
    if resp.status_code == 429:
        raise ChainqError("CoinGecko rate limit hit; retry in ~1 minute or set COINGECKO_API_KEY")
    if resp.status_code >= 400:
        raise ChainqError(f"CoinGecko returned HTTP {resp.status_code} for {path}")
    return resp.json()


def resolve_id(query: str) -> str:
    q = query.strip().lower()
    if q in SYMBOL_TO_ID:
        return SYMBOL_TO_ID[q]
    coins = _get("/search", {"query": q})["coins"]
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
    return _get("/search", {"query": query})["coins"]


def simple_price(ids: list[str]) -> dict:
    return _get("/simple/price", {"ids": ",".join(ids), "vs_currencies": "usd"})


def try_price_usd(coin_id: str | None) -> float | None:
    if not coin_id:
        return None
    try:
        data = simple_price([coin_id])
        return data.get(coin_id, {}).get("usd")
    except Exception:
        return None
