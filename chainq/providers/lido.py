from chainq import cache, http
from chainq.evm_address import checksum, selector
from chainq.networks import NETWORKS
from chainq.rpc import ChainClient, connect

SMA_APR_URL = "https://eth-api.lido.fi/v1/protocol/steth/apr/sma"
STETH_ADDRESS = "0xae7ab96520DE3A18E5e111B5EaAb095312D7fe84"
WSTETH_ADDRESS = "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0"


def _read_uint(client: ChainClient, address: str, signature: str) -> int:
    return int.from_bytes(client.w3.eth.call({"to": checksum(address), "data": selector(signature)}), "big")


def _fetch_apr() -> dict:
    data = http.fetch_json("Lido API", SMA_APR_URL).get("data") or {}
    points = data.get("aprs") or []
    return {
        "steth_apr_pct": data.get("smaApr"),
        "steth_apr_latest_pct": points[-1].get("apr") if points else None,
        "sma_window_days": len(points),
    }


def apr() -> dict:
    return cache.remember(("lido-apr",), 300, _fetch_apr)


def onchain() -> dict:
    client = connect(NETWORKS["ethereum"])
    return {
        "total_pooled_eth": _read_uint(client, STETH_ADDRESS, "getTotalPooledEther()") / 1e18,
        "wsteth_rate": _read_uint(client, WSTETH_ADDRESS, "stEthPerToken()") / 1e18,
        "rpc": client.url,
    }
