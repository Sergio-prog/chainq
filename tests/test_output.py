import pytest

from chainq.errors import ChainqError
from chainq.output import Out, _tabular, render_table, to_toon

ROWS = [
    {"name": "Ethereum", "symbol": "ETH", "price_usd": 2100.5, "rank": 2},
    {"name": "Bitcoin", "symbol": "BTC", "price_usd": 48000.0, "rank": 1},
]


def test_toon_list_of_dicts():
    assert to_toon(ROWS) == (
        "[2]{name,symbol,price_usd,rank}:\n"
        "  Ethereum,ETH,2100.5,2\n"
        "  Bitcoin,BTC,48000.0,1"
    )


def test_toon_dict_with_rows_and_scalars():
    result = to_toon({"total": 2, "coins": ROWS[:1], "next": "abc123"})
    assert result == ("total: 2\ncoins[1]{name,symbol,price_usd,rank}:\n  Ethereum,ETH,2100.5,2\nnext: abc123")


def test_toon_quotes_values_with_commas():
    assert to_toon([{"name": "a,b", "x": None}]) == '[1]{name,x}:\n  "a,b",null'


def test_render_table_aligns_and_formats():
    table = render_table(ROWS)
    lines = table.splitlines()
    assert lines[0].split() == ["name", "symbol", "price_usd", "rank"]
    assert len(lines) == 4
    assert "48,000" in table


def test_tabular_extracts_single_row_list():
    prologue, rows = _tabular({"network": "ethereum", "reserves": ROWS})
    assert prologue == ["network: ethereum"]
    assert rows == ROWS


def test_tabular_dict_of_scalars():
    prologue, rows = _tabular({"a": 1, "b": "x"})
    assert prologue == []
    assert rows == [{"field": "a", "value": 1}, {"field": "b", "value": "x"}]


def test_unknown_format_rejected():
    with pytest.raises(ChainqError):
        Out(format="yaml")


def test_json_flag_wins():
    assert Out(json=True, format="table").format == "json"
