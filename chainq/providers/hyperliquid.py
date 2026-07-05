import httpx

from chainq import http
from chainq.config import settings
from chainq.errors import ChainqError

INFO_URL = "https://api.hyperliquid.xyz/info"


def info(payload: dict) -> dict | list:
    try:
        resp = http.post(INFO_URL, json=payload, timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise ChainqError(f"Hyperliquid request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise ChainqError(f"Hyperliquid returned HTTP {resp.status_code}")
    return resp.json()


def perp_markets(dex: str = "") -> list[dict]:
    payload: dict = {"type": "metaAndAssetCtxs"}
    if dex:
        payload["dex"] = dex
    response = info(payload)
    if response is None:
        raise ChainqError(f"unknown Hyperliquid perp dex '{dex}' (list them with `hl dexs`)")
    meta, ctxs = response
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


def funding_history(coin: str, start_time_ms: int, dex: str = "") -> list[dict]:
    payload: dict = {"type": "fundingHistory", "coin": coin, "startTime": start_time_ms}
    if dex:
        payload["dex"] = dex
    return info(payload) or []


def perp_dexs() -> list[dict]:
    return [dex for dex in info({"type": "perpDexs"}) if dex]


def outcome_meta() -> list[dict]:
    return info({"type": "outcomeMeta"}).get("outcomes") or []


def all_mids() -> dict:
    return info({"type": "allMids"})


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
