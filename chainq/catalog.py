from dataclasses import dataclass, replace
from functools import cache as memoize

from web3 import Web3

from chainq import __version__, cache, http
from chainq.config import settings
from chainq.errors import ChainqError
from chainq.networks import NETWORKS
from chainq.providers.coingecko_data import PLATFORM_IDS, SYMBOL_TO_ID
from chainq.solana import is_solana_address
from chainq.tokens import SOLANA_TOKENS, TOKENS

COINGECKO_LIST_URL = "https://tokens.coingecko.com/{platform}/all.json"
AAVE_LIST_URL = "https://raw.githubusercontent.com/bgd-labs/aave-address-book/main/tokenlist.json"
PENDLE_ASSETS_URL = "https://api-v2.pendle.finance/core/v1/{chain_id}/assets/all"
PENDLE_CHAIN_IDS = frozenset({1, 56, 143, 999, 4663, 8453, 9745, 42161, 10, 146, 5000, 80094})
JUPITER_VERIFIED_URL = "https://lite-api.jup.ag/tokens/v2/tag?query=verified"
CATALOG_TTL = 86400
MAX_DECIMALS = 36

AAVE_KINDS = {"aTokenV3": "atoken", "aTokenV2": "atoken", "stataToken": "stata", "staticAT": "stata"}
PENDLE_KINDS = {"PT": "pt", "YT": "yt", "SY": "sy", "PENDLE_LP": "lp"}


@dataclass(frozen=True)
class CatalogToken:
    network: str
    address: str
    symbol: str
    name: str
    decimals: int | None
    source: str
    kind: str = "token"
    coingecko_id: str | None = None

    def as_dict(self) -> dict:
        return {
            "network": self.network,
            "symbol": self.symbol,
            "name": self.name,
            "address": self.address,
            "decimals": self.decimals,
            "kind": self.kind,
            "source": self.source,
        }


PENDLE_PRICES: dict[tuple[str, str], float] = {}


def _fetch_json(url: str) -> object | None:
    try:
        resp = http.get(url, headers={"User-Agent": f"chainq/{__version__}"}, timeout=settings.http_timeout)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except Exception:
        return None


def _load_source(name: str, url: str) -> object | None:
    fresh = cache.get_blob(name, CATALOG_TTL)
    if fresh is not None:
        return fresh
    fetched = _fetch_json(url)
    if fetched is not None:
        cache.put_blob(name, fetched)
        return fetched
    return cache.get_blob(name)


def _checksum(address: object) -> str | None:
    if not isinstance(address, str) or not address.startswith("0x") or len(address) != 42:
        return None
    try:
        return Web3.to_checksum_address(address)
    except Exception:
        return None


def _decimals(value: object) -> int | None:
    try:
        decimals = int(value)
    except (TypeError, ValueError):
        return None
    return decimals if 0 <= decimals <= MAX_DECIMALS else None


def _coingecko_tokens(network_key: str) -> list[CatalogToken]:
    platform = PLATFORM_IDS.get(network_key)
    if platform is None:
        return []
    data = _load_source(f"catalog-coingecko-{network_key}", COINGECKO_LIST_URL.format(platform=platform))
    entries = (data or {}).get("tokens") if isinstance(data, dict) else None
    tokens = []
    for entry in entries or []:
        address = entry.get("address") if network_key == "solana" else _checksum(entry.get("address"))
        decimals = _decimals(entry.get("decimals"))
        if not address or decimals is None or not entry.get("symbol"):
            continue
        if network_key == "solana" and not is_solana_address(address):
            continue
        tokens.append(
            CatalogToken(network_key, address, str(entry["symbol"]), str(entry.get("name") or ""), decimals, "coingecko")
        )
    return tokens


def _aave_tokens(network_key: str) -> list[CatalogToken]:
    data = _load_source("catalog-aave", AAVE_LIST_URL)
    entries = (data or {}).get("tokens") if isinstance(data, dict) else None
    chain_id = NETWORKS[network_key].chain_id
    tokens = []
    for entry in entries or []:
        if entry.get("chainId") != chain_id:
            continue
        kind = next((AAVE_KINDS[tag] for tag in entry.get("tags") or [] if tag in AAVE_KINDS), None)
        address = _checksum(entry.get("address"))
        decimals = _decimals(entry.get("decimals"))
        if kind is None or not address or decimals is None or not entry.get("symbol"):
            continue
        tokens.append(CatalogToken(network_key, address, entry["symbol"], entry.get("name") or "", decimals, "aave", kind))
    return tokens


def _pendle_tokens(network_key: str) -> list[CatalogToken]:
    chain_id = NETWORKS[network_key].chain_id
    if chain_id not in PENDLE_CHAIN_IDS:
        return []
    data = _load_source(f"catalog-pendle-{chain_id}", PENDLE_ASSETS_URL.format(chain_id=chain_id))
    tokens = []
    for entry in data if isinstance(data, list) else []:
        kind = PENDLE_KINDS.get(entry.get("baseType"))
        address = _checksum(entry.get("address"))
        decimals = _decimals(entry.get("decimals"))
        if kind is None or not address or decimals is None or not entry.get("symbol"):
            continue
        price = (entry.get("price") or {}).get("usd")
        if isinstance(price, (int, float)) and price > 0:
            PENDLE_PRICES[(network_key, address)] = float(price)
        tokens.append(CatalogToken(network_key, address, entry["symbol"], entry.get("name") or "", decimals, "pendle", kind))
    return tokens


