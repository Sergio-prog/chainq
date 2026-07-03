import httpx

from chainq import cache
from chainq.config import settings
from chainq.errors import ChainqError

SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"
TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens"
LLAMA_TVL_URL = "https://api.llama.fi/tvl/uniswap"
LLAMA_SUMMARY_URL = "https://api.llama.fi/summary/dexs/uniswap"

V2_FACTORIES = {
    "ethereum": "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
    "arbitrum": "0xf1D7CC64Fb4452F05c498126312eBE29f30Fbcf9",
    "base": "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6",
    "optimism": "0x0c3c1c532F1e39EdF36BE9Fe0bE1410313E074Bf",
    "polygon": "0x9e5A52f57b3038F1B8EeE45F28b3C1967e22799C",
    "bsc": "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6",
    "avalanche": "0x9e5A52f57b3038F1B8EeE45F28b3C1967e22799C",
    "unichain": "0x1f98400000000000000000000000000000000002",
    "worldchain": "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
    "monad": "0x182a927119d56008d921126764bf884221b10f59",
}

V4_STATE_VIEWS = {
    "ethereum": "0x7ffe42c4a5deea5b0fec41c94c136cf115597227",
    "unichain": "0x86e8631a016f9068c3f085faf484ee3f5fdee8f2",
    "optimism": "0xc18a3169788f4f75a170290584eca6395c75ecdb",
    "base": "0xa3c0c9b65bad0b08107aa264b0f3db444b867a71",
    "arbitrum": "0x76fd297e2d437cd7f76d50f01afe6160f86e9990",
    "polygon": "0x5ea1bd7974c8a611cbab0bdcafcb1d9cc9b3ba5a",
    "bsc": "0xd13dd3d6e93f276fafc9db9e6bb47c1180aee0c4",
    "avalanche": "0xc3c9e198c735a4b97e3e683f391ccbdd60b69286",
    "celo": "0xbc21f8720babf4b20d195ee5c6e99c52b76f2bfb",
    "worldchain": "0x51d394718bc09297262e368c1a481217fdeb71eb",
    "soneium": "0x76fd297e2d437cd7f76d50f01afe6160f86e9990",
    "ink": "0x76fd297e2d437cd7f76d50f01afe6160f86e9990",
    "monad": "0x77395f3b2e73ae90843717371294fa97cc419d64",
}

V4_FEE_TICK_SPACING = {100: 1, 500: 10, 3000: 60, 10000: 200}

V2_FACTORY_ABI = [
    {
        "name": "getPair",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "tokenA", "type": "address"}, {"name": "tokenB", "type": "address"}],
        "outputs": [{"name": "", "type": "address"}],
    }
]

V2_PAIR_ABI = [
    {
        "name": "getReserves",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [
            {"name": "reserve0", "type": "uint112"},
            {"name": "reserve1", "type": "uint112"},
            {"name": "blockTimestampLast", "type": "uint32"},
        ],
    },
    {
        "name": "token0",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "name": "token1",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
]

V4_STATE_VIEW_ABI = [
    {
        "name": "getSlot0",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "poolId", "type": "bytes32"}],
        "outputs": [
            {"name": "sqrtPriceX96", "type": "uint160"},
            {"name": "tick", "type": "int24"},
            {"name": "protocolFee", "type": "uint24"},
            {"name": "lpFee", "type": "uint24"},
        ],
    },
    {
        "name": "getLiquidity",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "poolId", "type": "bytes32"}],
        "outputs": [{"name": "", "type": "uint128"}],
    },
]

V3_FACTORIES = {
    "ethereum": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    "arbitrum": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    "optimism": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    "polygon": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    "base": "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
    "bsc": "0xdB1d10011AD0Ff90774D0C6Bb92e5C5c8b4461F7",
    "avalanche": "0x740b1c1de25031C31FF4fC9A62f554A55cdC1baD",
    "unichain": "0x1F98400000000000000000000000000000000003",
    "celo": "0xAfE208a311B21f13EF87E33A90049fC17A7acDEc",
}

