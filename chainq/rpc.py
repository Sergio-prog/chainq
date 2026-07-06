import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

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


def multicall(client: "ChainClient", calls: list[tuple[str, bytes]]) -> list[bytes | None]:
    if not calls:
        return []
    contract = client.w3.eth.contract(address=MULTICALL3_ADDRESS, abi=MULTICALL3_ABI)
    results = contract.functions.aggregate3(
        [(Web3.to_checksum_address(target), True, calldata) for target, calldata in calls]
    ).call()
    return [bytes(data) if success and data else None for success, data in results]


@dataclass
class ChainClient:
    w3: Web3
    network: Network
    url: str


def _probe(url: str, network: Network) -> ChainClient:
    w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": settings.rpc_timeout}))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    chain_id = w3.eth.chain_id
    if chain_id != network.chain_id:
        raise ChainqError(f"wrong chain id {chain_id}")
    return ChainClient(w3=w3, network=network, url=url)


def connect(network: Network) -> ChainClient:
    failures = []
    override = os.environ.get(f"CHAINQ_RPC_{network.key.upper()}")
    if override:
        try:
            return _probe(override, network)
        except Exception as exc:
            failures.append(f"{override} ({type(exc).__name__})")
    urls = network.rpc_urls
    if len(urls) == 1:
        try:
            return _probe(urls[0], network)
        except Exception as exc:
            failures.append(f"{urls[0]} ({type(exc).__name__})")
            raise ChainqError(f"all RPC endpoints failed for {network.name}: {'; '.join(failures)}") from None
    pool = ThreadPoolExecutor(max_workers=len(urls))
    try:
        futures = {pool.submit(_probe, url, network): url for url in urls}
        for future in as_completed(futures):
            try:
                return future.result()
            except Exception as exc:
                failures.append(f"{futures[future]} ({type(exc).__name__})")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    raise ChainqError(f"all RPC endpoints failed for {network.name}: {'; '.join(failures)}")


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
