from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_pct, fmt_usd, humanize_usd
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import aerodrome

app = typer.Typer(no_args_is_help=True, help="Aerodrome: Base DEX TVL, volume, fees, and top pools.")


@app.command()
def stats(
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Protocol TVL (AMM + Slipstream), 24h volume, fees, and AERO price."""
    out = Out(json_out, quiet, verbose, format)
    data = aerodrome.stats()
    lines = [
        f"Aerodrome TVL: {humanize_usd(data['tvl_usd'])} "
        f"(AMM {humanize_usd(data['tvl_amm_usd'])}, CL {humanize_usd(data['tvl_cl_usd'])})",
        f"24h volume: {humanize_usd(data['volume_24h_usd'] or 0)}  "
        f"24h fees: {humanize_usd(data['fees_24h_usd'] or 0)}",
        f"AERO: {fmt_usd(data['aero_price_usd']) if data['aero_price_usd'] else 'n/a'}",
    ]
    out.emit(
        data,
        lines,
        quiet_value=data["tvl_usd"],
        verbose_lines=[
            f"7d volume: {humanize_usd(data['volume_7d_usd'] or 0)}, "
            f"7d fees: {humanize_usd(data['fees_7d_usd'] or 0)}"
        ],
    )


@app.command()
def pools(
    project: Annotated[str, typer.Option("--project", "-p", help="all | v1 (amm) | cl (slipstream)")] = "all",
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    min_tvl: Annotated[float, typer.Option("--min-tvl", help="hide pools with TVL below this")] = 0,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Top Aerodrome pools by TVL, with swap-fee and emission APY split."""
    out = Out(json_out, quiet, verbose, format)
    projects = aerodrome.PROJECT_ALIASES.get(project)
    if projects is None:
        raise ChainqError(f"unknown project '{project}' (use: {', '.join(aerodrome.PROJECT_ALIASES)})")
    rows = [p for p in aerodrome.top_pools(projects, limit + 50) if (p["tvl_usd"] or 0) >= min_tvl][:limit]
    if not rows:
        raise ChainqError("no Aerodrome pools found")
    lines = [
        f"{r['symbol']}: TVL {humanize_usd(r['tvl_usd'] or 0)}  "
        f"APY {fmt_pct(r['apy_pct'], signed=False)} "
        f"(fees {fmt_pct(r['apy_base_pct'] or 0, signed=False)}, rewards {fmt_pct(r['apy_reward_pct'] or 0, signed=False)})"
        for r in rows
    ]
    out.emit(rows, lines, quiet_value="\n".join(r["symbol"] for r in rows))
