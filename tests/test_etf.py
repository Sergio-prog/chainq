import json

import pytest

from chainq.commands import etf as etf_cmd
from chainq.errors import ChainqError
from chainq.providers import theblock

FLOW_ROWS = [
    {"date": "2026-07-17", "FBTC": -4_200_000.0, "IBIT": 136_500_000.0, "net_flow_usd": 132_300_000.0},
    {"date": "2026-07-16", "BITB": 15_000_000.0, "FBTC": 30_700_000.0, "IBIT": 33_400_000.0, "net_flow_usd": 79_100_000.0},
]

THEBLOCK_PAYLOAD = {
    "jsonFile": {
        "data": json.dumps(
            {
                "Series": {
                    "IBIT": {"Data": [{"Timestamp": 1_784_203_200, "Result": 33_400_000.0},
                                       {"Timestamp": 1_784_289_600, "Result": 136_500_000.0}]},
                    "FBTC": {"Data": [{"Timestamp": 1_784_203_200, "Result": 30_700_000.0},
                                      {"Timestamp": 1_784_289_600, "Result": -4_200_000.0}]},
                }
            }
        )
    }
}


class _Resp:
    status_code = 200

    def json(self):
        return THEBLOCK_PAYLOAD


def test_flow_text_sign_and_units():
    assert etf_cmd._flow_text(254_300_000) == "+$254.30M"
    assert etf_cmd._flow_text(-55_066_297) == "-$55.07M"
    assert etf_cmd._flow_text(0) == "+$0.00"


def test_invalid_asset_rejected():
    with pytest.raises(ChainqError) as exc:
        etf_cmd.etf(asset="doge")
    assert "doge" in str(exc.value)


def test_theblock_parses_series_into_daily_totals(monkeypatch):
    monkeypatch.setattr(theblock.cache, "get", lambda key: None)
    monkeypatch.setattr(theblock.cache, "put", lambda *a, **k: None)
    monkeypatch.setattr(theblock.http, "get", lambda url, **kwargs: _Resp())
    rows = theblock.flow_history("BTC")
    assert rows[0]["date"] == "2026-07-17"
    assert rows[0]["net_flow_usd"] == 132_300_000.0
    assert rows[0]["IBIT"] == 136_500_000.0
    assert rows[1]["date"] == "2026-07-16"
    assert rows[1]["net_flow_usd"] == 64_100_000.0


def test_etf_maps_rows_and_json(monkeypatch, capsys):
    monkeypatch.setattr(etf_cmd.theblock, "flow_history", lambda symbol: FLOW_ROWS)
    etf_cmd.etf(asset="btc", days=2, json_out=True)
    out = capsys.readouterr().out
    assert "\x1b[" not in out
    assert '"net_flow_usd": 132300000.0' in out
    assert '"source": "The Block"' in out
    assert '"source_url": "https://www.theblock.co/data/etfs/bitcoin-etf/spot-bitcoin-etf-flows"' in out


def test_etf_quiet_is_bare_value(monkeypatch, capsys):
    monkeypatch.setattr(etf_cmd.theblock, "flow_history", lambda symbol: FLOW_ROWS)
    etf_cmd.etf(asset="btc", days=2, quiet=True)
    assert capsys.readouterr().out.strip() == "132300000.0"


def test_etf_empty_raises(monkeypatch):
    monkeypatch.setattr(etf_cmd.theblock, "flow_history", lambda symbol: [])
    with pytest.raises(ChainqError):
        etf_cmd.etf(asset="eth")
