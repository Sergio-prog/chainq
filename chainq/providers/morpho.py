import httpx

from chainq import cache, http
from chainq.config import settings
from chainq.errors import ChainqError

GRAPHQL_URL = "https://api.morpho.org/graphql"

MARKETS_QUERY = """
{
  markets(first: 100, orderBy: SupplyAssetsUsd, orderDirection: Desc, where: { chainId_in: [%d], listed: true }) {
    items {
      marketId
      lltv
      loanAsset { symbol }
      collateralAsset { symbol }
      state {
        supplyApy
        netSupplyApy
        borrowApy
        netBorrowApy
        supplyAssetsUsd
        borrowAssetsUsd
        utilization
      }
    }
  }
}
"""

VAULTS_QUERY = """
{
  vaults(first: 100, orderBy: TotalAssetsUsd, orderDirection: Desc, where: { chainId_in: [%d] }) {
    items {
      name
      symbol
      asset { symbol }
      state { apy netApy totalAssetsUsd }
    }
  }
}
"""


def _query(query: str, cache_tag: str, chain_id: int) -> list[dict]:
    key = cache.key_for("morpho", cache_tag, chain_id)
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        resp = http.post(GRAPHQL_URL, json={"query": query % chain_id}, timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise ChainqError(f"Morpho API request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise ChainqError(f"Morpho API returned HTTP {resp.status_code}")
    payload = resp.json()
    if payload.get("errors"):
        raise ChainqError(f"Morpho API error: {payload['errors'][0].get('message', payload['errors'])}")
    result = payload["data"][cache_tag]["items"]
    cache.put(key, result, ttl=60)
    return result


def markets(chain_id: int) -> list[dict]:
    return _query(MARKETS_QUERY, "markets", chain_id)


def vaults(chain_id: int) -> list[dict]:
    return _query(VAULTS_QUERY, "vaults", chain_id)
