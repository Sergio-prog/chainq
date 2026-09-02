import pytest
from typer.testing import CliRunner

from chainq.cli import app
from chainq.commands import buybacks as cmd
from chainq.errors import ChainqError
from chainq.providers import buybacks as provider

runner = CliRunner()

HYPE_FILLS = [
    {"coin": "@107", "side": "B", "sz": "100", "px": "60", "time": 1_784_000_000_000},
    {"coin": "@107", "side": "B", "sz": "50", "px": "62", "time": 1_784_000_000_000},
    {"coin": "@107", "side": "A", "sz": "10", "px": "61", "time": 1_784_000_000_000},
    {"coin": "@1", "side": "B", "sz": "5", "px": "1", "time": 1_784_000_000_000},
]

ZRO_REAL_HTML = (
    "<td>141,557 ZRO</td><td>$136,980</td><td>$136,980</td><td>Stargate</td><td>June 2026</td>"
    "<tr><td>124,574 ZRO</td><td>$143,217</td><td>$143,217</td><td>Stargate</td><td>May 2026</td>"
)


def test_zro_parser_reads_real_rows():
    assert provider._parse_zro(ZRO_REAL_HTML) == [("2026-06", 141557, 136980), ("2026-05", 124574, 143217)]


def test_zro_snapshot_fallback_is_self_consistent():
    prog = provider._zro_snapshot()
    assert prog["provenance"] == "snapshot"
    assert prog["cadence"] == "monthly"
    assert prog["cumulative_tokens"] == sum(p["tokens"] for p in prog["periods"])
    assert prog["cumulative_tokens"] == 2_031_182
    assert prog["periods"][0]["period"] == "2026-06"
    assert prog["source_url"].startswith("https://layerzero.foundation")


def test_hype_buckets_only_buy_fills(monkeypatch):
    monkeypatch.setattr(provider.cache, "get", lambda key: None)
    monkeypatch.setattr(provider.cache, "put", lambda *a, **k: None)
    monkeypatch.setattr(provider.hyperliquid, "user_fills_by_time", lambda addr, start, end: HYPE_FILLS)
    prog = provider._hype(1)
    assert prog["provenance"] == "live"
    assert prog["cumulative_tokens"] == 150.0
    assert prog["cumulative_usd"] == pytest.approx(100 * 60 + 50 * 62)
    assert len(prog["periods"]) == 1
    assert prog["periods"][0]["avg_price_usd"] == pytest.approx((100 * 60 + 50 * 62) / 150)


def test_uni_buckets_releases_by_day(monkeypatch):
    def fake_rpc(method, params):
        if method == "eth_blockNumber":
            return hex(1_000_000)
        if method == "eth_call":
            return hex(4000 * 10**18) if params[0]["data"] == "0x42cde4e8" else hex(1087)
        if method == "eth_getLogs":
            topic, block_filter = params[0]["topics"][0], params[0]
            if topic == provider.UNI_RELEASED_TOPIC:
                lo, hi = int(block_filter["fromBlock"], 16), int(block_filter["toBlock"], 16)
                if lo <= 999_000 <= hi:
                    return [{"blockNumber": hex(999_000), "transactionHash": "0xabc"}]
                return []
            return [{"transactionHash": "0xabc", "data": hex(4000 * 10**18)}]
        if method == "eth_getBlockByNumber":
            return {"timestamp": hex(1_784_000_000)}
        return None

    monkeypatch.setattr(provider, "_rpc", fake_rpc)
    prog = provider._uni(1)
    assert prog["provenance"] == "live"
    assert prog["cumulative_tokens"] == 4000.0
    assert len(prog["periods"]) == 1
    assert prog["periods"][0]["tokens"] == 4000.0
    assert "1087 cumulative releases" in prog["note"]


def test_sky_buckets_exec_events_by_day(monkeypatch):
    exec_data = "0x" + f"{6000 * 10**18:064x}" + f"{94860 * 10**18:064x}"

    def fake_rpc(method, params):
        if method == "eth_blockNumber":
            return hex(1_000_000)
        if method == "eth_getLogs":
            lo, hi = int(params[0]["fromBlock"], 16), int(params[0]["toBlock"], 16)
            if lo <= 999_000 <= hi:
                return [{"blockNumber": hex(999_000), "data": exec_data}] * 2
            return []
        if method == "eth_getBlockByNumber":
            return {"timestamp": hex(1_784_000_000)}
        return None

    monkeypatch.setattr(provider, "_rpc", fake_rpc)
    prog = provider._sky(1)
    assert prog["provenance"] == "live"
    assert prog["asset"] == "SKY"
    assert prog["cumulative_usd"] == pytest.approx(12000.0)
    assert prog["cumulative_tokens"] == pytest.approx(2 * 94860.0)
    assert prog["periods"][0]["avg_price_usd"] == pytest.approx(6000 / 94860.0)


def test_no_programs_reports_missing_argument():
    result = runner.invoke(app, ["buybacks"])
    assert result.exit_code == 2
    assert "Missing argument" in result.output


def test_lit_reports_precise_limitation():
    with pytest.raises(ChainqError) as exc:
        provider._lit(7)
    assert "not publicly retrievable" in str(exc.value)


def test_command_rejects_unknown_program():
    with pytest.raises(ChainqError) as exc:
        cmd.buybacks(programs=["doge"])
    assert "doge" in str(exc.value)


def test_command_lit_surfaces_limitation():
    with pytest.raises(ChainqError) as exc:
        cmd.buybacks(programs=["lit"])
    assert "not publicly retrievable" in str(exc.value)


def test_rows_flatten_preserves_provenance_and_source():
    fake = {
        "program": "ZRO", "asset": "ZRO", "cadence": "monthly", "provenance": "snapshot",
        "source": "src", "source_url": "https://x", "window_days": None, "note": "n",
        "cumulative_tokens": 3, "cumulative_usd": 3,
        "periods": [{"period": "2026-06", "tokens": 3, "usd": 3, "avg_price_usd": 1.0}],
    }
    rows = cmd._rows([fake])
    assert rows[0]["provenance"] == "snapshot"
    assert rows[0]["source_url"] == "https://x"
    assert rows[0]["period"] == "2026-06"


def test_command_json_and_quiet(monkeypatch, capsys):
    fake = provider._zro_snapshot()
    monkeypatch.setitem(provider.PROGRAMS, "zro", lambda days: fake)
    cmd.buybacks(programs=["zro"], json_out=True)
    out = capsys.readouterr().out
    assert '"provenance": "snapshot"' in out
    assert '"program": "ZRO"' in out
    assert "\x1b[" not in out
    cmd.buybacks(programs=["zro"], quiet=True)
    assert "ZRO 2031182" in capsys.readouterr().out
