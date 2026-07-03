import typer

from chainq.fmt import fmt_pct, fmt_usd, humanize_usd
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import defillama, ethena

app = typer.Typer(no_args_is_help=True, help="Ethena: sUSDe yield and USDe supply.")


def _pct(value: float | None) -> str:
    return fmt_pct(value, signed=False)


@app.command(name="yield")
def yield_(
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """sUSDe staking APY, protocol yield, and USDe supply/peg."""
    out = Out(json_out, quiet, verbose, format)
    data = dict(ethena.yields())
    usde = next((s for s in defillama.stablecoins() if s["symbol"] == "USDe"), None)
    if usde:
        data["usde_mcap_usd"] = usde["mcap_usd"]
        data["usde_price_usd"] = usde["price_usd"]
    lines = [
        f"sUSDe yield: {_pct(data['susde_apy_pct'])} APY "
        f"(30d avg {_pct(data['susde_apy_30d_pct'])}, 90d avg {_pct(data['susde_apy_90d_pct'])})",
        f"protocol yield: {_pct(data['protocol_yield_pct'])} (30d avg {_pct(data['protocol_yield_30d_pct'])})",
    ]
    if usde:
        lines.append(f"USDe supply: {humanize_usd(data['usde_mcap_usd'] or 0)}, price {fmt_usd(data['usde_price_usd'] or 0)}")
    out.emit(
        data,
        lines,
        quiet_value=data["susde_apy_pct"],
        verbose_lines=[f"yield data updated: {data.get('updated')}", f"source: {ethena.YIELD_URL}"],
    )
