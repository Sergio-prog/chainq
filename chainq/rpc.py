import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import Any

from requests import HTTPError
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.providers import JSONBaseProvider
from web3.providers.rpc import HTTPProvider
from web3.types import RPCEndpoint, RPCResponse

from chainq.catalog import CatalogToken
from chainq.config import settings
from chainq.errors import ChainqError
from chainq.networks import Network

ERC20_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
    {
        "name": "symbol",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "string"}],
    },
    {
        "name": "name",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "string"}],
    },
    {
        "name": "totalSupply",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"

MULTICALL3_ABI = [
    {
        "name": "aggregate3",
        "type": "function",
        "stateMutability": "payable",
        "inputs": [
            {
                "name": "calls",
                "type": "tuple[]",
                "components": [
                    {"name": "target", "type": "address"},
                    {"name": "allowFailure", "type": "bool"},
                    {"name": "callData", "type": "bytes"},
                ],
            }
        ],
        "outputs": [
            {
                "name": "returnData",
                "type": "tuple[]",
                "components": [
                    {"name": "success", "type": "bool"},
                    {"name": "returnData", "type": "bytes"},
                ],
            }
        ],
    },
    {
        "name": "getEthBalance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "addr", "type": "address"}],
        "outputs": [{"name": "balance", "type": "uint256"}],
    },
]

_codec_w3 = Web3()
_erc20_codec = _codec_w3.eth.contract(abi=ERC20_ABI)
_multicall_codec = _codec_w3.eth.contract(abi=MULTICALL3_ABI)


def encode_erc20(fn: str, args: list | None = None) -> bytes:
    return bytes.fromhex(_erc20_codec.encode_abi(fn, args or [])[2:])


def encode_call(abi: list, fn: str, args: list | None = None) -> bytes:
    return bytes.fromhex(_codec_w3.eth.contract(abi=abi).encode_abi(fn, args or [])[2:])


def decode_address(data: bytes) -> str:
    return Web3.to_checksum_address(f"0x{data[12:32].hex()}")


def encode_get_eth_balance(address: str) -> bytes:
    return bytes.fromhex(_multicall_codec.encode_abi("getEthBalance", [Web3.to_checksum_address(address)])[2:])


def decode_uint(data: bytes) -> int:
    return int.from_bytes(data[:32], "big")


def decode_string(data: bytes) -> str:
    try:
        return _codec_w3.codec.decode(["string"], data)[0]
    except Exception:
        return data[:32].rstrip(b"\x00").decode("utf-8", errors="replace")


MULTICALL_CHUNK = 1000
MULTICALL_MIN_CHUNK = 100


AGGREGATE3_SELECTOR = Web3.keccak(text="aggregate3((address,bool,bytes)[])")[:4]


def _word(value: int) -> bytes:
    return value.to_bytes(32, "big")


def _encode_aggregate3(calls: list[tuple[str, bytes]]) -> bytes:
    tuples = []
    for target, calldata in calls:
        padded = calldata + b"\x00" * (-len(calldata) % 32)
        tuples.append(
            _word(int(target, 16)) + _word(1) + _word(0x60) + _word(len(calldata)) + padded
        )
    offsets = []
    position = 32 * len(tuples)
    for item in tuples:
        offsets.append(_word(position))
        position += len(item)
    return AGGREGATE3_SELECTOR + _word(0x20) + _word(len(tuples)) + b"".join(offsets) + b"".join(tuples)


def _decode_aggregate3(data: bytes) -> list[bytes | None]:
    base = 32 + int.from_bytes(data[0:32], "big")
    count = int.from_bytes(data[base - 32 : base], "big")
    results: list[bytes | None] = []
    for i in range(count):
        item = base + int.from_bytes(data[base + 32 * i : base + 32 * (i + 1)], "big")
        success = int.from_bytes(data[item : item + 32], "big") == 1
        payload = item + int.from_bytes(data[item + 32 : item + 64], "big")
        length = int.from_bytes(data[payload : payload + 32], "big")
        returned = data[payload + 32 : payload + 32 + length]
        results.append(bytes(returned) if success and returned else None)
    return results


def _aggregate3(client: "ChainClient", calls: list[tuple[str, bytes]], block: str | int) -> list[bytes | None]:
    raw = client.w3.eth.call({"to": MULTICALL3_ADDRESS, "data": _encode_aggregate3(calls)}, block)
    return _decode_aggregate3(bytes(raw))


def multicall(
    client: "ChainClient",
    calls: list[tuple[str, bytes]],
    chunk: int = MULTICALL_CHUNK,
    block: str | int = "latest",
) -> list[bytes | None]:
    if not calls:
        return []
    results: list[bytes | None] = []
    for start in range(0, len(calls), chunk):
        batch = calls[start : start + chunk]
        try:
            results.extend(_aggregate3(client, batch, block))
        except Exception:
            if chunk <= MULTICALL_MIN_CHUNK:
                raise
            results.extend(multicall(client, batch, chunk // 2, block))
    return results


FAILOVER_ERROR_CODES = {-32004, -32005, -32601, -32603}
FAILOVER_MESSAGE = re.compile(
    r"rate limit|too many|limit exceeded|not supported|unsupported|upstream|unavailable"
    r"|timed? ?out|forbidden|capacity|overloaded|not able to process"
    r"|missing trie node|historical state|state histor|archive|pruned|usage limit|limit reached",
    re.IGNORECASE,
)


def describe_failure(exc: Exception) -> str:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status:
        return f"HTTP {status}"
    return type(exc).__name__


def is_provider_error(response: RPCResponse) -> bool:
    error = response.get("error")
    if not isinstance(error, dict):
        return False
    return error.get("code") in FAILOVER_ERROR_CODES or bool(FAILOVER_MESSAGE.search(str(error.get("message", ""))))


BATCH_SIZE = 10
BATCH_PARALLEL = 8
HISTORY_MISSING = re.compile(r"missing trie node|historical state|state histor|archive|pruned", re.IGNORECASE)
BATCH_BACKOFF = 1.0
CHUNK_RETRIES = 2
CHUNK_BACKOFF = 0.3
RATE_LIMITED = re.compile(r"HTTP 429|rate limit|limit reached|too many", re.IGNORECASE)
BATCH_REJECTED = re.compile(r"batch", re.IGNORECASE)
BATCH_CAP = re.compile(r"(?:more than|maximum of|over|exceeds?)\D{0,20}(\d+)", re.IGNORECASE)


UNSUPPORTED_CODES = {-32601, -32600, -32611}


def is_unsupported(response: RPCResponse) -> bool:
    error = response.get("error")
    if not isinstance(error, dict):
        return False
    return error.get("code") in UNSUPPORTED_CODES or "method" in str(error.get("message", "")).lower()


class BatchTooLarge(Exception):
    def __init__(self, limit: int | None):
        super().__init__(f"batch limit {limit}")
        self.limit = limit


def batch_limit(message: str) -> BatchTooLarge | None:
    if not BATCH_REJECTED.search(message):
        return None
    match = BATCH_CAP.search(message)
    return BatchTooLarge(int(match.group(1)) if match else None)


class FallbackProvider(JSONBaseProvider):
    def __init__(self, urls: list[str], chain_id: int, key: str | None = None):
        super().__init__()
        self.chain_id = chain_id
        self.key = key
        self.providers = [
            HTTPProvider(url, request_kwargs={"timeout": settings.rpc_timeout}, exception_retry_configuration=None)
            for url in urls
        ]
        self.active = 0
        self.verified: set[int] = set()
        self.dead: set[int] = set()
        self.batch_sizes: dict[int, int] = {}
        self.variants: dict[int, int] = {}

    @property
    def url(self) -> str:
        return self.providers[self.active].endpoint_uri

    def _verify(self, index: int) -> None:
        if index in self.verified:
            return
        response = self.providers[index].make_request(RPCEndpoint("eth_chainId"), [])
        if "result" not in response:
            raise ChainqError(f"eth_chainId failed: {response.get('error')}")
        chain_id = int(response["result"], 16)
        if chain_id != self.chain_id:
            self.dead.add(index)
            raise ChainqError(f"wrong chain id {chain_id}")
        self.verified.add(index)

    def _order(self) -> list[int]:
        order = [*range(self.active, len(self.providers)), *range(self.active)]
        return [index for index in order if index not in self.dead]

    def discard_active(self) -> None:
        self.dead.add(self.active)

    @property
    def alive(self) -> bool:
        return bool(self._order())

    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        failures = []
        for index in self._order():
            provider = self.providers[index]
            try:
                self._verify(index)
                response = provider.make_request(method, params)
            except Exception as exc:
                failures.append(f"{provider.endpoint_uri} ({describe_failure(exc)})")
                continue
            if is_provider_error(response):
                failures.append(f"{provider.endpoint_uri} ({response['error'].get('message')})")
                continue
            self.active = index
            return response
        message = f"all RPC endpoints failed for {method}: {'; '.join(failures)}"
        if self.key and HISTORY_MISSING.search(message):
            message += f". Historical state needs an archive RPC: set CHAINQ_RPC_{self.key.upper()}=<url>"
        raise ChainqError(message)

    def batch(self, *variants: list[tuple[str, Any]]) -> list[RPCResponse]:
        try:
            return self._batch_once(variants)
        except ChainqError as exc:
            if not RATE_LIMITED.search(str(exc)):
                raise
        time.sleep(BATCH_BACKOFF)
        return self._batch_once(variants)

    def _batch_once(self, variants: tuple[list[tuple[str, Any]], ...]) -> list[RPCResponse]:
        failures = []
        for index in self._order():
            provider = self.providers[index]
            try:
                self._verify(index)
                responses = self._batch_variants(index, variants)
            except Exception as exc:
                failures.append(f"{provider.endpoint_uri} ({describe_failure(exc)})")
                continue
            rejected = next((item for item in responses if is_provider_error(item)), None)
            if rejected:
                failures.append(f"{provider.endpoint_uri} ({rejected['error'].get('message')})")
                continue
            self.active = index
            return responses
        raise ChainqError(f"all RPC endpoints failed for batch: {'; '.join(failures)}")

    def _batch_variants(self, index: int, variants: tuple[list[tuple[str, Any]], ...]) -> list[RPCResponse]:
        position = min(self.variants.get(index, 0), len(variants) - 1)
        while True:
            responses = self._batch_at(index, variants[position])
            if position + 1 < len(variants) and any(is_unsupported(item) for item in responses):
                position += 1
                self.variants[index] = position
                continue
            return responses

    def _batch_at(self, index: int, calls: list[tuple[str, Any]]) -> list[RPCResponse]:
        while True:
            size = self.batch_sizes.get(index, BATCH_SIZE)
            chunks = [calls[start : start + size] for start in range(0, len(calls), size)]
            send = partial(self._send_chunk, index)
            try:
                if len(chunks) == 1:
                    parts = [send(chunks[0])]
                else:
                    with ThreadPoolExecutor(min(len(chunks), BATCH_PARALLEL)) as pool:
                        parts = list(pool.map(send, chunks))
            except BatchTooLarge as exc:
                if size == 1:
                    raise
                self.batch_sizes[index] = max(1, min(exc.limit or size // 2, size - 1))
                continue
            return [item for part in parts for item in part]

    def _send_chunk(self, index: int, chunk: list[tuple[str, Any]]) -> list[RPCResponse]:
        for attempt in range(CHUNK_RETRIES):
            try:
                responses = self._post_chunk(index, chunk)
            except HTTPError as exc:
                if exc.response is None or exc.response.status_code != 429:
                    raise
            else:
                if not any(RATE_LIMITED.search(str(item["error"])) for item in responses if "error" in item):
                    return responses
            time.sleep(CHUNK_BACKOFF * (attempt + 1))
        return self._post_chunk(index, chunk)

    def _post_chunk(self, index: int, chunk: list[tuple[str, Any]]) -> list[RPCResponse]:
        provider = self.providers[index]
        if len(chunk) == 1:
            return [provider.make_request(RPCEndpoint(chunk[0][0]), chunk[0][1])]
        try:
            response = provider.make_batch_request([(RPCEndpoint(method), params) for method, params in chunk])
        except HTTPError as exc:
            rejection = batch_limit(exc.response.text if exc.response is not None else "")
            if rejection:
                raise rejection from None
            raise
        if not isinstance(response, list):
            message = str(response.get("error"))
            raise batch_limit(message) or ChainqError(f"batch failed: {message}")
        for item in response:
            rejection = batch_limit(str(item["error"])) if "error" in item else None
            if rejection:
                raise rejection
        if len(response) != len(chunk):
            raise ChainqError("batch response size mismatch")
        return response


@dataclass
class ChainClient:
    w3: Web3
    network: Network
    provider: FallbackProvider

    @property
    def url(self) -> str:
        return self.provider.url


def connect(network: Network) -> ChainClient:
    urls = list(network.rpc_urls)
    override = os.environ.get(f"CHAINQ_RPC_{network.key.upper()}")
    if override:
        urls.insert(0, override)
    provider = FallbackProvider(urls, network.chain_id, network.key)
    w3 = Web3(provider)
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return ChainClient(w3=w3, network=network, provider=provider)


def erc20(client: ChainClient, address: str):
    return client.w3.eth.contract(address=Web3.to_checksum_address(address), abi=ERC20_ABI)


SWEEP_CHUNK = 1500


def sweep_catalog(client: "ChainClient", address: str, tokens: list[CatalogToken]) -> tuple[int, list[dict]]:
    holder = Web3.to_checksum_address(address)
    balance_of = encode_erc20("balanceOf", [holder])
    calls = [(MULTICALL3_ADDRESS, encode_get_eth_balance(holder))]
    calls += [(token.address, balance_of) for token in tokens]
    results = multicall(client, calls, SWEEP_CHUNK)
    wei = decode_uint(results[0]) if results[0] else 0
    hits = [(token, decode_uint(raw)) for token, raw in zip(tokens, results[1:], strict=True) if raw and decode_uint(raw)]
    incomplete = [token for token, _ in hits if token.decimals is None]
    metadata: dict[str, tuple[int, str]] = {}
    if incomplete:
        meta_calls = []
        for token in incomplete:
            meta_calls.append((token.address, encode_erc20("decimals")))
            meta_calls.append((token.address, encode_erc20("symbol")))
        meta = multicall(client, meta_calls)
        for i, token in enumerate(incomplete):
            decimals, symbol = meta[2 * i : 2 * i + 2]
            metadata[token.address] = (
                decode_uint(decimals) if decimals else 18,
                decode_string(symbol) if symbol else token.symbol,
            )
    rows = []
    for token, raw in hits:
        decimals, symbol = metadata.get(token.address, (token.decimals, token.symbol))
        rows.append(
            {
                "registry_symbol": token.symbol.lower() if token.source == "registry" else None,
                "token_address": token.address,
                "symbol": symbol,
                "raw_amount": raw,
                "decimals": decimals,
                "catalog": token,
            }
        )
    return wei, rows
