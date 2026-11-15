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


def market_row(m: dict) -> dict:
    state = m.get("state") or {}
    lltv = float(m["lltv"]) / 1e18 * 100 if m.get("lltv") else None
    return {
        "collateral": (m.get("collateralAsset") or {}).get("symbol") or "idle",
        "loan": (m.get("loanAsset") or {}).get("symbol"),
        "lltv_pct": lltv,
        "supply_apy_pct": state["supplyApy"] * 100 if state.get("supplyApy") is not None else None,
        "net_supply_apy_pct": state["netSupplyApy"] * 100 if state.get("netSupplyApy") is not None else None,
        "borrow_apy_pct": state["borrowApy"] * 100 if state.get("borrowApy") is not None else None,
        "net_borrow_apy_pct": state["netBorrowApy"] * 100 if state.get("netBorrowApy") is not None else None,
        "supplied_usd": state.get("supplyAssetsUsd"),
        "borrowed_usd": state.get("borrowAssetsUsd"),
        "utilization_pct": state["utilization"] * 100 if state.get("utilization") is not None else None,
        "market_id": m.get("marketId"),
    }


def vault_row(vault: dict) -> dict:
    state = vault.get("state") or {}
    return {
        "name": vault.get("name"),
        "symbol": vault.get("symbol"),
        "asset": (vault.get("asset") or {}).get("symbol"),
        "apy_pct": state["apy"] * 100 if state.get("apy") is not None else None,
        "net_apy_pct": state["netApy"] * 100 if state.get("netApy") is not None else None,
        "tvl_usd": state.get("totalAssetsUsd"),
    }