V3_FEE_TIERS = (100, 500, 3000, 10000)

V3_FACTORY_ABI = [
    {
        "name": "getPool",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "tokenA", "type": "address"},
            {"name": "tokenB", "type": "address"},
            {"name": "fee", "type": "uint24"},
        ],
        "outputs": [{"name": "", "type": "address"}],
    }
]

V3_POOL_ABI = [
    {
        "name": "slot0",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [
            {"name": "sqrtPriceX96", "type": "uint160"},
            {"name": "tick", "type": "int24"},
            {"name": "observationIndex", "type": "uint16"},
            {"name": "observationCardinality", "type": "uint16"},
            {"name": "observationCardinalityNext", "type": "uint16"},
            {"name": "feeProtocol", "type": "uint8"},
            {"name": "unlocked", "type": "bool"},
        ],
    },
    {
        "name": "liquidity",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint128"}],
    },
    {
        "name": "token0",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "name": "token1",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
]

CHAIN_SLUGS = {
    "ethereum": "ethereum",
    "arbitrum": "arbitrum",
    "base": "base",
    "optimism": "optimism",
    "polygon": "polygon",
    "bsc": "bsc",
    "avalanche": "avalanche",
    "gnosis": "gnosischain",
    "unichain": "unichain",
}


def _get(url: str, params: dict | None = None, ttl: float = 60) -> dict:
    key = cache.key_for("uniswap", url, params)
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        resp = httpx.get(url, params=params or {}, timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise ChainqError(f"request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise ChainqError(f"{url} returned HTTP {resp.status_code}")
    result = resp.json()
    cache.put(key, result, ttl)
    return result


def _pair_row(pair: dict) -> dict:
    labels = pair.get("labels") or []
    return {
        "pair": f"{pair['baseToken']['symbol']}/{pair['quoteToken']['symbol']}",
        "chain": pair.get("chainId"),
        "version": labels[0] if labels else None,
        "price_usd": float(pair["priceUsd"]) if pair.get("priceUsd") else None,
        "change_24h_pct": (pair.get("priceChange") or {}).get("h24"),
        "volume_24h_usd": (pair.get("volume") or {}).get("h24"),
        "liquidity_usd": (pair.get("liquidity") or {}).get("usd"),
        "fdv_usd": pair.get("fdv"),
        "pair_address": pair.get("pairAddress"),
        "url": pair.get("url"),
    }


def token_pairs(address: str) -> list[dict]:
    return _get(f"{TOKEN_URL}/{address}").get("pairs") or []


def search_pairs(query: str) -> list[dict]:
    return _get(SEARCH_URL, {"q": query}).get("pairs") or []


def uniswap_rows(pairs: list[dict], chain_slug: str, quote: str | None = None) -> list[dict]:
    rows = []
    for pair in pairs:
        if pair.get("dexId") != "uniswap" or pair.get("chainId") != chain_slug:
            continue
        symbols = {pair["baseToken"]["symbol"].upper(), pair["quoteToken"]["symbol"].upper()}
        if quote and quote.upper() not in symbols:
            continue
        rows.append(_pair_row(pair))
    return rows


def stats() -> dict:
    summary = _get(
        LLAMA_SUMMARY_URL,
        {"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true"},
        ttl=300,
    )
    tvl = _get(LLAMA_TVL_URL, ttl=300)
    return {
        "protocol": "uniswap",
        "tvl_usd": float(tvl) if isinstance(tvl, int | float) else None,
        "volume_24h_usd": summary.get("total24h"),
        "volume_7d_usd": summary.get("total7d"),
        "volume_30d_usd": summary.get("total30d"),
        "volume_change_1d_pct": summary.get("change_1d"),
        "volume_change_7d_pct": summary.get("change_7d"),
        "source": "defillama",
    }
