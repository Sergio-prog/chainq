import pytest

from chainq import cache, catalog, pricing
from chainq.errors import ChainqError

BASECAT = "0xB2000000000000000000004c27f6523082f41D01"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
ATOKEN = "0x4e65fE4DbA92790696d040ac24Aa414708F5c0AB"
PT = "0x1234567890AbcdEF1234567890aBcdef12345678"
YT = "0xABCDEFabcdefABCDEFabcdefABCDEFabcdefABCD"
MINT = "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
NEW_MINT = "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"

COINGECKO_BASE = {
    "tokens": [
        {"chainId": 8453, "address": BASECAT.lower(), "name": "Basecat", "symbol": "BASECAT", "decimals": 18},
        {"chainId": 8453, "address": USDC_BASE.lower(), "name": "USD Coin", "symbol": "USDC", "decimals": 6},
        {"chainId": 8453, "address": "0x" + "1" * 40, "name": "Pepe One", "symbol": "PEPE", "decimals": 18},
        {"chainId": 8453, "address": "0x" + "2" * 40, "name": "Pepe Two", "symbol": "PEPE", "decimals": 18},
        {"chainId": 8453, "address": "not-an-address", "name": "Broken", "symbol": "BAD", "decimals": 18},
        {"chainId": 8453, "address": "0x" + "3" * 40, "name": "Too Many", "symbol": "BIG", "decimals": 99},
    ]
}


def _aave(chain_id, address, symbol, tags):
    return {"chainId": chain_id, "address": address, "name": symbol, "symbol": symbol, "decimals": 6, "tags": tags}


def _pendle(address, symbol, base_type, price=None):
    return {"address": address, "symbol": symbol, "name": symbol, "decimals": "18", "baseType": base_type, "price": price}


AAVE = {
    "tokens": [
        _aave(8453, ATOKEN, "aBasUSDC", ["aTokenV3", "aaveV3"]),
        _aave(8453, USDC_BASE, "USDC", ["underlying"]),
        _aave(1, "0x" + "4" * 40, "aEthX", ["aTokenV3"]),
    ]
}
PENDLE = [
    _pendle(PT.lower(), "PT-sUSDE-25SEP2026", "PT", {"usd": 0.97}),
    _pendle(YT.lower(), "YT-sUSDE-25SEP2026", "YT", {"usd": 0.03}),
    _pendle("0x" + "5" * 40, "PENDLE", "GENERIC"),
]
JUPITER = [
    {"id": MINT, "symbol": "JUP", "name": "Jupiter", "decimals": 6},
    {"id": NEW_MINT, "symbol": "Bonk", "name": "Bonk", "decimals": 5},
    {"id": "bad", "symbol": "BAD", "name": "Bad", "decimals": 6},
]
COINGECKO_SOLANA = {"tokens": [{"address": NEW_MINT, "name": "Bonk", "symbol": "BONK", "decimals": 5}]}


@pytest.fixture
def stubbed_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "BLOB_DIR", tmp_path / "blobs")
    catalog.tokens_for.cache_clear()
    catalog.PENDLE_PRICES.clear()
    payloads = {
        catalog.COINGECKO_LIST_URL.format(platform="base"): COINGECKO_BASE,
        catalog.COINGECKO_LIST_URL.format(platform="solana"): COINGECKO_SOLANA,
        catalog.AAVE_LIST_URL: AAVE,
        catalog.PENDLE_ASSETS_URL.format(chain_id=8453): PENDLE,
        catalog.JUPITER_VERIFIED_URL: JUPITER,
    }
    calls: list[str] = []

    def fake_fetch(url):
        calls.append(url)
        return payloads.get(url)

    monkeypatch.setattr(catalog, "_fetch_json", fake_fetch)
    yield calls
    catalog.tokens_for.cache_clear()
    catalog.PENDLE_PRICES.clear()


def _by_address(network, address):
    return catalog.lookup(network, address)


def test_sources_merge_with_registry_first(stubbed_sources):
    tokens = catalog.tokens_for("base")
    usdc = _by_address("base", USDC_BASE)
    assert usdc.source == "registry"
    assert usdc.name == "USD Coin"
    assert usdc.decimals == 6
    assert usdc.coingecko_id == "usd-coin"
    assert _by_address("base", BASECAT).source == "coingecko"
    assert _by_address("base", ATOKEN).kind == "atoken"
    assert _by_address("base", PT).kind == "pt"
    assert _by_address("base", YT).kind == "yt"
    assert all(t.address.startswith("0x") and len(t.address) == 42 for t in tokens)
    assert catalog.PENDLE_PRICES[("base", PT)] == 0.97


def test_invalid_entries_are_dropped(stubbed_sources):
    symbols = {t.symbol for t in catalog.tokens_for("base")}
    assert "BAD" not in symbols
    assert "BIG" not in symbols
    assert "PENDLE" not in symbols
    assert "aEthX" not in symbols


def test_solana_sources(stubbed_sources):
    tokens = catalog.tokens_for("solana")
    assert _by_address("solana", MINT).source == "registry"
    assert _by_address("solana", NEW_MINT).source == "coingecko"
    assert "bad" not in {t.address for t in tokens}


def test_resolve_symbol_rules(stubbed_sources):
    assert [t.address for t in catalog.resolve_symbol("base", "USDC")] == [USDC_BASE]
    assert catalog.resolve_symbol("base", "basecat")[0].address == BASECAT
    assert len(catalog.resolve_symbol("base", "pepe")) == 2
    assert catalog.resolve_symbol("base", "nope") == []


