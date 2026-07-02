from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_pct, humanize_usd
from chainq.networks import resolve_network
from chainq.output import JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import aave

app = typer.Typer(no_args_is_help=True, help="Aave v3 protocol data (lending markets).")

SORT_KEYS = {
    "supplied": lambda r: r["supplied_usd"] or 0,
    "supply-apy": lambda r: r["supply_apy_pct"] or 0,
    "borrow-apy": lambda r: r["borrow_apy_pct"] or 0,
    "utilization": lambda r: r["utilization_pct"] or 0,
}


def _market_label(name: str) -> str:
    return name.removeprefix("AaveV3") or name


def _reserve_row(market: dict, reserve: dict) -> dict:
    supply = reserve.get("supplyInfo") or {}
    borrow = reserve.get("borrowInfo") or {}
    return {
        "market": _market_label(market["name"]),
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


def _row_line(r: dict) -> str:
    borrow = f"borrow {fmt_pct(r['borrow_apy_pct'], signed=False)}" if r["borrow_apy_pct"] is not None else "not borrowable"
    util = f"  util {fmt_pct(r['utilization_pct'], signed=False)}" if r["utilization_pct"] is not None else ""
    return (
        f"{r['symbol']} [{r['market']}]: supply {fmt_pct(r['supply_apy_pct'], signed=False)}  {borrow}  "
        f"supplied {humanize_usd(r['supplied_usd'] or 0)}{util}"
    )


@app.command()
def markets(
    network: Annotated[str, typer.Option("--network", "-n", help="network key, alias, or chain id")] = "ethereum",
    coin: Annotated[str | None, typer.Option("--coin", "-c", help="filter by underlying token symbol")] = None,
    sort: Annotated[str, typer.Option("--sort", "-s", help="supplied | supply-apy | borrow-apy | utilization")] = "supplied",
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
):
    """Aave v3 reserves on a network: supply/borrow APY, size, utilization."""
    out = Out(json_out, quiet, verbose)
    if sort not in SORT_KEYS:
        raise ChainqError(f"unknown sort '{sort}' (use: {', '.join(SORT_KEYS)})")
    net = resolve_network(network)
    aave_markets = aave.markets(net.chain_id)
    if not aave_markets:
        raise ChainqError(f"no Aave v3 market on {net.name}")
    rows = [
        _reserve_row(market, reserve)
        for market in aave_markets
        for reserve in market.get("reserves") or []
        if not reserve.get("isPaused")
    ]
    if coin:
        rows = [r for r in rows if (r["symbol"] or "").lower() == coin.lower()]
        if not rows:
            raise ChainqError(f"no Aave reserve for '{coin}' on {net.name}")
    else:
        rows = sorted(rows, key=SORT_KEYS[sort], reverse=True)[:limit]
    total = sum(float(m["totalMarketSize"]) for m in aave_markets)
    header = (
        f"Aave v3 on {net.name}: {humanize_usd(total)} total market size, "
        f"{len(aave_markets)} market{'s' if len(aave_markets) != 1 else ''} "
        f"({', '.join(_market_label(m['name']) for m in aave_markets)})"
    )
    out.emit(
        {"network": net.key, "total_market_size_usd": total, "reserves": rows},
        [header, *(_row_line(r) for r in rows)],
        quiet_value="\n".join(f"{r['symbol']}" for r in rows),
        verbose_lines=[
            f"{r['symbol']} [{r['market']}]: borrowed {humanize_usd(r['borrowed_usd'] or 0)}, "
            f"available {humanize_usd(r['available_usd'] or 0)}, collateral {r['collateral']}, frozen {r['frozen']}"
            for r in rows
        ],
    )
