import httpx

from chainq import cache, http
from chainq.errors import ChainqError

BASE_URL = "https://api.llama.fi"
STABLECOINS_URL = "https://stablecoins.llama.fi/stablecoins"
YIELDS_URL = "https://yields.llama.fi/pools"
COINS_URL = "https://coins.llama.fi/prices/current"
COINS_BATCH = 80
MIN_CONFIDENCE = 0.5

CHAIN_SLUGS = {
    "ethereum": "ethereum",
    "arbitrum": "arbitrum",
    "base": "base",
    "optimism": "optimism",
    "polygon": "polygon",
    "bsc": "bsc",
    "avalanche": "avax",
    "gnosis": "xdai",
    "unichain": "unichain",
    "linea": "linea",
    "scroll": "scroll",
    "zksync": "era",
    "mantle": "mantle",
    "blast": "blast",
    "sonic": "sonic",
    "berachain": "berachain",
    "worldchain": "wc",
    "ink": "ink",
    "soneium": "soneium",
    "celo": "celo",
    "sei": "sei",
    "hyperevm": "hyperliquid",
    "monad": "monad",
    "plasma": "plasma",
    "katana": "katana",
    "robinhood": "robinhood",
    "arc": "arc",
}


def _fetch(url: str, params: dict | None = None) -> dict | list:
    try:
        resp = http.get(url, params=params or {})
    except httpx.HTTPError as exc:
        raise ChainqError(f"DefiLlama request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise ChainqError(f"DefiLlama returned HTTP {resp.status_code} for {url}")
    return resp.json()


def protocols() -> list[dict]:
    key = cache.key_for("llama-protocols")
    cached = cache.get(key)
    if cached is not None:
        return cached
    synthetic = {"borrowed", "staking", "pool2", "vesting", "treasury", "offers"}
    trimmed = [
        {
            "slug": p.get("slug"),
            "name": p.get("name"),
            "symbol": p.get("symbol"),
            "category": p.get("category"),
            "tvl_usd": p.get("tvl"),
            "chains": (p.get("chains") or [])[:10],
            "chain_tvls": dict(
                sorted(
                    (
                        (name, tvl)
                        for name, tvl in (p.get("chainTvls") or {}).items()
                        if "-" not in name and name.lower() not in synthetic
                    ),
                    key=lambda kv: -(kv[1] or 0),
                )[:5]
            ),
            "change_1d_pct": p.get("change_1d"),
            "change_7d_pct": p.get("change_7d"),
            "mcap_usd": p.get("mcap"),
        }
        for p in _fetch(f"{BASE_URL}/protocols")
    ]
    cache.put(key, trimmed, ttl=300)
    return trimmed


def find_protocol(query: str) -> dict | None:
    q = query.strip().lower()
    rows = protocols()
    for p in rows:
        if p["slug"] == q or (p["name"] or "").lower() == q:
            return p
    matches = [p for p in rows if q in (p["slug"] or "") or q in (p["name"] or "").lower()]
    if matches:
        return max(matches, key=lambda p: p["tvl_usd"] or 0)
    return None


def _circulating(asset: dict, field: str) -> float | None:
    return (asset.get(field) or {}).get(asset.get("pegType"))


def stablecoins() -> list[dict]:
    key = cache.key_for("llama-stablecoins")
    cached = cache.get(key)
    if cached is not None:
        return cached
    rows = [
        {
            "symbol": asset.get("symbol"),
            "name": asset.get("name"),
            "gecko_id": asset.get("gecko_id"),
            "peg_type": asset.get("pegType"),
            "mechanism": asset.get("pegMechanism"),
            "price_usd": asset.get("price"),
            "mcap_usd": _circulating(asset, "circulating"),
            "mcap_prev_day_usd": _circulating(asset, "circulatingPrevDay"),
            "mcap_prev_week_usd": _circulating(asset, "circulatingPrevWeek"),
            "mcap_prev_month_usd": _circulating(asset, "circulatingPrevMonth"),
        }
        for asset in _fetch(STABLECOINS_URL, {"includePrices": "true"}).get("peggedAssets") or []
    ]
    cache.put(key, rows, ttl=300)
    return rows


def chains() -> list[dict]:
    key = cache.key_for("llama-chains")
    cached = cache.get(key)
    if cached is not None:
        return cached
    rows = [
        {"name": c.get("name"), "tvl_usd": c.get("tvl"), "token": c.get("tokenSymbol")}
        for c in _fetch(f"{BASE_URL}/v2/chains")
    ]
    cache.put(key, rows, ttl=300)
    return rows


def _summary(kind: str, slug: str) -> dict | None:
    key = cache.key_for("llama-summary", kind, slug)
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        resp = http.get(
            f"{BASE_URL}/summary/{kind}/{slug}",
            params={"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true"},
        )
    except httpx.HTTPError:
        return None
    if resp.status_code >= 400:
        return None
    payload = resp.json()
    result = {
        "total_24h_usd": payload.get("total24h"),
        "total_7d_usd": payload.get("total7d"),
        "total_30d_usd": payload.get("total30d"),
        "change_1d_pct": payload.get("change_1d"),
    }
    cache.put(key, result, ttl=300)
    return result


def fees(slug: str) -> dict | None:
    return _summary("fees", slug)


def dex_volume(slug: str) -> dict | None:
    return _summary("dexs", slug)


def tvl(slug: str) -> float | None:
    key = cache.key_for("llama-tvl", slug)
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        resp = http.get(f"{BASE_URL}/tvl/{slug}")
    except httpx.HTTPError:
        return None
    if resp.status_code >= 400:
        return None
    value = resp.json()
    result = float(value) if isinstance(value, int | float) else None
    cache.put(key, result, ttl=300)
    return result


def yield_pools(projects: tuple[str, ...] | None = None) -> list[dict]:
    key = cache.key_for("llama-yields")
    cached = cache.get(key)
    if cached is None:
        cached = [
            {
                "symbol": p.get("symbol"),
                "project": p.get("project"),
                "chain": p.get("chain"),
                "tvl_usd": p.get("tvlUsd"),
                "apy_pct": p.get("apy"),
                "apy_base_pct": p.get("apyBase"),
                "apy_reward_pct": p.get("apyReward"),
                "pool": p.get("pool"),
            }
            for p in _fetch(YIELDS_URL).get("data") or []
        ]
        cache.put(key, cached, ttl=300)
    if projects:
        return [p for p in cached if p["project"] in projects]
    return cached


def token_prices(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], dict]:
    ids = {}
    for network_key, address in pairs:
        slug = CHAIN_SLUGS.get(network_key)
        if slug:
            ids[f"{slug}:{address}"] = (network_key, address)
    keys = sorted(ids)
    prices: dict[tuple[str, str], dict] = {}
    for start in range(0, len(keys), COINS_BATCH):
        batch = keys[start : start + COINS_BATCH]
        cache_key = cache.key_for("llama-coins", batch)
        payload = cache.get(cache_key)
        if payload is None:
            try:
                payload = _fetch(f"{COINS_URL}/{','.join(batch)}").get("coins") or {}
            except ChainqError:
                continue
            cache.put(cache_key, payload, 60)
        for coin_id, coin in payload.items():
            price = coin.get("price")
            confidence = coin.get("confidence", 1.0)
            if coin_id in ids and isinstance(price, (int, float)) and price > 0 and confidence >= MIN_CONFIDENCE:
                prices[ids[coin_id]] = {"price": float(price), "confidence": float(confidence)}
    return prices
