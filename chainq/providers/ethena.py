import httpx

from chainq import cache, http
from chainq.config import settings
from chainq.errors import ChainqError

YIELD_URL = "https://app.ethena.fi/api/yields/protocol-and-staking-yield"


def yields() -> dict:
    key = cache.key_for("ethena-yields")
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        resp = http.get(YIELD_URL, timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise ChainqError(f"Ethena API request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise ChainqError(f"Ethena API returned HTTP {resp.status_code}")
    payload = resp.json()

    def value(field: str) -> float | None:
        return (payload.get(field) or {}).get("value")

    result = {
        "susde_apy_pct": value("stakingYield"),
        "susde_apy_30d_pct": value("avg30dSusdeYield"),
        "susde_apy_90d_pct": value("avg90dSusdeYield"),
        "protocol_yield_pct": value("protocolYield"),
        "protocol_yield_30d_pct": value("avg30dProtocolYield"),
        "updated": (payload.get("stakingYield") or {}).get("lastUpdated"),
    }
    cache.put(key, result, ttl=300)
    return result
