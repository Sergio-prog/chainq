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
