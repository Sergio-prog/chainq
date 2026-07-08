from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_pct, humanize_usd
from chainq.networks import resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import morpho

app = typer.Typer(no_args_is_help=True, help="Morpho lending markets and vaults.")

MARKET_SORT = {
    "supplied": lambda m: m["supplied_usd"] or 0,
    "supply-apy": lambda m: m["supply_apy_pct"] or 0,
    "borrow-apy": lambda m: m["borrow_apy_pct"] or 0,
    "utilization": lambda m: m["utilization_pct"] or 0,
}


def _pct(value: float | None) -> str:
    return fmt_pct(value, signed=False)


def _market_row(m: dict) -> dict:
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


@app.command()
def markets(
    network: Annotated[str, typer.Option("--network", "-n", help="network key, alias, or chain id")] = "ethereum",
    coin: Annotated[str | None, typer.Option("--coin", "-c", help="filter by loan or collateral symbol")] = None,
    sort: Annotated[str, typer.Option("--sort", "-s", help="supplied | supply-apy | borrow-apy | utilization")] = "supplied",
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Morpho lending markets: supply/borrow APY, size, utilization."""
    out = Out(json_out, quiet, verbose, format)
    if sort not in MARKET_SORT:
        raise ChainqError(f"unknown sort '{sort}' (use: {', '.join(MARKET_SORT)})")
    net = resolve_network(network)
    rows = [_market_row(m) for m in morpho.markets(net.chain_id)]
    if not rows:
        raise ChainqError(f"no Morpho markets on {net.name}")
    if coin:
        needle = coin.lower()
        rows = [r for r in rows if needle in (r["loan"] or "").lower() or needle in (r["collateral"] or "").lower()]
        if not rows:
            raise ChainqError(f"no Morpho market matching '{coin}' on {net.name}")
    rows = sorted(rows, key=MARKET_SORT[sort], reverse=True)[:limit]
    lines = [
        f"{r['collateral']}/{r['loan']} (lltv {_pct(r['lltv_pct'])}): supply {_pct(r['supply_apy_pct'])}  "
        f"borrow {_pct(r['borrow_apy_pct'])}  supplied {humanize_usd(r['supplied_usd'] or 0)}  "
        f"util {_pct(r['utilization_pct'])}"
        for r in rows
    ]
    out.emit(
        rows,
        lines,
        quiet_value="\n".join(f"{r['collateral']}/{r['loan']}" for r in rows),
        verbose_lines=[
            f"{r['collateral']}/{r['loan']}: net supply {_pct(r['net_supply_apy_pct'])}, "
            f"net borrow {_pct(r['net_borrow_apy_pct'])}, borrowed {humanize_usd(r['borrowed_usd'] or 0)}, "
            f"id {r['market_id']}"
            for r in rows
        ],
    )


@app.command()
def vaults(
    network: Annotated[str, typer.Option("--network", "-n", help="network key, alias, or chain id")] = "ethereum",
    coin: Annotated[str | None, typer.Option("--coin", "-c", help="filter by deposit asset symbol")] = None,
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Morpho vaults ranked by TVL: APY and deposit asset."""
    out = Out(json_out, quiet, verbose, format)
    net = resolve_network(network)
    rows = []
    for v in morpho.vaults(net.chain_id):
        state = v.get("state") or {}
        rows.append(
            {
                "name": v.get("name"),
                "symbol": v.get("symbol"),
                "asset": (v.get("asset") or {}).get("symbol"),
                "apy_pct": state["apy"] * 100 if state.get("apy") is not None else None,
                "net_apy_pct": state["netApy"] * 100 if state.get("netApy") is not None else None,
                "tvl_usd": state.get("totalAssetsUsd"),
            }
        )
    if not rows:
        raise ChainqError(f"no Morpho vaults on {net.name}")
    if coin:
        rows = [r for r in rows if (r["asset"] or "").lower() == coin.lower()]
        if not rows:
            raise ChainqError(f"no Morpho vault for asset '{coin}' on {net.name}")
    rows = rows[:limit]
    lines = [
        f"{r['name']} ({r['symbol']}): APY {_pct(r['apy_pct'])} (net {_pct(r['net_apy_pct'])})  "
        f"TVL {humanize_usd(r['tvl_usd'] or 0)}  [{r['asset']}]"
        for r in rows
    ]
    out.emit(rows, lines, quiet_value="\n".join(r["symbol"] or "" for r in rows))
