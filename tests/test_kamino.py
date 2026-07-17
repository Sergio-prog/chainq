import pytest

from chainq.commands.kamino import _collect_rows, _filter_rows, _reserve_row, _selected_markets, _sort_rows

MARKET = {
    "name": "Primary market on mainnet",
    "lendingMarket": "7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF",
}

RESERVE = {
    "reserve": "Reserve111111111111111111111111111111111",
    "liquidityToken": "USDC",
    "liquidityTokenMint": "Mint1111111111111111111111111111111111111",
    "maxLtv": "0.8",
    "borrowApy": "0.0618",
    "supplyApy": "0.0421",
    "totalSupplyUsd": "1200.5",
    "totalBorrowUsd": "900.375",
}


def test_reserve_row_normalizes_string_values():
    row = _reserve_row(MARKET, RESERVE)

    assert row is not None
    assert row["supply_apy_pct"] == pytest.approx(4.21)
    assert row["borrow_apy_pct"] == pytest.approx(6.18)
    assert row["max_ltv_pct"] == pytest.approx(80)
    assert row["supplied_usd"] == pytest.approx(1200.5)
    assert row["borrowed_usd"] == pytest.approx(900.375)
    assert row["utilization_pct"] == pytest.approx(75)


def test_zero_supply_has_no_utilization():
    row = _reserve_row(MARKET, {**RESERVE, "totalSupplyUsd": "0"})

    assert row is not None
    assert row["utilization_pct"] is None


@pytest.mark.parametrize("sort", ["supplied", "supply-apy", "borrow-apy", "utilization"])
def test_sort_rows(sort):
    low = _reserve_row(MARKET, RESERVE)
    high = _reserve_row(
        MARKET,
        {
            **RESERVE,
            "liquidityToken": "HIGH",
            "totalSupplyUsd": "2401",
            "totalBorrowUsd": "2160.9",
            "supplyApy": "0.0842",
            "borrowApy": "0.1236",
        },
    )

    assert low is not None and high is not None
    assert _sort_rows([low, high], sort)[0]["symbol"] == "HIGH"


def test_filter_rows_matches_symbol_and_mint_exactly_case_insensitive():
    row = _reserve_row(MARKET, RESERVE)

    assert row is not None
    assert _filter_rows([row], "usdc") == [row]
    assert _filter_rows([row], RESERVE["liquidityTokenMint"].lower()) == [row]
    assert _filter_rows([row], "usd") == []


def test_selected_markets_matches_address_or_name_substring():
    assert _selected_markets([MARKET], MARKET["lendingMarket"].lower()) == [MARKET]
    assert _selected_markets([MARKET], "PRIMARY") == [MARKET]
    assert _selected_markets([MARKET], "other") == []


@pytest.mark.parametrize(
    "malformed",
    [
        {},
        {**RESERVE, "supplyApy": None},
        {**RESERVE, "totalSupplyUsd": "not-a-number"},
        {**RESERVE, "totalSupplyUsd": "nan"},
        {**RESERVE, "liquidityTokenMint": None},
        None,
    ],
)
def test_malformed_reserve_is_skipped(malformed):
    rows, skipped = _collect_rows([MARKET], [[RESERVE, malformed]])

    assert len(rows) == 1
    assert skipped == 1
