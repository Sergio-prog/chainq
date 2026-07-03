from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_pct, humanize_usd
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import defillama

app = typer.Typer(no_args_is_help=True, help="DefiLlama general metrics for any protocol or chain.")


@app.command()
def protocol(
    query: Annotated[str, typer.Argument(help="protocol slug or name, e.g. aave, morpho, lido")],
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """TVL, chains, fees, and volume for any protocol DefiLlama tracks."""
    out = Out(json_out, quiet, verbose, format)
    p = defillama.find_protocol(query)
    if p is None:
        raise ChainqError(f"no DefiLlama protocol found for '{query}'")
    data = {**p, "fees": defillama.fees(p["slug"]), "dex_volume": defillama.dex_volume(p["slug"]), "source": "defillama"}
    lines = [
        f"{p['name']} ({p['category']}): TVL {humanize_usd(p['tvl_usd'] or 0)}  "
        f"24h {fmt_pct(p['change_1d_pct'])}  7d {fmt_pct(p['change_7d_pct'])}"
        + (f"  mcap {humanize_usd(p['mcap_usd'])}" if p.get("mcap_usd") else "")
    ]
    if p.get("chain_tvls"):
        top = ", ".join(f"{name} {humanize_usd(tvl or 0)}" for name, tvl in list(p["chain_tvls"].items())[:4])
        lines.append(f"  top chains: {top}")
    if data["fees"] and data["fees"].get("total_24h_usd") is not None:
        fees_30d = humanize_usd(data["fees"].get("total_30d_usd") or 0)
        lines.append(f"  fees: {humanize_usd(data['fees']['total_24h_usd'])} 24h, {fees_30d} 30d")
    if data["dex_volume"] and data["dex_volume"].get("total_24h_usd") is not None:
        lines.append(f"  dex volume: {humanize_usd(data['dex_volume']['total_24h_usd'])} 24h")
    out.emit(data, lines, quiet_value=p["tvl_usd"], verbose_lines=[f"slug: {p['slug']}, chains: {', '.join(p['chains'])}"])


@app.command()
def top(
    category: Annotated[str | None, typer.Option("--category", "-c", help="filter by category, e.g. Lending, Dexs")] = None,
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Top protocols by TVL, optionally within a category."""
    out = Out(json_out, quiet, verbose, format)
    rows = defillama.protocols()
    if category:
        rows = [p for p in rows if (p["category"] or "").lower() == category.lower()]
        if not rows:
            categories = sorted({p["category"] for p in defillama.protocols() if p["category"]})
            raise ChainqError(f"no protocols in category '{category}' (known: {', '.join(categories[:30])}...)")
    rows = sorted(rows, key=lambda p: p["tvl_usd"] or 0, reverse=True)[:limit]
    lines = [
        f"{i}. {p['name']} ({p['category']}): {humanize_usd(p['tvl_usd'] or 0)}  24h {fmt_pct(p['change_1d_pct'])}"
        for i, p in enumerate(rows, start=1)
    ]
    out.emit(rows, lines, quiet_value="\n".join(p["slug"] or "" for p in rows))


@app.command()
def chains(
    limit: Annotated[int, typer.Option("--limit", "-l")] = 15,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Chains ranked by DeFi TVL."""
    out = Out(json_out, quiet, verbose, format)
    rows = sorted(defillama.chains(), key=lambda c: c["tvl_usd"] or 0, reverse=True)[:limit]
    lines = [f"{i}. {c['name']}: {humanize_usd(c['tvl_usd'] or 0)}" for i, c in enumerate(rows, start=1)]
    out.emit(rows, lines, quiet_value="\n".join(c["name"] or "" for c in rows))
