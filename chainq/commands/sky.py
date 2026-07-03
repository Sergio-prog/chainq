import typer

from chainq.fmt import fmt_pct, humanize_usd
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import sky

app = typer.Typer(no_args_is_help=True, help="Sky (ex-MakerDAO): savings rates.")


@app.command()
def rate(
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Sky Savings Rate (sUSDS) and legacy DSR (sDAI), read onchain."""
    out = Out(json_out, quiet, verbose, format)
    data = sky.savings()
    rpc = data.pop("rpc")
    lines = [
        f"Sky Savings Rate (sUSDS): {fmt_pct(data['ssr_apy_pct'], signed=False)} APY — "
        f"{humanize_usd(data['susds_deposits_usds'])} USDS deposited",
        f"Legacy DSR (sDAI): {fmt_pct(data['dsr_apy_pct'], signed=False)} APY",
    ]
    out.emit(
        data,
        lines,
        quiet_value=data["ssr_apy_pct"],
        verbose_lines=[
            f"sUSDS: {sky.SUSDS_ADDRESS}, pot: {sky.POT_ADDRESS}",
            f"rpc: {rpc}",
        ],
    )
