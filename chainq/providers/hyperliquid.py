import httpx

from chainq.config import settings
from chainq.errors import ChainqError

INFO_URL = "https://api.hyperliquid.xyz/info"


def info(payload: dict) -> dict | list:
    try:
        resp = httpx.post(INFO_URL, json=payload, timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise ChainqError(f"Hyperliquid request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise ChainqError(f"Hyperliquid returned HTTP {resp.status_code}")
    return resp.json()


def perp_markets() -> list[dict]:
    meta, ctxs = info({"type": "metaAndAssetCtxs"})
    markets = []
    for asset, ctx in zip(meta["universe"], ctxs, strict=False):
        if asset.get("isDelisted"):
            continue
        mark = float(ctx["markPx"])
        prev = float(ctx["prevDayPx"]) if ctx.get("prevDayPx") else None
        funding = float(ctx["funding"])
        oi = float(ctx["openInterest"])
        markets.append(
            {
                "coin": asset["name"],
                "mark_price": mark,
                "oracle_price": float(ctx["oraclePx"]),
                "mid_price": float(ctx["midPx"]) if ctx.get("midPx") else None,
                "change_24h_pct": (mark / prev - 1) * 100 if prev else None,
                "volume_24h_usd": float(ctx["dayNtlVlm"]),
                "open_interest": oi,
                "open_interest_usd": oi * mark,
                "funding_hourly_pct": funding * 100,
                "funding_apr_pct": funding * 24 * 365 * 100,
                "max_leverage": asset.get("maxLeverage"),
            }
        )
    return markets


def clearinghouse_state(address: str) -> dict:
    return info({"type": "clearinghouseState", "user": address})


def spot_markets() -> list[dict]:
    meta, ctxs = info({"type": "spotMetaAndAssetCtxs"})
    token_names = {t["index"]: t["name"] for t in meta["tokens"]}
    ctx_by_coin = {ctx.get("coin"): ctx for ctx in ctxs}
    markets = []
    for pair in meta["universe"]:
        ctx = ctx_by_coin.get(pair["name"])
        if ctx is None:
            continue
        base_idx, quote_idx = pair["tokens"]
        mark = float(ctx["markPx"]) if ctx.get("markPx") else None
        prev = float(ctx["prevDayPx"]) if ctx.get("prevDayPx") else None
        supply = float(ctx["circulatingSupply"]) if ctx.get("circulatingSupply") else None
        markets.append(
            {
                "pair": f"{token_names.get(base_idx)}/{token_names.get(quote_idx)}",
                "base": token_names.get(base_idx),
                "hl_name": pair["name"],
                "canonical": pair.get("isCanonical", False),
                "mark_price": mark,
                "mid_price": float(ctx["midPx"]) if ctx.get("midPx") else None,
                "change_24h_pct": (mark / prev - 1) * 100 if mark and prev else None,
                "volume_24h_usd": float(ctx.get("dayNtlVlm") or 0),
                "circulating_supply": supply,
                "market_cap_usd": mark * supply if mark and supply else None,
            }
        )
    return markets


def spot_balances(address: str) -> list[dict]:
    state = info({"type": "spotClearinghouseState", "user": address})
    return state.get("balances") or []
