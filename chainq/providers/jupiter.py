from chainq import cache, http
from chainq.errors import ChainqError

PRICE_URL = "https://lite-api.jup.ag/price/v3"
PRICE_BATCH = 50


def _fetch_batch(batch: list[str]) -> dict:
    return cache.remember(
        ("jupiter-price", batch), 60, lambda: http.fetch_json("Jupiter", PRICE_URL, params={"ids": ",".join(batch)})
    )


def prices(mints: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    unique = sorted(set(mints))
    for start in range(0, len(unique), PRICE_BATCH):
        try:
            payload = _fetch_batch(unique[start : start + PRICE_BATCH])
        except ChainqError:
            continue
        for mint, entry in (payload or {}).items():
            price = (entry or {}).get("usdPrice")
            if isinstance(price, (int, float)) and price > 0:
                result[mint] = {"price": float(price), "liquidity": float((entry or {}).get("liquidity") or 0)}
    return result
