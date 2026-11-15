
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
    return http.fetch_json("DefiLlama", url, params=params or {})


SYNTHETIC_TVL_KEYS = {"borrowed", "staking", "pool2", "vesting", "treasury", "offers"}


def _top_chain_tvls(chain_tvls: dict) -> dict:
    real = ((name, tvl) for name, tvl in chain_tvls.items() if "-" not in name and name.lower() not in SYNTHETIC_TVL_KEYS)
    return dict(sorted(real, key=lambda kv: -(kv[1] or 0))[:5])


def _fetch_protocols() -> list[dict]:
    return [
        {
            "slug": p.get("slug"),
            "name": p.get("name"),
            "symbol": p.get("symbol"),
            "category": p.get("category"),
            "tvl_usd": p.get("tvl"),
            "chains": (p.get("chains") or [])[:10],
            "chain_tvls": _top_chain_tvls(p.get("chainTvls") or {}),
            "change_1d_pct": p.get("change_1d"),
            "change_7d_pct": p.get("change_7d"),
            "mcap_usd": p.get("mcap"),
        }
        for p in _fetch(f"{BASE_URL}/protocols")
    ]


def protocols() -> list[dict]:
    return cache.remember(("llama-protocols",), 300, _fetch_protocols)


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


def _fetch_stablecoins() -> list[dict]:
    return [
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


def stablecoins() -> list[dict]:
    return cache.remember(("llama-stablecoins",), 300, _fetch_stablecoins)


def _fetch_chains() -> list[dict]:
    return [
        {"name": c.get("name"), "tvl_usd": c.get("tvl"), "token": c.get("tokenSymbol")} for c in _fetch(f"{BASE_URL}/v2/chains")
    ]


def chains() -> list[dict]:
    return cache.remember(("llama-chains",), 300, _fetch_chains)


def _fetch_summary(kind: str, slug: str) -> dict | None:
    try:
        payload = _fetch(
            f"{BASE_URL}/summary/{kind}/{slug}",
            {"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true"},
        )
    except ChainqError:
        return None
    return {
        "total_24h_usd": payload.get("total24h"),
        "total_7d_usd": payload.get("total7d"),
        "total_30d_usd": payload.get("total30d"),
        "change_1d_pct": payload.get("change_1d"),
    }


def _summary(kind: str, slug: str) -> dict | None:
    return cache.remember(("llama-summary", kind, slug), 300, lambda: _fetch_summary(kind, slug))


def fees(slug: str) -> dict | None:
    return _summary("fees", slug)


def dex_volume(slug: str) -> dict | None:
    return _summary("dexs", slug)


def _fetch_tvl(slug: str) -> float | None:
    try:
        value = _fetch(f"{BASE_URL}/tvl/{slug}")
    except ChainqError:
        return None
    return float(value) if isinstance(value, int | float) else None


def tvl(slug: str) -> float | None:
    return cache.remember(("llama-tvl", slug), 300, lambda: _fetch_tvl(slug))


def _fetch_yield_pools() -> list[dict]:
    return [
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


def yield_pools(projects: tuple[str, ...] | None = None) -> list[dict]:
    pools = cache.remember(("llama-yields",), 300, _fetch_yield_pools)
    if projects:
        return [p for p in pools if p["project"] in projects]
    return pools


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
