import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.style import Style
from rich.table import Table
from rich.text import Text

from chainq import cache, catalog, pricing, solana
from chainq.errors import ChainqError
from chainq.fmt import fmt_amount, fmt_usd, short_addr
from chainq.networks import NETWORKS, resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt, render_rich
from chainq.progress import Progress
from chainq.providers import coingecko, hyperliquid, lighter
from chainq.rpc import connect, erc20, resolve_address, sweep_catalog
from chainq.tokens import TOKENS


def _scan_evm_legacy(client, net, address: str) -> list[dict]:
    assets = []
    wei = client.w3.eth.get_balance(address)
    if wei:
        assets.append(
            {
                "network": net.key,
                "symbol": net.native_symbol,
                "token_address": None,
                "amount": str(Decimal(wei) / Decimal(10**18)),
                "coingecko_id": net.native_coingecko_id,
            }
        )
    for symbol, token_address in TOKENS.get(net.key, {}).items():
        if token_address == net.native_erc20:
            continue
        contract = erc20(client, token_address)
        raw = contract.functions.balanceOf(address).call()
        if not raw:
            continue
        decimals = contract.functions.decimals().call()
        assets.append(
            {
                "network": net.key,
                "symbol": contract.functions.symbol().call(),
                "token_address": token_address,
                "amount": str(Decimal(raw) / Decimal(10**decimals)),
                "kind": "token",
                "source": "registry",
                "coingecko_id": coingecko.SYMBOL_TO_ID.get(symbol),
            }
        )
    return assets


def _scan_evm(net_key: str, address: str) -> list[dict]:
    net = NETWORKS[net_key]
    client = connect(net)
    try:
        wei, rows = sweep_catalog(client, address, list(catalog.tokens_for(net.key)))
    except Exception:
        return _scan_evm_legacy(client, net, address)
    assets = []
    if wei:
        assets.append(
            {
                "network": net.key,
                "symbol": net.native_symbol,
                "token_address": None,
                "amount": str(Decimal(wei) / Decimal(10**18)),
                "coingecko_id": net.native_coingecko_id,
            }
        )
    for row in rows:
        if row["token_address"] == net.native_erc20:
            continue
        token = row["catalog"]
        assets.append(
            {
                "network": net.key,
                "symbol": row["symbol"],
                "token_address": row["token_address"],
                "amount": str(Decimal(row["raw_amount"]) / Decimal(10 ** row["decimals"])),
                "kind": token.kind,
                "source": token.source,
                "coingecko_id": token.coingecko_id,
            }
        )
    return assets


def _scan_solana(address: str) -> list[dict]:
    assets = []
    lamports = solana.get_balance(address)
    if lamports:
        assets.append(
            {
                "network": "solana",
                "symbol": "SOL",
                "token_address": None,
                "amount": str(solana.lamports_to_sol(lamports)),
                "coingecko_id": "solana",
            }
        )
    for account in solana.token_accounts(address):
        if not account["raw_amount"]:
            continue
        token = catalog.lookup("solana", account["mint"])
        assets.append(
            {
                "network": "solana",
                "symbol": token.symbol if token else short_addr(account["mint"]),
                "token_address": account["mint"],
                "amount": account["amount"],
                "kind": token.kind if token else "unknown",
                "source": token.source if token else None,
                "coingecko_id": token.coingecko_id if token else None,
            }
        )
    return assets


def _scan_network(net_key: str, address: str) -> list[dict]:
    if NETWORKS[net_key].kind == "solana":
        return _scan_solana(address)
    return _scan_evm(net_key, address)


def _scan_hyperliquid(address: str) -> list[dict]:
    assets: list[dict] = []
    try:
        state = hyperliquid.clearinghouse_state(address)
        equity = float((state.get("marginSummary") or {}).get("accountValue") or 0)
        if equity:
            assets.append(
                {
                    "network": "hyperliquid",
                    "symbol": "perp equity (USDC)",
                    "token_address": None,
                    "amount": str(equity),
                    "price_usd": 1.0,
                    "price_source": "hyperliquid",
                    "value_usd": equity,
                }
            )
    except Exception:
        pass
    try:
        balances = hyperliquid.spot_balances(address)
    except Exception:
        return assets
    if not balances:
        return assets
    prices = {"USDC": 1.0}
    for m in hyperliquid.spot_markets():
        price = m["mid_price"] or m["mark_price"]
        if m["base"] and price:
            prices[m["base"]] = price
    for b in balances:
        total = float(b.get("total") or 0)
        if not total:
            continue
        price = prices.get(b.get("coin"))
        assets.append(
            {
                "network": "hyperliquid",
                "symbol": b.get("coin"),
                "token_address": None,
                "amount": str(total),
                "price_usd": price,
                "price_source": "hyperliquid" if price is not None else None,
                "value_usd": total * price if price is not None else None,
            }
        )
    return assets


