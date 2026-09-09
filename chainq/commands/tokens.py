from typing import Annotated

import typer

from chainq import catalog
from chainq.errors import ChainqError
from chainq.fmt import bold, dim
from chainq.networks import NETWORKS, resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt

app = typer.Typer(help="Token catalog: CoinGecko lists + Aave/Pendle/Jupiter wrappers per network, cached daily.")

NetworkOpt = Annotated[str | None, typer.Option("--network", "-n", help="network key, alias, or chain id")]


def _keys(network: str | None) -> list[str]:
    return [resolve_network(network).key] if network else list(NETWORKS)


def _token_line(row: dict) -> str:
    symbol = f"{row['symbol'][:14]:<14}"
    name = f"{(row['name'] or '')[:28]:<28}"
    tag = row["kind"] if row["kind"] != "token" else row["source"]
    return f"{bold(symbol)} {name} {dim(f'{row["network"]:<10}')} {row['address']} {dim(tag)}"


def _status_line(row: dict) -> str:
    sources = ", ".join(f"{name} {count:,}" for name, count in sorted(row["sources"].items()))
    age = "not cached" if row["age_hours"] is None else f"{row['age_hours']}h old"
    flags = " STALE" if row["stale"] else ""
    missing = f" ({row['missing_sources']} source(s) missing)" if row["missing_sources"] else ""
    return f"{dim(f'{row["network"]:<10}')} {bold(f'{row["tokens"]:>6,}')} tokens  {dim(sources)}  {dim(age)}{flags}{missing}"


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="symbol or name fragment")],
    network: NetworkOpt = None,
    limit: Annotated[int, typer.Option("--limit", "-l", help="max rows")] = 20,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Find tokens by symbol or name; exact symbol and curated matches come first."""
    out = Out(json_out, quiet, verbose, format)
    net_key = resolve_network(network).key if network else None
    rows = [t.as_dict() for t in catalog.search(query, net_key, limit)]
    if not rows:
        where = f" on {NETWORKS[net_key].name}" if net_key else ""
        raise ChainqError(f"no catalog token matches '{query}'{where}")
    out.emit(
        rows,
        [_token_line(r) for r in rows],
        quiet_value="\n".join(r["address"] for r in rows),
        verbose_lines=[f"searched {sum(len(catalog.tokens_for(k)) for k in _keys(network)):,} catalog tokens"],
    )


@app.command()
def refresh(
    network: NetworkOpt = None,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Re-download the token lists now instead of waiting for the daily refresh."""
    out = Out(json_out, quiet, verbose, format)
    keys = _keys(network)
    catalog.refresh(keys)
    rows = catalog.status(keys)
    out.emit(rows, [_status_line(r) for r in rows], quiet_value=sum(r["tokens"] for r in rows))


@app.command()
def status(
    network: NetworkOpt = None,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Show catalog size, sources, and cache age per network."""
    out = Out(json_out, quiet, verbose, format)
    rows = catalog.status(_keys(network))
    out.emit(rows, [_status_line(r) for r in rows], quiet_value=sum(r["tokens"] for r in rows))
