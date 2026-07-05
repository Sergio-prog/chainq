import typer

from chainq.fmt import fmt_amount, fmt_pct, fmt_usd, humanize_usd
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import coingecko, lido

app = typer.Typer(no_args_is_help=True, help="Lido: stETH staking APR, TVL, and wstETH rate.")


@app.command()
def apr(
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """stETH staking APR (7d SMA), TVL, and the wstETH/stETH exchange rate."""
    out = Out(json_out, quiet, verbose, format)
    data = lido.apr()
    chain = lido.onchain()
    eth_price = coingecko.try_price_usd("ethereum")
    data["total_pooled_eth"] = chain["total_pooled_eth"]
    data["tvl_usd"] = chain["total_pooled_eth"] * eth_price if eth_price else None
    data["wsteth_rate"] = chain["wsteth_rate"]
    lines = [
        f"Lido stETH APR: {fmt_pct(data['steth_apr_pct'], signed=False)} "
        f"({data['sma_window_days']}d SMA, latest {fmt_pct(data['steth_apr_latest_pct'], signed=False)})",
        f"TVL: {fmt_amount(data['total_pooled_eth'])} ETH"
        + (f" (~{humanize_usd(data['tvl_usd'])})" if data["tvl_usd"] else ""),
        f"wstETH rate: 1 wstETH = {fmt_amount(data['wsteth_rate'])} stETH",
    ]
    out.emit(
        data,
        lines,
        quiet_value=data["steth_apr_pct"],
        verbose_lines=[
            f"stETH: {lido.STETH_ADDRESS}, wstETH: {lido.WSTETH_ADDRESS}",
            f"ETH price: {fmt_usd(eth_price) if eth_price else 'n/a'}",
            f"rpc: {chain['rpc']}",
        ],
    )
