import os
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
]


@dataclass
class ChainClient:
    w3: Web3
    network: Network
    url: str


def _candidate_urls(network: Network) -> tuple[str, ...]:
    override = os.environ.get(f"CHAINQ_RPC_{network.key.upper()}")
    if override:
        return (override, *network.rpc_urls)
    return network.rpc_urls


def connect(network: Network) -> ChainClient:
    failures = []
    for url in _candidate_urls(network):
        try:
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": settings.rpc_timeout}))
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            chain_id = w3.eth.chain_id
        except Exception as exc:
            failures.append(f"{url} ({type(exc).__name__})")
            continue
        if chain_id != network.chain_id:
            failures.append(f"{url} (wrong chain id {chain_id})")
            continue
        return ChainClient(w3=w3, network=network, url=url)
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
