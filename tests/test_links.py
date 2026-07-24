import pytest

from chainq import links
from chainq.errors import ChainqError


def test_default_provider_is_tradingview():
    assert links.parse_providers(None) == ["tradingview"]
    assert links.parse_providers("") == ["tradingview"]


def test_parse_multiple_and_dedupes():
    assert links.parse_providers("binance, coingecko, binance") == ["binance", "coingecko"]


def test_parse_is_case_insensitive():
    assert links.parse_providers("TradingView") == ["tradingview"]


def test_invalid_provider_raises():
    with pytest.raises(ChainqError) as exc:
        links.parse_providers("tradingview,nope")
    assert "nope" in str(exc.value)


def test_asset_links_urls():
    result = links.asset_links("eth", "ethereum", ["tradingview", "binance", "coingecko"])
    assert result == {
        "tradingview": "https://www.tradingview.com/symbols/ETHUSD/",
        "binance": "https://www.binance.com/en/trade/ETH_USDT",
        "coingecko": "https://www.coingecko.com/en/coins/ethereum",
    }


def test_coingecko_link_skipped_without_id():
    result = links.asset_links("eth", None, ["tradingview", "coingecko"])
    assert "coingecko" not in result
    assert result["tradingview"].endswith("ETHUSD/")


def test_configured_providers_uses_override(monkeypatch):
    monkeypatch.setattr(links.settings, "asset_links", "coingecko")
    assert links.configured_providers() == ["coingecko"]
    assert links.configured_providers("binance") == ["binance"]
