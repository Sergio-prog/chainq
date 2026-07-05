import httpx
from web3 import Web3

from chainq import cache, http
from chainq.config import settings
from chainq.errors import ChainqError
from chainq.networks import NETWORKS
from chainq.rpc import ChainClient, connect

SMA_APR_URL = "https://eth-api.lido.fi/v1/protocol/steth/apr/sma"
STETH_ADDRESS = "0xae7ab96520DE3A18E5e111B5EaAb095312D7fe84"
WSTETH_ADDRESS = "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0"


def _read_uint(client: ChainClient, address: str, signature: str) -> int:
    selector = Web3.keccak(text=signature)[:4]
    to = Web3.to_checksum_address(address)
    return int.from_bytes(client.w3.eth.call({"to": to, "data": selector}), "big")


def apr() -> dict:
    key = cache.key_for("lido-apr")
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        resp = http.get(SMA_APR_URL, timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise ChainqError(f"Lido API request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise ChainqError(f"Lido API returned HTTP {resp.status_code}")
    data = resp.json().get("data") or {}
    points = data.get("aprs") or []
    result = {
        "steth_apr_pct": data.get("smaApr"),
        "steth_apr_latest_pct": points[-1].get("apr") if points else None,
        "sma_window_days": len(points),
    }
    cache.put(key, result, ttl=300)
    return result


def onchain() -> dict:
    client = connect(NETWORKS["ethereum"])
    return {
        "total_pooled_eth": _read_uint(client, STETH_ADDRESS, "getTotalPooledEther()") / 1e18,
        "wsteth_rate": _read_uint(client, WSTETH_ADDRESS, "stEthPerToken()") / 1e18,
        "rpc": client.url,
    }
