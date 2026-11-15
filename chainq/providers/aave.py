
from chainq import cache, http
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
    def fetch() -> list[dict]:
        result = http.fetch_graphql("Aave API", GRAPHQL_URL, MARKETS_QUERY % chain_id).get("markets")
        if not isinstance(result, list):
            raise ChainqError("Aave API returned an unexpected payload (no markets)")
        return result

    return cache.remember(("aave-markets", chain_id), 60, fetch)