def _scan_lighter(address: str) -> list[dict]:
    try:
        acc = lighter.account(address)
        balances = lighter.asset_balances(acc)
    except Exception:
        return []
    assets: list[dict] = []
    equity = float(acc.get("total_asset_value") or 0)
    if equity:
        assets.append(
            {
                "network": "lighter",
                "symbol": "perp equity (USDC)",
                "token_address": None,
                "amount": str(equity),
                "price_usd": 1.0,
                "price_source": "lighter",
                "value_usd": equity,
            }
        )
    for b in balances:
        amount = b["total"] - (b["margin"] if b["coin"] == "USDC" else 0)
        if not amount:
            continue
        price = b["price_usd"]
        assets.append(
            {
                "network": "lighter",
                "symbol": b["coin"],
                "token_address": None,
                "amount": str(amount),
                "price_usd": price,
                "price_source": "lighter" if price is not None else None,
                "value_usd": amount * price if price is not None else None,
            }
        )
    return assets


def _resolve_scan_target(address: str, networks: list[str] | None) -> tuple[str, list[str]]:
    value = address.strip()
    if solana.looks_like_solana(value):
        kind, addr = "solana", solana.resolve_solana_address(value)
    else:
        kind, addr = "evm", resolve_address(value)
    if networks:
        requested = [resolve_network(n) for n in networks]
        mismatched = [n.key for n in requested if n.kind != kind]
        if mismatched:
            raise ChainqError(
                f"{', '.join(mismatched)} cannot hold this address "
                f"({'base58 Solana pubkey' if kind == 'solana' else '0x EVM address'})"
            )
        return addr, [n.key for n in requested]
    return addr, [key for key, net in NETWORKS.items() if net.kind == kind]


MAX_SCAN_WORKERS = 16
SCAN_TTL = 300
DEFI_SOURCE = "defi"
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


def _resolve_targets(inputs: list[str], networks: list[str] | None) -> list[tuple[str, str, list[str]]]:
    targets: dict[str, tuple[str, str, list[str]]] = {}
    invalid: list[str] = []
    for value in inputs:
        try:
            addr, keys = _resolve_scan_target(value, networks)
        except ChainqError as exc:
            if len(inputs) == 1:
                raise
            invalid.append(f"{value} ({exc})")
            continue
        targets.setdefault(addr, (value, addr, keys))
    if invalid:
        raise ChainqError("cannot scan: " + "; ".join(invalid))
    return list(targets.values())


def _scan_defi(address: str) -> list[dict]:
    return _scan_hyperliquid(address) + _scan_lighter(address)


def _scan_job(addr: str, source: str) -> list[dict]:
    return _scan_defi(addr) if source == DEFI_SOURCE else _scan_network(source, addr)


