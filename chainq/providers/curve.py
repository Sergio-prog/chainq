import httpx

from chainq import cache, http
from chainq.errors import ChainqError
from chainq.providers import coingecko, defillama

BASE_URL = "https://api.curve.finance/v1"

CHAIN_IDS = {
    "ethereum": "ethereum",
    "arbitrum": "arbitrum",
    "base": "base",
    "optimism": "optimism",
    "polygon": "polygon",
    "avalanche": "avalanche",
    "bsc": "bsc",
    "gnosis": "xdai",
    "celo": "celo",
    "mantle": "mantle",
    "sonic": "sonic",
    "zksync": "zksync",
    "hyperevm": "hyperliquid",
}


def _fetch(path: str) -> dict:
    key = cache.key_for("curve", path)
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        resp = http.get(f"{BASE_URL}{path}")
    except httpx.HTTPError as exc:
        raise ChainqError(f"Curve API request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise ChainqError(f"Curve API returned HTTP {resp.status_code} for {path}")
    payload = resp.json()
    if not payload.get("success"):
        raise ChainqError(f"Curve API returned an unsuccessful response for {path}")
    data = payload.get("data") or {}
    cache.put(key, data, ttl=120)
    return data


def chain_id(network_key: str) -> str:
    chain = CHAIN_IDS.get(network_key)
    if chain is None:
        known = ", ".join(sorted(CHAIN_IDS))
        raise ChainqError(f"Curve has no deployment mapping for '{network_key}' (known: {known})")
    return chain


def pools(network_key: str) -> list[dict]:
    chain = chain_id(network_key)
    pool_data = _fetch(f"/getPools/big/{chain}").get("poolData") or []
    volumes = {
        (v.get("address") or "").lower(): v
        for v in _fetch(f"/getVolumes/{chain}").get("pools") or []
    }
    rows = []
    for p in pool_data:
        if p.get("isBroken"):
            continue
        volume = volumes.get((p.get("address") or "").lower()) or {}
        gauge_apy = p.get("gaugeCrvApy") or []
        rows.append(
            {
                "name": p.get("name"),
                "symbol": p.get("symbol"),
                "coins": [c.get("symbol") for c in p.get("coins") or []],
                "pool_type": p.get("assetTypeName"),
                "tvl_usd": p.get("usdTotal"),
                "volume_24h_usd": volume.get("volumeUSD"),
                "apy_base_pct": volume.get("latestDailyApyPcent"),
                "apy_crv_min_pct": gauge_apy[0] if len(gauge_apy) > 0 else None,
                "apy_crv_max_pct": gauge_apy[1] if len(gauge_apy) > 1 else None,
                "address": p.get("address"),
            }
        )
    return rows


def stats() -> dict:
    tvl = defillama.tvl("curve-dex")
    volume = defillama.dex_volume("curve-dex") or {}
    fees = defillama.fees("curve-dex") or {}
    crvusd = defillama.tvl("crvusd")
    return {
        "tvl_usd": tvl,
        "volume_24h_usd": volume.get("total_24h_usd"),
        "volume_7d_usd": volume.get("total_7d_usd"),
        "fees_24h_usd": fees.get("total_24h_usd"),
        "fees_7d_usd": fees.get("total_7d_usd"),
        "crvusd_tvl_usd": crvusd,
        "crv_price_usd": coingecko.try_price_usd("curve-dao-token"),
    }
