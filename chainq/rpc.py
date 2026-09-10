import os
import re
from dataclasses import dataclass
from typing import Any

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.providers import JSONBaseProvider
from web3.providers.rpc import HTTPProvider
from web3.types import RPCEndpoint, RPCResponse

from chainq.catalog import CatalogToken
from chainq.config import settings
from chainq.errors import ChainqError
from chainq.networks import NETWORKS, Network

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


def _aggregate3(client: "ChainClient", calls: list[tuple[str, bytes]]) -> list[bytes | None]:
    raw = client.w3.eth.call({"to": MULTICALL3_ADDRESS, "data": _encode_aggregate3(calls)})
    return _decode_aggregate3(bytes(raw))


def multicall(client: "ChainClient", calls: list[tuple[str, bytes]], chunk: int = MULTICALL_CHUNK) -> list[bytes | None]:
    if not calls:
        return []
    results: list[bytes | None] = []
    for start in range(0, len(calls), chunk):
        batch = calls[start : start + chunk]
        try:
            results.extend(_aggregate3(client, batch))
        except Exception:
            if chunk <= MULTICALL_MIN_CHUNK:
                raise
            results.extend(multicall(client, batch, chunk // 2))
    return results


FAILOVER_ERROR_CODES = {-32004, -32005, -32601, -32603}
FAILOVER_MESSAGE = re.compile(
    r"rate limit|too many|limit exceeded|not supported|unsupported|upstream|unavailable"
    r"|timed? ?out|forbidden|capacity|overloaded|not able to process",
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


class FallbackProvider(JSONBaseProvider):
    def __init__(self, urls: list[str], chain_id: int):
        super().__init__()
        self.chain_id = chain_id
        self.providers = [
            HTTPProvider(url, request_kwargs={"timeout": settings.rpc_timeout}, exception_retry_configuration=None)
            for url in urls
        ]
        self.active = 0
        self.verified: set[int] = set()
        self.dead: set[int] = set()

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

    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        failures = []
        order = [*range(self.active, len(self.providers)), *range(self.active)]
        for index in order:
            if index in self.dead:
                continue
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
        raise ChainqError(f"all RPC endpoints failed for {method}: {'; '.join(failures)}")


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
    provider = FallbackProvider(urls, network.chain_id)
    w3 = Web3(provider)
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return ChainClient(w3=w3, network=network, provider=provider)


def resolve_address(value: str) -> str:
    value = value.strip()
    if value.lower().endswith(".eth"):
        client = connect(NETWORKS["ethereum"])
        resolved = client.w3.ens.address(value)
        if resolved is None:
            raise ChainqError(f"could not resolve ENS name '{value}'")
        return resolved
    try:
        return Web3.to_checksum_address(value)
    except Exception as exc:
        raise ChainqError(f"invalid address '{value}'") from exc


def erc20(client: ChainClient, address: str):
    return client.w3.eth.contract(address=Web3.to_checksum_address(address), abi=ERC20_ABI)


def sweep_balances(client: ChainClient, address: str, tokens: dict[str, str]) -> tuple[int, list[dict]]:
    items = list(tokens.items())
    calls = [(MULTICALL3_ADDRESS, encode_get_eth_balance(address))]
    for _, token_address in items:
        calls.append((token_address, encode_erc20("balanceOf", [Web3.to_checksum_address(address)])))
        calls.append((token_address, encode_erc20("decimals")))
        calls.append((token_address, encode_erc20("symbol")))
    results = multicall(client, calls)
    wei = decode_uint(results[0]) if results[0] else 0
    rows = []
    for i, (registry_symbol, token_address) in enumerate(items):
        raw, decimals, symbol = results[1 + 3 * i : 4 + 3 * i]
        if raw is None or not decode_uint(raw):
            continue
        rows.append(
            {
                "registry_symbol": registry_symbol,
                "token_address": token_address,
                "symbol": decode_string(symbol) if symbol else registry_symbol.upper(),
                "raw_amount": decode_uint(raw),
                "decimals": decode_uint(decimals) if decimals else 18,
            }
        )
    return wei, rows


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