def _jupiter_tokens() -> list[CatalogToken]:
    data = _load_source("catalog-jupiter", JUPITER_VERIFIED_URL)
    tokens = []
    for entry in data if isinstance(data, list) else []:
        mint = entry.get("id")
        decimals = _decimals(entry.get("decimals"))
        if not isinstance(mint, str) or not is_solana_address(mint) or decimals is None or not entry.get("symbol"):
            continue
        tokens.append(CatalogToken("solana", mint, entry["symbol"], entry.get("name") or "", decimals, "jupiter"))
    return tokens


def _registry_tokens(network_key: str) -> list[CatalogToken]:
    if network_key == "solana":
        entries = SOLANA_TOKENS.items()
    else:
        entries = TOKENS.get(network_key, {}).items()
    return [
        CatalogToken(network_key, address, symbol.upper(), "", None, "registry", coingecko_id=SYMBOL_TO_ID.get(symbol))
        for symbol, address in entries
    ]


def _merge(kept: CatalogToken, other: CatalogToken) -> CatalogToken:
    if kept.decimals is not None and kept.name:
        return kept
    return replace(
        kept,
        name=kept.name or other.name,
        decimals=kept.decimals if kept.decimals is not None else other.decimals,
    )


def _dedupe(tokens: list[CatalogToken]) -> list[CatalogToken]:
    unique: dict[str, CatalogToken] = {}
    for token in tokens:
        key = token.address if token.network == "solana" else token.address.lower()
        unique[key] = _merge(unique[key], token) if key in unique else token
    return list(unique.values())


@memoize
def tokens_for(network_key: str) -> tuple[CatalogToken, ...]:
    if network_key not in NETWORKS:
        return ()
    if network_key == "solana":
        return tuple(_dedupe(_registry_tokens("solana") + _coingecko_tokens("solana") + _jupiter_tokens()))
    return tuple(
        _dedupe(
            _registry_tokens(network_key)
            + _coingecko_tokens(network_key)
            + _aave_tokens(network_key)
            + _pendle_tokens(network_key)
        )
    )


def lookup(network_key: str, address: str) -> CatalogToken | None:
    wanted = address if network_key == "solana" else address.lower()
    for token in tokens_for(network_key):
        candidate = token.address if network_key == "solana" else token.address.lower()
        if candidate == wanted:
            return token
    return None


def resolve_symbol(network_key: str, symbol: str) -> list[CatalogToken]:
    wanted = symbol.strip().lower()
    matches = [t for t in tokens_for(network_key) if t.symbol.lower() == wanted]
    curated = [t for t in matches if t.source == "registry"]
    return curated[:1] if curated else matches


def resolve_one(network_key: str, symbol: str) -> CatalogToken:
    matches = resolve_symbol(network_key, symbol)
    network = NETWORKS[network_key]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ChainqError(
            f"unknown token '{symbol}' on {network.name}; try `chainq tokens search {symbol}` "
            f"or pass the {'mint' if network.kind == 'solana' else 'contract'} address instead"
        )
    listed = ", ".join(f"{t.address} ({t.name or t.symbol}, {t.source})" for t in matches[:5])
    more = f" and {len(matches) - 5} more" if len(matches) > 5 else ""
    raise ChainqError(f"'{symbol}' is ambiguous on {network.name}: {listed}{more} — pass the address instead")


def search(query: str, network_key: str | None = None, limit: int = 20) -> list[CatalogToken]:
    q = query.strip().lower()
    keys = [network_key] if network_key else list(NETWORKS)
    exact, curated, rest = [], [], []
    for key in keys:
        for token in tokens_for(key):
            symbol = token.symbol.lower()
            if symbol == q:
                (curated if token.source == "registry" else exact).append(token)
            elif q in symbol or q in token.name.lower():
                rest.append(token)
    return (curated + exact + rest)[:limit]


def _blob_names(network_key: str) -> list[str]:
    if network_key == "solana":
        return ["catalog-coingecko-solana", "catalog-jupiter"]
    names = [f"catalog-coingecko-{network_key}", "catalog-aave"]
    chain_id = NETWORKS[network_key].chain_id
    if chain_id in PENDLE_CHAIN_IDS:
        names.append(f"catalog-pendle-{chain_id}")
    return names


def refresh(network_keys: list[str]) -> None:
    for key in network_keys:
        for name in _blob_names(key):
            cache.drop_blob(name)
    tokens_for.cache_clear()


def status(network_keys: list[str]) -> list[dict]:
    rows = []
    for key in network_keys:
        tokens = tokens_for(key)
        ages = [cache.blob_age(name) for name in _blob_names(key)]
        known = [age for age in ages if age is not None]
        sources: dict[str, int] = {}
        for token in tokens:
            sources[token.source] = sources.get(token.source, 0) + 1
        rows.append(
            {
                "network": key,
                "tokens": len(tokens),
                "sources": sources,
                "age_hours": round(max(known) / 3600, 1) if known else None,
                "stale": bool(known) and max(known) > CATALOG_TTL,
                "missing_sources": sum(1 for age in ages if age is None),
            }
        )
    return rows