def test_resolve_one_errors(stubbed_sources):
    assert catalog.resolve_one("base", "basecat").address == BASECAT
    with pytest.raises(ChainqError, match="ambiguous"):
        catalog.resolve_one("base", "pepe")
    with pytest.raises(ChainqError, match="tokens search"):
        catalog.resolve_one("base", "nope")


def test_search_orders_exact_then_registry_then_rest(stubbed_sources):
    rows = catalog.search("usdc", "base")
    assert rows[0].address == USDC_BASE
    assert rows[1].address == ATOKEN
    assert [t.symbol for t in catalog.search("pepe", "base")] == ["PEPE", "PEPE"]


def test_stale_blob_used_when_fetch_fails(stubbed_sources, monkeypatch):
    catalog.tokens_for("base")
    catalog.tokens_for.cache_clear()
    monkeypatch.setattr(catalog, "_fetch_json", lambda url: None)
    monkeypatch.setattr(catalog, "CATALOG_TTL", -1)
    assert _by_address("base", BASECAT) is not None


def test_no_cache_and_fetch_failure_degrades_to_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "BLOB_DIR", tmp_path / "blobs")
    monkeypatch.setattr(catalog, "_fetch_json", lambda url: None)
    catalog.tokens_for.cache_clear()
    try:
        tokens = catalog.tokens_for("base")
        assert tokens and all(t.source == "registry" for t in tokens)
        assert all(t.decimals is None for t in tokens)
    finally:
        catalog.tokens_for.cache_clear()


def test_status_and_refresh(stubbed_sources):
    rows = catalog.status(["base"])
    assert rows[0]["tokens"] == len(catalog.tokens_for("base"))
    assert rows[0]["sources"]["registry"] == 5
    assert rows[0]["missing_sources"] == 0
    fetched_before = len(stubbed_sources)
    catalog.refresh(["base"])
    catalog.tokens_for("base")
    assert len(stubbed_sources) > fetched_before


def test_pricing_cascade(monkeypatch):
    monkeypatch.setattr(pricing.coingecko, "simple_price", lambda ids: {"usd-coin": {"usd": 1.0}})
    monkeypatch.setattr(
        pricing.defillama, "token_prices", lambda pairs: {("base", BASECAT): {"price": 0.04, "confidence": 0.99}}
    )
    monkeypatch.setattr(
        pricing.jupiter,
        "prices",
        lambda mints: {MINT: {"price": 0.5, "liquidity": 5e6}, NEW_MINT: {"price": 1.0, "liquidity": 10}},
    )
    monkeypatch.setattr(pricing.catalog, "PENDLE_PRICES", {("base", PT): 0.97})
    monkeypatch.setattr(
        pricing.uniswap,
        "token_pairs_batch",
        lambda slug, addresses: [
            {"baseToken": {"address": YT.lower()}, "liquidity": {"usd": 5000}, "priceUsd": "0.02"},
            {"baseToken": {"address": YT.lower()}, "liquidity": {"usd": 900}, "priceUsd": "9"},
            {"baseToken": {"address": ATOKEN.lower()}, "liquidity": {"usd": 500}, "priceUsd": "1"},
        ],
    )
    assets = [
        {"network": "base", "symbol": "USDC", "token_address": USDC_BASE, "amount": "2", "coingecko_id": "usd-coin"},
        {"network": "base", "symbol": "BASECAT", "token_address": BASECAT, "amount": "100"},
        {"network": "solana", "symbol": "JUP", "token_address": MINT, "amount": "4"},
        {"network": "solana", "symbol": "BONK", "token_address": NEW_MINT, "amount": "4"},
        {"network": "base", "symbol": "PT", "token_address": PT, "amount": "10"},
        {"network": "base", "symbol": "YT", "token_address": YT, "amount": "10"},
        {"network": "base", "symbol": "aUSDC", "token_address": ATOKEN, "amount": "1"},
        {"network": "solana", "symbol": "????", "token_address": "x", "amount": "1", "kind": "unknown"},
    ]
    pricing.price_assets(assets)
    by_symbol = {a["symbol"]: a for a in assets}
    assert (by_symbol["USDC"]["price_source"], by_symbol["USDC"]["value_usd"]) == ("coingecko", 2.0)
    assert (by_symbol["BASECAT"]["price_source"], by_symbol["BASECAT"]["value_usd"]) == ("defillama", 4.0)
    assert by_symbol["JUP"]["price_source"] == "jupiter"
    assert by_symbol["BONK"]["price_usd"] is None
    assert by_symbol["PT"]["price_source"] == "pendle"
    assert (by_symbol["YT"]["price_source"], by_symbol["YT"]["price_usd"]) == ("dexscreener", 0.02)
    assert by_symbol["aUSDC"]["price_usd"] is None
    assert by_symbol["????"]["price_usd"] is None
    assert all("coingecko_id" not in a for a in assets)


def test_pricing_survives_provider_failures(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(pricing.coingecko, "simple_price", boom)
    monkeypatch.setattr(pricing.defillama, "token_prices", boom)
    monkeypatch.setattr(pricing.jupiter, "prices", boom)
    monkeypatch.setattr(pricing.uniswap, "token_pairs_batch", boom)
    assets = [{"network": "base", "symbol": "X", "token_address": BASECAT, "amount": "1", "coingecko_id": "x"}]
    pricing.price_assets(assets)
    assert assets[0]["price_usd"] is None
    assert assets[0]["value_usd"] is None