def _scan_wallets(
    targets: list[tuple[str, str, list[str]]], defi: bool, use_cache: bool
) -> tuple[dict[str, list[dict]], dict[str, list[str]], int]:
    jobs = [(addr, key) for _, addr, keys in targets for key in keys]
    if defi:
        jobs += [(addr, DEFI_SOURCE) for _, addr, _ in targets if addr.startswith("0x")]
    keys = {job: cache.key_for("portfolio", *job) for job in jobs}
    cached = cache.get_many(list(keys.values())) if use_cache else {}
    assets: dict[str, list[dict]] = {addr: [] for _, addr, _ in targets}
    unreachable: dict[str, list[str]] = {addr: [] for _, addr, _ in targets}
    for (addr, _), key in keys.items():
        assets[addr].extend(cached.get(key, []))
    pending = [job for job in jobs if keys[job] not in cached]
    scanned: dict[tuple[str, str], list[dict]] = {}
    if pending:
        wallets = len({addr for addr, _ in pending})
        with Progress(f"scanning {wallets} wallet(s)", len(pending)) as progress:
            with ThreadPoolExecutor(max_workers=min(MAX_SCAN_WORKERS, len(pending))) as pool:
                futures = {pool.submit(_scan_job, *job): job for job in pending}
                for future in as_completed(futures):
                    job = futures[future]
                    progress.advance()
                    try:
                        scanned[job] = future.result()
                    except Exception:
                        unreachable[job[0]].append(job[1])
            progress.stage("pricing assets")
            pricing.price_assets([a for (_, source), found in scanned.items() if source != DEFI_SOURCE for a in found])
        cache.put_many({keys[job]: found for job, found in scanned.items()}, SCAN_TTL)
        for (addr, _), found in scanned.items():
            assets[addr].extend(found)
    return assets, {addr: sorted(keys) for addr, keys in unreachable.items()}, len(jobs) - len(pending)


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


def _hidden_note(hidden: int, show_all: bool, min_usd: float) -> str:
    reason = "unpriced" if show_all else f"below {fmt_usd(min_usd)} or unpriced; --all shows them"
    return f"  ({hidden} asset(s) hidden: {reason})"


def _single_report(
    out: Out, wallet: dict, keys: list[str], defi: bool, show_all: bool, min_usd: float, cache_hits: int
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
    out.emit(
        data,
        lines,
        quiet_value=total,
        verbose_lines=[
            f"scanned {len(keys)} network(s), {sum(len(catalog.tokens_for(k)) for k in keys):,} catalog tokens"
            + (" + Hyperliquid + Lighter" if defi else ""),
            f"address: {addr}",
            _cache_note(cache_hits),
        ],
    )


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
        str, typer.Option("--sort", help="wallet order: balance (default, largest first) | input | address")
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
    targets = _resolve_targets(_gather_inputs(addresses, file, paste), networks)
    found, unreachable, cache_hits = _scan_wallets(targets, defi, not no_cache)
    wallets = []
    for value, addr, _ in targets:
        assets, hidden = _filter_assets(found[addr], min_usd, show_all, hide_unpriced)
        by_network: dict[str, float] = {}
        for a in assets:
            by_network[a["network"]] = by_network.get(a["network"], 0) + (a["value_usd"] or 0)
        wallets.append(
            {
                "input": value,
                "address": addr,
                "assets": assets,
                "hidden": hidden,
                "unreachable": unreachable[addr],
                "networks": {n: usd for n, usd in by_network.items() if usd},
                "total_usd": sum(by_network.values()),
            }
        )
    if len(wallets) == 1 and by is None:
        _single_report(out, wallets[0], targets[0][2], defi, show_all, min_usd, cache_hits)
        return
    if all(not w["assets"] and w["unreachable"] for w in wallets):
        raise ChainqError("no assets found; every scanned network was unreachable")
    view = {"network": _network_view, "total": _total_view, "token": _token_view}[by or "network"]
    data, table = view(_sort_wallets(wallets, sort), short)
    lines = render_rich(table)
    hidden = sum(w["hidden"] for w in wallets)
    failed: dict[str, int] = {}
    for w in wallets:
        for key in w["unreachable"]:
            failed[key] = failed.get(key, 0) + 1
    data = {
        "wallets_scanned": len(wallets),
        "hidden_assets": hidden,
        "unreachable": failed,
        **data,
    }
    if hidden:
        lines.append(_hidden_note(hidden, show_all, min_usd).strip())
    if failed:
        lines.append("(unreachable: " + ", ".join(f"{k} for {n} wallet(s)" for k, n in sorted(failed.items())) + ")")
    keys = sorted({k for _, _, ks in targets for k in ks})
    out.emit(
        data,
        lines,
        quiet_value=data["total_usd"],
        verbose_lines=[
            f"scanned {len(wallets)} wallet(s) × {len(keys)} network(s)" + (" + Hyperliquid + Lighter" if defi else ""),
            _cache_note(cache_hits),
            "links: wallet labels open DeBank in terminals with OSC 8 hyperlink support",
        ],
    )
