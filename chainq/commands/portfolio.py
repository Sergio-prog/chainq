import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.style import Style
from rich.table import Table
from rich.text import Text

from chainq import catalog
from chainq.errors import ChainqError
from chainq.fmt import fmt_amount, fmt_usd, short_addr
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt, render_rich
from chainq.wallets import SCAN_TTL, ScanResult, Target, resolve_targets, scan_wallets

VIEWS = ("network", "total", "token")


def _split_addresses(text: str) -> list[str]:
    return [item for line in text.splitlines() for item in re.split(r"[\s,;]+", line.split("#", 1)[0]) if item]


def _read_source(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    try:
        return Path(source).expanduser().read_text()
    except OSError as exc:
        raise ChainqError(f"cannot read address file '{source}': {exc.strerror}") from exc


CLIPBOARD_COMMANDS = (
    ["pbpaste"],
    ["wl-paste", "--no-newline"],
    ["xclip", "-selection", "clipboard", "-o"],
    ["xsel", "--clipboard", "--output"],
    ["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard"],
)


def _read_clipboard() -> str:
    for command in CLIPBOARD_COMMANDS:
        if not shutil.which(command[0]):
            continue
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout
    raise ChainqError("no clipboard tool found (install pbpaste, wl-paste, xclip, or xsel), or pipe addresses via -")


def _gather_inputs(addresses: list[str] | None, file: str | None, paste: bool = False) -> list[str]:
    values: list[str] = []
    if paste:
        values += _split_addresses(_read_clipboard())
    for value in addresses or []:
        values += _split_addresses(_read_source("-") if value == "-" else value)
    if file:
        values += _split_addresses(_read_source(file))
    if not values:
        raise ChainqError("no addresses given (pass them as arguments, --file PATH, --paste, or - for stdin)")
    return list(dict.fromkeys(values))


def _filter_assets(assets: list[dict], min_usd: float, show_all: bool, hide_unpriced: bool) -> tuple[list[dict], int]:
    kept = []
    for a in assets:
        if a["value_usd"] is None:
            trusted = a["token_address"] is None or a.get("source") == "registry"
            visible = (show_all or trusted) and not hide_unpriced
        else:
            visible = show_all or a["value_usd"] >= min_usd
        if visible:
            kept.append(a)
    kept.sort(key=lambda a: (a["value_usd"] is None, -(a["value_usd"] or 0)))
    return kept, len(assets) - len(kept)


def _wallet_report(target: Target, scan: ScanResult, min_usd: float, show_all: bool, hide_unpriced: bool) -> dict:
    assets, hidden = _filter_assets(scan.assets[target.address], min_usd, show_all, hide_unpriced)
    by_network: dict[str, float] = {}
    for asset in assets:
        by_network[asset["network"]] = by_network.get(asset["network"], 0) + (asset["value_usd"] or 0)
    return {
        "input": target.input,
        "address": target.address,
        "assets": assets,
        "hidden": hidden,
        "unreachable": scan.unreachable[target.address],
        "networks": {network: usd for network, usd in by_network.items() if usd},
        "total_usd": sum(by_network.values()),
    }


def _hidden_note(hidden: int, show_all: bool, min_usd: float) -> str:
    reason = "unpriced" if show_all else f"below {fmt_usd(min_usd)} or unpriced; --all shows them"
    return f"  ({hidden} asset(s) hidden: {reason})"


def _single_report(
    out: Out, wallet: dict, keys: tuple[str, ...], defi: bool, show_all: bool, min_usd: float, scan: ScanResult
) -> None:
    address, addr, assets = wallet["input"], wallet["address"], wallet["assets"]
    unreachable, hidden, total = wallet["unreachable"], wallet["hidden"], wallet["total_usd"]
    if not assets and unreachable:
        raise ChainqError(f"no assets found; unreachable networks: {', '.join(unreachable)}")
    data = {
        "address": addr,
        "input": address,
        "networks_scanned": len(keys) - len(unreachable),
        "unreachable": unreachable,
        "hidden_assets": hidden,
        "price_failures": scan.price_failures,
        "total_usd": total,
        "assets": assets,
    }
    label = f"{address} ({short_addr(addr)})" if address != addr else short_addr(addr)
    lines = [f"{label}: ≈ {fmt_usd(total)} across {len({a['network'] for a in assets})} network(s)"]
    lines += [
        f"  {a['network']}: {fmt_amount(a['amount'])} {a['symbol']}"
        + (f" (~{fmt_usd(a['value_usd'])})" if a["value_usd"] is not None else "")
        for a in assets
    ]
    if hidden:
        lines.append(_hidden_note(hidden, show_all, min_usd))
    if unreachable:
        lines.append(f"  (unreachable: {', '.join(unreachable)})")
    if scan.price_failures:
        lines.append(f"  {_price_failure_note(scan.price_failures)}")
    out.emit(
        data,
        lines,
        quiet_value=total,
        verbose_lines=[
            f"scanned {len(keys)} network(s), {sum(len(catalog.tokens_for(k)) for k in keys):,} catalog tokens"
            + (" + Hyperliquid + Lighter" if defi else ""),
            f"address: {addr}",
            _cache_note(scan.cache_hits),
        ],
    )


def _price_failure_note(sources: list[str]) -> str:
    return f"(price sources failed: {', '.join(sources)}; some values are missing, rerun shortly)"


def _cache_note(hits: int) -> str:
    return f"cache: {hits} scan(s) reused (≤{SCAN_TTL // 60} min old; --no-cache rescans)"


SORTS = ("balance", "input", "address")


def _sort_wallets(wallets: list[dict], sort: str) -> list[dict]:
    if sort == "balance":
        return sorted(wallets, key=lambda w: -w["total_usd"])
    if sort == "address":
        return sorted(wallets, key=lambda w: w["address"].lower())
    return wallets


def _wallet_cell(wallet: dict, short: bool) -> Text:
    addr = wallet["address"]
    text = short_addr(addr) if short else addr
    url = f"https://debank.com/profile/{addr}" if addr.startswith("0x") else None
    return Text(text, style=Style(color="cyan", link=url))


def _usd_cell(value: float | None, strong: bool = False) -> Text:
    if not value:
        return Text("·", style="dim")
    text = f"${value:,.0f}" if value >= 100 else f"${value:,.2f}"
    return Text(text, style="bold green" if strong else "green")


def _table(*columns: tuple[str, str]) -> Table:
    table = Table(box=box.HEAVY_HEAD, show_footer=True, header_style="bold", footer_style="bold")
    for name, justify in columns:
        table.add_column(name, justify=justify, no_wrap=True)
    return table


def _network_view(wallets: list[dict], short: bool) -> tuple[dict, Table]:
    per_network: dict[str, float] = {}
    for w in wallets:
        for net, usd in w["networks"].items():
            per_network[net] = per_network.get(net, 0) + usd
    columns = sorted((n for n, usd in per_network.items() if usd), key=lambda n: -per_network[n])
    grand = sum(w["total_usd"] for w in wallets)
    rows = [
        {"address": w["address"], **{n: w["networks"].get(n, 0.0) for n in columns}, "total_usd": w["total_usd"]}
        for w in wallets
    ]
    table = _table(("wallet", "left"), *((n, "right") for n in columns), ("total", "right"))
    for w in wallets:
        table.add_row(
            _wallet_cell(w, short),
            *(_usd_cell(w["networks"].get(n)) for n in columns),
            _usd_cell(w["total_usd"], strong=True),
        )
    footers = [Text(f"{len(wallets)} wallet(s)", style="dim"), *(_usd_cell(per_network[n]) for n in columns)]
    for column, footer in zip(table.columns, [*footers, _usd_cell(grand, strong=True)], strict=True):
        column.footer = footer
    return {"total_usd": grand, "networks": columns, "wallets": rows}, table


def _total_view(wallets: list[dict], short: bool) -> tuple[dict, Table]:
    grand = sum(w["total_usd"] for w in wallets)
    rows = [{"address": w["address"], "networks": len(w["networks"]), "total_usd": w["total_usd"]} for w in wallets]
    table = _table(("wallet", "left"), ("networks", "right"), ("total", "right"))
    for w in wallets:
        table.add_row(_wallet_cell(w, short), str(len(w["networks"])), _usd_cell(w["total_usd"], strong=True))
    footers = [Text(f"{len(wallets)} wallet(s)", style="dim"), "", _usd_cell(grand, strong=True)]
    for column, footer in zip(table.columns, footers, strict=True):
        column.footer = footer
    return {"total_usd": grand, "wallets": rows}, table


def _token_view(wallets: list[dict], short: bool) -> tuple[dict, Table]:
    grand = sum(w["total_usd"] for w in wallets)
    rows = [
        {
            "address": w["address"],
            "network": a["network"],
            "symbol": a["symbol"],
            "token_address": a["token_address"],
            "amount": a["amount"],
            "price_usd": a["price_usd"],
            "value_usd": a["value_usd"],
        }
        for w in wallets
        for a in w["assets"]
    ]
    table = _table(("wallet", "left"), ("token", "left"), ("network", "left"), ("amount", "right"), ("value", "right"))
    for w in wallets:
        table.add_row(_wallet_cell(w, short), "", "", "", _usd_cell(w["total_usd"], strong=True))
        for a in w["assets"]:
            table.add_row(
                "",
                Text(a["symbol"], style="magenta"),
                Text(a["network"], style="dim"),
                fmt_amount(a["amount"]),
                _usd_cell(a["value_usd"]),
            )
        table.add_section()
    footers = [Text(f"{len(wallets)} wallet(s)", style="dim"), "", "", "", _usd_cell(grand, strong=True)]
    for column, footer in zip(table.columns, footers, strict=True):
        column.footer = footer
    return {"total_usd": grand, "assets": rows}, table


def portfolio(
    addresses: Annotated[
        list[str] | None,
        typer.Argument(help="wallet address(es) (0x or Solana base58), ENS, or .sol names; - reads stdin"),
    ] = None,
    file: Annotated[
        str | None, typer.Option("--file", "-F", help="file with addresses (one per line, commas ok); - for stdin")
    ] = None,
    paste: Annotated[
        bool, typer.Option("--paste", "-p", help="read addresses from the clipboard (pbpaste, wl-paste, xclip, xsel)")
    ] = False,
    by: Annotated[
        str | None,
        typer.Option("--by", help="multi-wallet view: network (default) | total | token; forces it for one address"),
    ] = None,
    networks: Annotated[list[str] | None, typer.Option("--network", "-n", help="network(s) to scan; default: all")] = None,
    min_usd: Annotated[float, typer.Option("--min-usd", help="hide assets worth less than this")] = 1.0,
    show_all: Annotated[bool, typer.Option("--all", help="also show unpriced assets and those below --min-usd")] = False,
    hide_unpriced: Annotated[
        bool, typer.Option("--hide-unpriced", help="drop unpriced assets even with --all (default without --all)")
    ] = False,
    defi: Annotated[
        bool, typer.Option("--defi", help="also fold in Hyperliquid and Lighter perp equity and spot balances")
    ] = False,
    sort: Annotated[
        str, typer.Option("--sort", "-s", help="wallet order: balance (default, largest first) | input | address")
    ] = "balance",
    short: Annotated[bool, typer.Option("--short", help="abbreviate wallet addresses (0x1234…abcd)")] = False,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help=f"rescan instead of reusing results cached for {SCAN_TTL // 60} min")
    ] = False,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Sweep native + every catalog token across networks with USD totals, for one wallet or many."""
    out = Out(json_out, quiet, verbose, format)
    if by is not None and by not in VIEWS:
        raise ChainqError(f"unknown view '{by}' (use: {' | '.join(VIEWS)})")
    if sort not in SORTS:
        raise ChainqError(f"unknown sort '{sort}' (use: {' | '.join(SORTS)})")
    targets = resolve_targets(_gather_inputs(addresses, file, paste), networks)
    scan = scan_wallets(targets, defi, not no_cache)
    reports = [_wallet_report(target, scan, min_usd, show_all, hide_unpriced) for target in targets]
    if len(reports) == 1 and by is None:
        _single_report(out, reports[0], targets[0].networks, defi, show_all, min_usd, scan)
        return
    if all(not w["assets"] and w["unreachable"] for w in reports):
        raise ChainqError("no assets found; every scanned network was unreachable")
    view = {"network": _network_view, "total": _total_view, "token": _token_view}[by or "network"]
    data, table = view(_sort_wallets(reports, sort), short)
    lines = render_rich(table)
    hidden = sum(w["hidden"] for w in reports)
    failed = dict(Counter(key for w in reports for key in w["unreachable"]))
    data = {
        "wallets_scanned": len(reports),
        "hidden_assets": hidden,
        "unreachable": failed,
        "price_failures": scan.price_failures,
        **data,
    }
    if hidden:
        lines.append(_hidden_note(hidden, show_all, min_usd).strip())
    if failed:
        lines.append("(unreachable: " + ", ".join(f"{k} for {n} wallet(s)" for k, n in sorted(failed.items())) + ")")
    if scan.price_failures:
        lines.append(_price_failure_note(scan.price_failures))
    keys = sorted({key for target in targets for key in target.networks})
    out.emit(
        data,
        lines,
        quiet_value=data["total_usd"],
        verbose_lines=[
            f"scanned {len(reports)} wallet(s) × {len(keys)} network(s)" + (" + Hyperliquid + Lighter" if defi else ""),
            _cache_note(scan.cache_hits),
            "links: wallet labels open DeBank in terminals with OSC 8 hyperlink support",
        ],
    )
