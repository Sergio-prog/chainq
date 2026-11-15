from chainq import cache, http

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


def _query(query: str, field: str, chain_id: int) -> list[dict]:
    def fetch() -> list[dict]:
        data = http.fetch_graphql("Morpho API", GRAPHQL_URL, query % chain_id)
        return ((data.get(field) or {}).get("items")) or []

    return cache.remember(("morpho", field, chain_id), 60, fetch)


def markets(chain_id: int) -> list[dict]:
    return _query(MARKETS_QUERY, "markets", chain_id)


def vaults(chain_id: int) -> list[dict]:
    return _query(VAULTS_QUERY, "vaults", chain_id)
