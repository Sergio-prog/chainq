import httpx

from chainq import cache, http

PRICE_URL = "https://lite-api.jup.ag/price/v3"
PRICE_BATCH = 50


def prices(mints: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    unique = sorted(set(mints))
    for start in range(0, len(unique), PRICE_BATCH):
        batch = unique[start : start + PRICE_BATCH]
        cache_key = cache.key_for("jupiter-price", batch)
        payload = cache.get(cache_key)
        if payload is None:
            try:
                resp = http.get(PRICE_URL, params={"ids": ",".join(batch)})
            except httpx.HTTPError:
                continue
            if resp.status_code != 200:
                continue
            payload = resp.json()
            cache.put(cache_key, payload, 60)
        for mint, entry in (payload or {}).items():
            price = (entry or {}).get("usdPrice")
            if isinstance(price, (int, float)) and price > 0:
                result[mint] = {"price": float(price), "liquidity": float((entry or {}).get("liquidity") or 0)}
    return result
