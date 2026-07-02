import httpx

from chainq import cache
from chainq.config import settings
from chainq.errors import ChainqError

GRAPHQL_URL = "https://api.v3.aave.com/graphql"

MARKETS_QUERY = """
{
  markets(request: { chainIds: [%d] }) {
    name
    address
    chain { chainId name }
    totalMarketSize
    reserves {
      underlyingToken { symbol name }
      size { usd }
      isFrozen
      isPaused
      supplyInfo { apy { value } total { value } canBeCollateral }
      borrowInfo {
        apy { value }
        total { usd }
        availableLiquidity { usd }
        utilizationRate { value }
      }
    }
  }
}
"""


def markets(chain_id: int) -> list[dict]:
    key = cache.key_for("aave-markets", chain_id)
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        resp = httpx.post(GRAPHQL_URL, json={"query": MARKETS_QUERY % chain_id}, timeout=settings.http_timeout)
    except httpx.HTTPError as exc:
        raise ChainqError(f"Aave API request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise ChainqError(f"Aave API returned HTTP {resp.status_code}")
    payload = resp.json()
    if payload.get("errors"):
        raise ChainqError(f"Aave API error: {payload['errors'][0].get('message', payload['errors'])}")
    result = payload["data"]["markets"]
    cache.put(key, result, ttl=60)
    return result
