from chainq.rpc import decode_address, decode_string, decode_uint, encode_erc20, encode_get_eth_balance

HOLDER = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


def test_encode_balanceof_selector():
    calldata = encode_erc20("balanceOf", [HOLDER])
    assert calldata.hex().startswith("70a08231")
    assert len(calldata) == 36


def test_encode_get_eth_balance():
    assert encode_get_eth_balance(HOLDER).hex().startswith("4d2301cc")


def test_decode_uint():
    assert decode_uint((123).to_bytes(32, "big")) == 123


def test_decode_address():
    padded = b"\x00" * 12 + bytes.fromhex(HOLDER[2:])
    assert decode_address(padded) == HOLDER


def test_decode_string_abi_encoded():
    data = (32).to_bytes(32, "big") + (4).to_bytes(32, "big") + b"USDT".ljust(32, b"\x00")
    assert decode_string(data) == "USDT"


def test_decode_string_bytes32_fallback():
    assert decode_string(b"MKR".ljust(32, b"\x00")) == "MKR"


def test_aggregate3_roundtrip_encoding():
    from chainq.rpc import AGGREGATE3_SELECTOR, _decode_aggregate3, _encode_aggregate3

    calls = [("0x" + "ab" * 20, encode_erc20("balanceOf", [HOLDER])), ("0x" + "cd" * 20, encode_erc20("symbol"))]
    data = _encode_aggregate3(calls)
    assert data[:4] == AGGREGATE3_SELECTOR
    assert int.from_bytes(data[4:36], "big") == 0x20
    assert int.from_bytes(data[36:68], "big") == 2
    payload = (
        (0x20).to_bytes(32, "big")
        + (2).to_bytes(32, "big")
        + (0x40).to_bytes(32, "big")
        + (0xA0).to_bytes(32, "big")
        + (1).to_bytes(32, "big")
        + (0x40).to_bytes(32, "big")
        + (32).to_bytes(32, "big")
        + (7).to_bytes(32, "big")
        + (0).to_bytes(32, "big")
        + (0x40).to_bytes(32, "big")
        + (0).to_bytes(32, "big")
    )
    assert _decode_aggregate3(payload) == [(7).to_bytes(32, "big"), None]


def test_multicall_chunks_and_halves_on_failure(monkeypatch):
    from chainq import rpc

    seen: list[int] = []

    def fake_aggregate3(client, calls):
        seen.append(len(calls))
        if len(calls) > 250:
            raise RuntimeError("payload too large")
        return [b"\x01" for _ in calls]

    monkeypatch.setattr(rpc, "_aggregate3", fake_aggregate3)
    calls = [("0x" + "ab" * 20, b"\x00")] * 1000
    assert rpc.multicall(None, calls) == [b"\x01"] * 1000
    assert seen == [1000, 500, 250, 250, 500, 250, 250]
