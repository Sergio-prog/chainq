from chainq import catalog
from chainq.providers import coingecko, defillama, jupiter, uniswap
from chainq.providers.uniswap_data import CHAIN_SLUGS

DEX_MIN_LIQUIDITY_USD = 1000
PENDLE_FRESH_SECONDS = 3600
DEXSCREENER_SLUGS = {**CHAIN_SLUGS, "solana": "solana", "tron": "tron"}


def _unpriced(assets: list[dict]) -> list[dict]:
    return [a for a in assets if a.get("price_usd") is None and a.get("kind") != "unknown"]


def _apply(asset: dict, price: float | None, source: str | None) -> None:
    asset["price_usd"] = price
    asset["price_source"] = source
    asset["value_usd"] = float(asset["amount"]) * price if price is not None else None


def _price_coingecko(assets: list[dict]) -> None:
    ids = sorted({a["coingecko_id"] for a in assets if a.get("coingecko_id")})
    prices: dict = {}
    if ids:
        try:
            prices = coingecko.simple_price(ids)
        except Exception:
            prices = {}
    for asset in assets:
        price = (prices.get(asset.get("coingecko_id")) or {}).get("usd")
        _apply(asset, price, "coingecko" if price is not None else None)


def _defillama_key(asset: dict) -> tuple[str, str] | None:
    if asset.get("token_address"):
        return asset["network"], asset["token_address"]
    if asset.get("coingecko_id"):
        return "coingecko", asset["coingecko_id"]
    return None


def _price_defillama(assets: list[dict]) -> None:
    targets = [(a, key) for a in assets if (key := _defillama_key(a))]
    if not targets:
        return
    try:
        prices = defillama.token_prices(sorted({key for _, key in targets}))
    except Exception:
        return
    for asset, key in targets:
        hit = prices.get(key)
        if hit:
            _apply(asset, hit["price"], "defillama")


def native_price(coingecko_id: str) -> float | None:
    price = coingecko.try_price_usd(coingecko_id)
    if price is not None:
        return price
    try:
        hit = defillama.token_prices([("coingecko", coingecko_id)]).get(("coingecko", coingecko_id))
    except Exception:
        return None
    return hit["price"] if hit else None


def _price_jupiter(assets: list[dict]) -> None:
    targets = [a for a in assets if a["network"] == "solana" and a.get("token_address")]
    if not targets:
        return
    try:
        prices = jupiter.prices([a["token_address"] for a in targets])
    except Exception:
        return
    for asset in targets:
        hit = prices.get(asset["token_address"])
        if hit and hit["liquidity"] >= DEX_MIN_LIQUIDITY_USD:
            _apply(asset, hit["price"], "jupiter")


def _price_pendle(assets: list[dict]) -> None:
    for asset in assets:
        price = catalog.PENDLE_PRICES.get((asset["network"], asset.get("token_address")))
        if price is not None:
            _apply(asset, price, "pendle")


def _price_dexscreener(assets: list[dict]) -> None:
    by_network: dict[str, list[dict]] = {}
    for asset in assets:
        if asset.get("token_address") and DEXSCREENER_SLUGS.get(asset["network"]):
            by_network.setdefault(asset["network"], []).append(asset)
    for network_key, targets in by_network.items():
        try:
            pairs = uniswap.token_pairs_batch(DEXSCREENER_SLUGS[network_key], [a["token_address"] for a in targets])
        except Exception:
            continue
        best: dict[str, dict] = {}
        for pair in pairs:
            token = ((pair.get("baseToken") or {}).get("address") or "").lower()
            liquidity = (pair.get("liquidity") or {}).get("usd") or 0
            current = ((best.get(token) or {}).get("liquidity") or {}).get("usd") or 0
            if liquidity >= DEX_MIN_LIQUIDITY_USD and liquidity > current:
                best[token] = pair
        for asset in targets:
            pair = best.get(asset["token_address"].lower())
            if pair and pair.get("priceUsd"):
                _apply(asset, float(pair["priceUsd"]), "dexscreener")


def price_assets(assets: list[dict]) -> list[dict]:
    for asset in assets:
        asset.setdefault("price_usd", None)
        asset.setdefault("price_source", None)
        asset.setdefault("value_usd", None)
    _price_coingecko([a for a in assets if a.get("coingecko_id")])
    _price_jupiter(_unpriced(assets))
    _price_defillama(_unpriced(assets))
    _price_pendle(_unpriced(assets))
    _price_dexscreener(_unpriced(assets))
    for asset in assets:
        asset.pop("coingecko_id", None)
    return assets
