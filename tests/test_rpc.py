import pytest

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

    def fake_aggregate3(client, calls, block):
        seen.append(len(calls))
        if len(calls) > 250:
            raise RuntimeError("payload too large")
        return [b"\x01" for _ in calls]

    monkeypatch.setattr(rpc, "_aggregate3", fake_aggregate3)
    calls = [("0x" + "ab" * 20, b"\x00")] * 1000
    assert rpc.multicall(None, calls) == [b"\x01"] * 1000
    assert seen == [1000, 500, 250, 250, 500, 250, 250]


def test_fallback_provider_skips_failing_endpoints(monkeypatch):
    from chainq.rpc import FallbackProvider

    calls: list[tuple[str, str]] = []

    def fake_make_request(self, method, params):
        calls.append((self.endpoint_uri, method))
        if "bad" in self.endpoint_uri:
            raise RuntimeError("HTTP 403")
        if "wrong" in self.endpoint_uri:
            return {"jsonrpc": "2.0", "id": 1, "result": "0x2"}
        if "limited" in self.endpoint_uri and method == "eth_call":
            return {"jsonrpc": "2.0", "id": 1, "error": {"code": -32005, "message": "rate limit exceeded"}}
        return {"jsonrpc": "2.0", "id": 1, "result": "0x1"}

    monkeypatch.setattr("chainq.rpc.HTTPProvider.make_request", fake_make_request)
    provider = FallbackProvider(["https://bad", "https://wrong", "https://limited", "https://good"], 1)

    assert provider.make_request("eth_blockNumber", [])["result"] == "0x1"
    assert provider.url == "https://limited"
    assert provider.make_request("eth_call", [{}])["result"] == "0x1"
    assert provider.url == "https://good"
    assert provider.make_request("eth_blockNumber", [])["result"] == "0x1"
    assert provider.url == "https://good"
    assert 1 in provider.dead
    assert ("https://good", "eth_chainId") in calls
    assert calls.count(("https://good", "eth_chainId")) == 1


def test_fallback_provider_reports_every_failure(monkeypatch):
    from chainq.errors import ChainqError
    from chainq.rpc import FallbackProvider

    def fake_make_request(self, method, params):
        raise RuntimeError("boom")

    monkeypatch.setattr("chainq.rpc.HTTPProvider.make_request", fake_make_request)
    provider = FallbackProvider(["https://a", "https://b"], 1)
    with pytest.raises(ChainqError, match=r"https://a \(RuntimeError\); https://b \(RuntimeError\)"):
        provider.make_request("eth_blockNumber", [])


def _fake_batch_transport(monkeypatch, limits=None, unsupported=(), throttle_once=()):
    from requests import HTTPError, Response

    limits = limits or {}
    sent: list[tuple[str, int]] = []
    throttled: set[str] = set()

    def make_request(self, method, params):
        if method == "eth_chainId":
            return {"jsonrpc": "2.0", "id": 1, "result": "0x1"}
        return make_batch_request(self, [(method, params)])[0]

    def make_batch_request(self, calls):
        uri = self.endpoint_uri
        sent.append((uri, len(calls)))
        if uri in throttle_once and uri not in throttled:
            throttled.add(uri)
            response = Response()
            response.status_code = 429
            raise HTTPError(response=response)
        if len(calls) > limits.get(uri, 100):
            response = Response()
            response.status_code = 400
            response._content = f"Batch of more than {limits[uri]} requests are not allowed".encode()
            raise HTTPError(response=response)
        return [
            {"jsonrpc": "2.0", "id": i, "error": {"code": -32601, "message": "method not found"}}
            if uri in unsupported and method == "eth_getHeaderByNumber"
            else {"jsonrpc": "2.0", "id": i, "result": f"{method}:{params[0]}"}
            for i, (method, params) in enumerate(calls)
        ]

    monkeypatch.setattr("chainq.rpc.HTTPProvider.make_request", make_request)
    monkeypatch.setattr("chainq.rpc.HTTPProvider.make_batch_request", make_batch_request)
    monkeypatch.setattr("chainq.rpc.time.sleep", lambda _: None)
    return sent


def _variants(count):
    return (
        [("eth_getHeaderByNumber", [hex(i)]) for i in range(count)],
        [("eth_getBlockByNumber", [hex(i), False]) for i in range(count)],
    )


def test_batch_shrinks_to_advertised_limit(monkeypatch):
    from chainq.rpc import FallbackProvider

    sent = _fake_batch_transport(monkeypatch, limits={"https://capped": 3})
    provider = FallbackProvider(["https://capped"], 1)
    results = provider.batch(*_variants(10))
    assert [item["result"] for item in results] == [f"eth_getHeaderByNumber:{hex(i)}" for i in range(10)]
    assert provider.batch_sizes == {0: 3}
    assert max(size for _, size in sent[-4:]) == 3


def test_batch_falls_back_to_block_method(monkeypatch):
    from chainq.rpc import FallbackProvider

    _fake_batch_transport(monkeypatch, unsupported={"https://old"})
    provider = FallbackProvider(["https://old"], 1)
    assert provider.batch(*_variants(2))[0]["result"] == "eth_getBlockByNumber:0x0"
    assert provider.variants == {0: 1}


def test_batch_retries_throttled_chunk_in_place(monkeypatch):
    from chainq.rpc import FallbackProvider

    sent = _fake_batch_transport(monkeypatch, throttle_once={"https://busy"})
    provider = FallbackProvider(["https://busy", "https://spare"], 1)
    assert len(provider.batch(*_variants(4))) == 4
    assert provider.url == "https://busy"
    assert all(uri == "https://busy" for uri, _ in sent)


def test_batch_fails_over_on_provider_error(monkeypatch):
    from chainq.rpc import FallbackProvider

    _fake_batch_transport(monkeypatch)
    from chainq.rpc import HTTPProvider

    original = HTTPProvider.make_batch_request

    def limited(self, calls):
        if "limited" in self.endpoint_uri:
            return [{"jsonrpc": "2.0", "id": i, "error": {"code": -32005, "message": "rate limit"}} for i in range(len(calls))]
        return original(self, calls)

    monkeypatch.setattr("chainq.rpc.HTTPProvider.make_batch_request", limited)
    provider = FallbackProvider(["https://limited", "https://good"], 1)
    assert provider.batch(*_variants(3))[2]["result"] == "eth_getHeaderByNumber:0x2"
    assert provider.url == "https://good"


def test_archive_failures_suggest_override(monkeypatch):
    from chainq.errors import ChainqError
    from chainq.rpc import FallbackProvider

    def make_request(self, method, params):
        if method == "eth_chainId":
            return {"jsonrpc": "2.0", "id": 1, "result": "0x1"}
        return {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "missing trie node abc"}}

    monkeypatch.setattr("chainq.rpc.HTTPProvider.make_request", make_request)
    provider = FallbackProvider(["https://full"], 1, "arbitrum")
    with pytest.raises(ChainqError, match="CHAINQ_RPC_ARBITRUM"):
        provider.make_request("eth_call", [{}, "0x1"])
