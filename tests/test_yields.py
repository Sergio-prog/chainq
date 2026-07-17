import sys
from inspect import signature

from chainq.commands.yields import _filter_rows, _merge_results, _row, _yield_lines, yields


def opportunity(
    market: str,
    symbol: str,
    apy_pct: float,
    tvl_usd: float | None = 100,
    protocol: str = "test",
) -> dict:
    return _row(protocol, "ethereum", market, symbol, apy_pct, None, "lending", tvl_usd)


def test_default_sort_and_minimum_tvl():
    parameters = signature(yields).parameters

    assert parameters["sort"].default == "tvl"
    assert parameters["min_tvl"].default == 1_000_000


def test_asset_filter_matches_symbol_and_market_name():
    rows = [opportunity("USDC Core", "usdc", 3), opportunity("ETH/USDC", "weth", 4), opportunity("DAI", "dai", 5)]

    assert _filter_rows(rows, "USDC", None, 0, "apy", 15) == [rows[1], rows[0]]


def test_eth_asset_matches_token_family_without_matching_ethereum():
    rows = [
        opportunity("DAI [Ethereum]", "dai", 10),
        opportunity("WETH [Ethereum]", "weth", 8),
        opportunity("stETH", "steth", 6),
        opportunity("ETH/USDC", "eth", 4),
    ]

    assert _filter_rows(rows, "eth", None, 0, "apy", 15) == rows[1:]


def test_asset_filter_respects_fixed_staking_symbols():
    rows = [
        opportunity("sUSDS", "usds", 4, protocol="sky"),
        opportunity("sUSDe", "usde", 5, protocol="ethena"),
        opportunity("stETH", "steth", 3, protocol="lido"),
    ]

    assert _filter_rows(rows, "usdc", None, 0, "apy", 15) == []
    assert _filter_rows(rows, "usde", None, 0, "apy", 15) == [rows[1]]
    assert _filter_rows(rows, "eth", None, 0, "apy", 15) == [rows[2]]


def test_apy_sorting_min_tvl_and_limit_are_applied_in_order():
    rows = [
        opportunity("low tvl", "a", 20, 5),
        opportunity("second", "b", 8, 100),
        opportunity("first", "c", 10, 100),
        opportunity("third", "d", 6, 100),
    ]

    assert _filter_rows(rows, None, None, 10, "apy", 2) == [rows[2], rows[1]]


def test_tvl_sorting_is_descending():
    rows = [
        opportunity("highest apy", "a", 20, 2_000_000),
        opportunity("highest tvl", "b", 5, 10_000_000),
        opportunity("middle tvl", "c", 8, 5_000_000),
    ]

    assert _filter_rows(rows, None, None, 1_000_000, "tvl", 15) == [rows[1], rows[2], rows[0]]


def test_text_output_uses_aligned_columns():
    rows = [
        opportunity("short", "a", 3.2, 2_000_000_000, protocol="aave"),
        opportunity("long market", "b", 12.34, 1_500_000, protocol="morpho"),
    ]
    rows[1]["type"] = "vault"
    rows[1]["network"] = "base"

    assert _yield_lines(rows) == [
        " 3.20%  lending  aave short          (ethereum)  tvl $2.00B",
        "12.34%  vault    morpho long market  (base)      tvl $1.50M",
    ]


def test_text_output_truncates_long_markets():
    row = opportunity("x" * 100, "a", 3.2, 2_000_000_000, protocol="aave")

    line = _yield_lines([row])[0]

    assert "…" in line
    assert "x" * 49 not in line


def test_text_output_uses_showcase_colors(monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    row = opportunity("USDC [Ethereum]", "usdc", 3.28, 2_130_000_000, protocol="aave")

    line = _yield_lines([row])[0]

    assert line.startswith("\033[32m3.28%\033[0m")
    assert "\033[2mlending\033[0m" in line
    assert "\033[2m(ethereum)\033[0m" in line
    assert "\033[2mtvl\033[0m" in line
    assert line.endswith("\033[1m$2.13B\033[0m")


def test_asset_filter_respects_limit():
    rows = [opportunity(f"USDC {index}", "usdc", index) for index in range(5)]

    assert _filter_rows(rows, "usdc", None, 0, "apy", 2) == list(reversed(rows))[:2]


def test_failing_source_becomes_verbose_note():
    row = opportunity("USDC", "usdc", 4)

    rows, errors = _merge_results([([row], None), (None, "morpho ethereum: timeout")])

    assert rows == [row]
    assert errors == ["morpho ethereum: timeout"]
