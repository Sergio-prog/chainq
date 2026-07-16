from chainq.commands.yields import _filter_rows, _merge_results, _row


def opportunity(
    market: str,
    symbol: str,
    apy_pct: float,
    tvl_usd: float | None = 100,
    protocol: str = "test",
) -> dict:
    return _row(protocol, "ethereum", market, symbol, apy_pct, None, "lending", tvl_usd)


def test_asset_filter_matches_symbol_and_market_name():
    rows = [opportunity("USDC Core", "usdc", 3), opportunity("ETH/USDC", "weth", 4), opportunity("DAI", "dai", 5)]

    assert _filter_rows(rows, "USDC", None, 0, 15) == [rows[1], rows[0]]


def test_eth_asset_matches_token_family_without_matching_ethereum():
    rows = [
        opportunity("DAI [Ethereum]", "dai", 10),
        opportunity("WETH [Ethereum]", "weth", 8),
        opportunity("stETH", "steth", 6),
        opportunity("ETH/USDC", "eth", 4),
    ]

    assert _filter_rows(rows, "eth", None, 0, 15) == rows[1:]


def test_asset_filter_respects_fixed_staking_symbols():
    rows = [
        opportunity("sUSDS", "usds", 4, protocol="sky"),
        opportunity("sUSDe", "usde", 5, protocol="ethena"),
        opportunity("stETH", "steth", 3, protocol="lido"),
    ]

    assert _filter_rows(rows, "usdc", None, 0, 15) == []
    assert _filter_rows(rows, "usde", None, 0, 15) == [rows[1]]
    assert _filter_rows(rows, "eth", None, 0, 15) == [rows[2]]


def test_sorting_min_tvl_and_limit_are_applied_in_order():
    rows = [
        opportunity("low tvl", "a", 20, 5),
        opportunity("second", "b", 8, 100),
        opportunity("first", "c", 10, 100),
        opportunity("third", "d", 6, 100),
    ]

    assert _filter_rows(rows, None, None, 10, 2) == [rows[2], rows[1]]


def test_asset_filter_respects_limit():
    rows = [opportunity(f"USDC {index}", "usdc", index) for index in range(5)]

    assert _filter_rows(rows, "usdc", None, 0, 2) == list(reversed(rows))[:2]


def test_failing_source_becomes_verbose_note():
    row = opportunity("USDC", "usdc", 4)

    rows, errors = _merge_results([([row], None), (None, "morpho ethereum: timeout")])

    assert rows == [row]
    assert errors == ["morpho ethereum: timeout"]
