import httpx

from chainq import cache
from chainq.config import settings
from chainq.errors import ChainqError

SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"
TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens"
LLAMA_TVL_URL = "https://api.llama.fi/tvl/uniswap"
LLAMA_SUMMARY_URL = "https://api.llama.fi/summary/dexs/uniswap"

CHAIN_SLUGS = {
    "ethereum": "ethereum",
    "arbitrum": "arbitrum",
    "base": "base",
    "optimism": "optimism",
    "polygon": "polygon",
    "bsc": "bsc",
    "avalanche": "avalanche",
    "gnosis": "gnosischain",
    "unichain": "unichain",
}


def _get(url: str, params: dict | None = None, ttl: float = 60) -> dict:
    key = cache.key_for("uniswap", url, params)
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        resp = httpx.get(url, params=params or {}, timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise ChainqError(f"request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise ChainqError(f"{url} returned HTTP {resp.status_code}")
    result = resp.json()
    cache.put(key, result, ttl)
    return result


def _pair_row(pair: dict) -> dict:
    labels = pair.get("labels") or []
    return {
        "pair": f"{pair['baseToken']['symbol']}/{pair['quoteToken']['symbol']}",
        "chain": pair.get("chainId"),
        "version": labels[0] if labels else None,
        "price_usd": float(pair["priceUsd"]) if pair.get("priceUsd") else None,
        "change_24h_pct": (pair.get("priceChange") or {}).get("h24"),
        "volume_24h_usd": (pair.get("volume") or {}).get("h24"),
        "liquidity_usd": (pair.get("liquidity") or {}).get("usd"),
        "fdv_usd": pair.get("fdv"),
        "pair_address": pair.get("pairAddress"),
        "url": pair.get("url"),
    }


def token_pairs(address: str) -> list[dict]:
    return _get(f"{TOKEN_URL}/{address}").get("pairs") or []


def search_pairs(query: str) -> list[dict]:
    return _get(SEARCH_URL, {"q": query}).get("pairs") or []


def uniswap_rows(pairs: list[dict], chain_slug: str, quote: str | None = None) -> list[dict]:
    rows = []
    for pair in pairs:
        if pair.get("dexId") != "uniswap" or pair.get("chainId") != chain_slug:
            continue
        symbols = {pair["baseToken"]["symbol"].upper(), pair["quoteToken"]["symbol"].upper()}
        if quote and quote.upper() not in symbols:
            continue
        rows.append(_pair_row(pair))
    return rows


def stats() -> dict:
    summary = _get(
        LLAMA_SUMMARY_URL,
        {"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true"},
        ttl=300,
    )
    tvl = _get(LLAMA_TVL_URL, ttl=300)
    return {
        "protocol": "uniswap",
        "tvl_usd": float(tvl) if isinstance(tvl, int | float) else None,
        "volume_24h_usd": summary.get("total24h"),
        "volume_7d_usd": summary.get("total7d"),
        "volume_30d_usd": summary.get("total30d"),
        "volume_change_1d_pct": summary.get("change_1d"),
        "volume_change_7d_pct": summary.get("change_7d"),
        "source": "defillama",
    }
