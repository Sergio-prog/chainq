
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


def market_label(name: str) -> str:
    return name.removeprefix("AaveV3") or name


def reserve_row(market: dict, reserve: dict) -> dict:
    supply = reserve.get("supplyInfo") or {}
    borrow = reserve.get("borrowInfo") or {}
    return {
        "market": market_label(market["name"]),
        "symbol": (reserve.get("underlyingToken") or {}).get("symbol"),
        "supply_apy_pct": float(supply["apy"]["value"]) * 100 if supply.get("apy") else None,
        "borrow_apy_pct": float(borrow["apy"]["value"]) * 100 if borrow.get("apy") else None,
        "supplied_usd": float(reserve["size"]["usd"]) if reserve.get("size") else None,
        "borrowed_usd": float(borrow["total"]["usd"]) if borrow.get("total") else None,
        "available_usd": float(borrow["availableLiquidity"]["usd"]) if borrow.get("availableLiquidity") else None,
        "utilization_pct": float(borrow["utilizationRate"]["value"]) * 100 if borrow.get("utilizationRate") else None,
        "collateral": supply.get("canBeCollateral"),
        "frozen": reserve.get("isFrozen"),
    }
