from web3 import Web3

from chainq.networks import NETWORKS
from chainq.rpc import ChainClient, connect

SUSDS_ADDRESS = "0xa3931d71877C0E7a3148CB7Eb4463524FEc27fbD"
POT_ADDRESS = "0x197E90f9FAD81970bA7976f33CbD77088E5D7cf7"
SECONDS_PER_YEAR = 31_536_000
RAY = 10**27


def _read_uint(client: ChainClient, address: str, signature: str) -> int:
    selector = Web3.keccak(text=signature)[:4]
    return int.from_bytes(client.w3.eth.call({"to": address, "data": selector}), "big")


def _apy_pct(per_second_ray: int) -> float:
    return ((per_second_ray / RAY) ** SECONDS_PER_YEAR - 1) * 100


def savings() -> dict:
    client = connect(NETWORKS["ethereum"])
    return {
        "ssr_apy_pct": _apy_pct(_read_uint(client, SUSDS_ADDRESS, "ssr()")),
        "dsr_apy_pct": _apy_pct(_read_uint(client, POT_ADDRESS, "dsr()")),
        "susds_deposits_usds": _read_uint(client, SUSDS_ADDRESS, "totalAssets()") / 1e18,
        "rpc": client.url,
    }
