from chainq.commands import chain
from chainq.providers import fourbyte

TOKEN = "0x1111111111111111111111111111111111111111"
FROM = "0x2222222222222222222222222222222222222222"
TO = "0x3333333333333333333333333333333333333333"

OTHER_TOPIC = bytes.fromhex("aa" * 32)


def _topic(address: str) -> bytes:
    return bytes(12) + bytes.fromhex(address[2:])


def _transfer_log(address: str = TOKEN, amount: int = 500, data: bytes | None = None) -> dict:
    return {
        "address": address,
        "topics": [chain.TRANSFER_TOPIC, _topic(FROM), _topic(TO)],
        "data": data if data is not None else amount.to_bytes(32, "big"),
    }


def _fake_metadata(client, addresses):
    return {address: ("USDT", 6) for address in addresses}


def test_excludes_two_topic_logs(monkeypatch):
    monkeypatch.setattr(chain, "_token_metadata", _fake_metadata)
    log = {"address": TOKEN, "topics": [chain.TRANSFER_TOPIC, _topic(FROM)], "data": (500).to_bytes(32, "big")}
    assert chain._decode_transfers(None, {"logs": [log]}) == []


def test_excludes_four_topic_logs(monkeypatch):
    monkeypatch.setattr(chain, "_token_metadata", _fake_metadata)
    log = {
        "address": TOKEN,
        "topics": [chain.TRANSFER_TOPIC, _topic(FROM), _topic(TO), _topic(TOKEN)],
        "data": b"",
    }
    assert chain._decode_transfers(None, {"logs": [log]}) == []


def test_excludes_non_transfer_three_topic_logs(monkeypatch):
    monkeypatch.setattr(chain, "_token_metadata", _fake_metadata)
    log = {"address": TOKEN, "topics": [OTHER_TOPIC, _topic(FROM), _topic(TO)], "data": (500).to_bytes(32, "big")}
    assert chain._decode_transfers(None, {"logs": [log]}) == []


def test_includes_three_topic_transfer_log(monkeypatch):
    monkeypatch.setattr(chain, "_token_metadata", _fake_metadata)
    rows = chain._decode_transfers(None, {"logs": [_transfer_log(amount=500_000_000)]})
    assert rows == [
        {"token": TOKEN, "symbol": "USDT", "amount": 500.0, "from": FROM, "to": TO}
    ]


def test_address_extraction_from_32_byte_topics(monkeypatch):
    monkeypatch.setattr(chain, "_token_metadata", _fake_metadata)
    rows = chain._decode_transfers(None, {"logs": [_transfer_log()]})
    assert rows[0]["from"] == FROM
    assert rows[0]["to"] == TO


def test_empty_data_guard(monkeypatch):
    monkeypatch.setattr(chain, "_token_metadata", _fake_metadata)
    rows = chain._decode_transfers(None, {"logs": [_transfer_log(data=b"")]})
    assert rows[0]["amount"] == 0.0


def test_caps_at_ten_transfers_with_count_row(monkeypatch):
    monkeypatch.setattr(chain, "_token_metadata", _fake_metadata)
    logs = [_transfer_log(amount=i + 1) for i in range(12)]
    rows = chain._decode_transfers(None, {"logs": logs})
    assert len(rows) == 11
    assert all("note" not in row for row in rows[:10])
    assert rows[10] == {"note": "+2 more"}


def test_unknown_token_metadata_falls_back_to_short_address(monkeypatch):
    monkeypatch.setattr(chain, "_token_metadata", lambda client, addresses: {})
    rows = chain._decode_transfers(None, {"logs": [_transfer_log()]})
    assert rows[0]["symbol"] == chain.short_addr(TOKEN)


def test_token_metadata_failure_degrades_to_short_address_and_raw_amount(monkeypatch):
    def _raise(client, addresses):
        raise RuntimeError("multicall rpc failure")

    monkeypatch.setattr(chain, "_token_metadata", _raise)
    rows = chain._decode_transfers(None, {"logs": [_transfer_log(amount=500)]})
    assert rows == [{"token": TOKEN, "symbol": chain.short_addr(TOKEN), "amount": 500.0, "from": FROM, "to": TO}]


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload


def test_fourbyte_signature_malformed_results_returns_none(monkeypatch):
    monkeypatch.setattr(fourbyte.cache, "get", lambda key: None)
    monkeypatch.setattr(fourbyte.cache, "put", lambda key, value, ttl: None)
    monkeypatch.setattr(fourbyte.http, "get", lambda *args, **kwargs: _FakeResponse({"results": [{"id": 1}]}))
    assert fourbyte.signature("0xaaaaaaaa") is None
