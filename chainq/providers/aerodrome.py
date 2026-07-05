from chainq.providers import coingecko, defillama

AMM_SLUG = "aerodrome-v1"
CL_SLUG = "aerodrome-slipstream"
PARENT_SLUG = "aerodrome"
AERO_COINGECKO_ID = "aerodrome-finance"

PROJECT_ALIASES = {
    "all": (AMM_SLUG, CL_SLUG),
    "v1": (AMM_SLUG,),
    "amm": (AMM_SLUG,),
    "cl": (CL_SLUG,),
    "slipstream": (CL_SLUG,),
}


def stats() -> dict:
    amm_tvl = defillama.tvl(AMM_SLUG) or 0
    cl_tvl = defillama.tvl(CL_SLUG) or 0
    volume = defillama.dex_volume(PARENT_SLUG) or {}
    fee = defillama.fees(PARENT_SLUG) or {}
    return {
        "tvl_usd": amm_tvl + cl_tvl,
        "tvl_amm_usd": amm_tvl,
        "tvl_cl_usd": cl_tvl,
        "volume_24h_usd": volume.get("total_24h_usd"),
        "volume_7d_usd": volume.get("total_7d_usd"),
        "fees_24h_usd": fee.get("total_24h_usd"),
        "fees_7d_usd": fee.get("total_7d_usd"),
        "aero_price_usd": coingecko.try_price_usd(AERO_COINGECKO_ID),
    }


def top_pools(projects: tuple[str, ...], limit: int) -> list[dict]:
    pools = defillama.yield_pools(projects)
    pools.sort(key=lambda p: p["tvl_usd"] or 0, reverse=True)
    return pools[:limit]
