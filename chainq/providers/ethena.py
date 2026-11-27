from chainq import cache, http

YIELD_URL = "https://app.ethena.fi/api/yields/protocol-and-staking-yield"


def _fetch_yields() -> dict:
    payload = http.fetch_json("Ethena API", YIELD_URL)

    def value(field: str) -> float | None:
        return (payload.get(field) or {}).get("value")

    return {
        "susde_apy_pct": value("stakingYield"),
        "susde_apy_30d_pct": value("avg30dSusdeYield"),
        "susde_apy_90d_pct": value("avg90dSusdeYield"),
        "protocol_yield_pct": value("protocolYield"),
        "protocol_yield_30d_pct": value("avg30dProtocolYield"),
        "updated": (payload.get("stakingYield") or {}).get("lastUpdated"),
    }


def yields() -> dict:
    return cache.remember(("ethena-yields",), 300, _fetch_yields)
