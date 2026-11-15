from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from decimal import Decimal

from chainq import cache, catalog, pricing, solana
from chainq.errors import ChainqError
from chainq.evm_address import resolve_address
from chainq.fmt import short_addr
from chainq.networks import NETWORKS, resolve_network
from chainq.progress import Progress
from chainq.providers import coingecko, hyperliquid, lighter
from chainq.rpc import connect, erc20, sweep_catalog
from chainq.tokens import TOKENS

MAX_SCAN_WORKERS = 16
SCAN_TTL = 300
PERP_EQUITY = "perp equity (USDC)"


@dataclass(frozen=True)
class Target:
    input: str
    address: str
    networks: tuple[str, ...]


@dataclass
class ScanResult:
    assets: dict[str, list[dict]]
    unreachable: dict[str, list[str]]
    cache_hits: int
    price_failures: list[str]


def _asset(network: str, symbol: str, amount: object, token_address: str | None = None, **extra) -> dict:
    return {"network": network, "symbol": symbol, "token_address": token_address, "amount": str(amount), **extra}


def _venue_asset(venue: str, symbol: str, amount: float, price: float | None) -> dict:
    return _asset(
        venue,
        symbol,
        amount,
        price_usd=price,
        price_source=venue if price is not None else None,
        value_usd=amount * price if price is not None else None,
    )


def _native_asset(net, wei: int) -> dict:
    return _asset(net.key, net.native_symbol, Decimal(wei) / Decimal(10**18), coingecko_id=net.native_coingecko_id)


def _scan_evm_registry(client, net, address: str) -> list[dict]:
    wei = client.w3.eth.get_balance(address)
    assets = [_native_asset(net, wei)] if wei else []
    for symbol, token_address in TOKENS.get(net.key, {}).items():
        if token_address == net.native_erc20:
            continue
        contract = erc20(client, token_address)
        raw = contract.functions.balanceOf(address).call()
        if not raw:
            continue
        decimals = contract.functions.decimals().call()
        assets.append(
            _asset(
                net.key,
                contract.functions.symbol().call(),
                Decimal(raw) / Decimal(10**decimals),
                token_address,
                kind="token",
                source="registry",
                coingecko_id=coingecko.SYMBOL_TO_ID.get(symbol),
            )
        )
    return assets


def _scan_evm(net_key: str, address: str) -> list[dict]:
    net = NETWORKS[net_key]
    client = connect(net)
    try:
        wei, rows = sweep_catalog(client, address, list(catalog.tokens_for(net.key)))
    except Exception:
        return _scan_evm_registry(client, net, address)
    assets = [_native_asset(net, wei)] if wei else []
    for row in rows:
        if row["token_address"] == net.native_erc20:
            continue
        token = row["catalog"]
        assets.append(
            _asset(
                net.key,
                row["symbol"],
                Decimal(row["raw_amount"]) / Decimal(10 ** row["decimals"]),
                row["token_address"],
                kind=token.kind,
                source=token.source,
                coingecko_id=token.coingecko_id,
            )
        )
    return assets


def _scan_solana(address: str) -> list[dict]:
    lamports = solana.get_balance(address)
    assets = [_asset("solana", "SOL", solana.lamports_to_sol(lamports), coingecko_id="solana")] if lamports else []
    for account in solana.token_accounts(address):
        if not account["raw_amount"]:
            continue
        token = catalog.lookup("solana", account["mint"])
        assets.append(
            _asset(
                "solana",
                token.symbol if token else short_addr(account["mint"]),
                account["amount"],
                account["mint"],
                kind=token.kind if token else "unknown",
                source=token.source if token else None,
                coingecko_id=token.coingecko_id if token else None,
            )
        )
    return assets


def _scan_hyperliquid(address: str) -> list[dict]:
    state = hyperliquid.clearinghouse_state(address)
    equity = float((state.get("marginSummary") or {}).get("accountValue") or 0)
    assets = [_venue_asset("hyperliquid", PERP_EQUITY, equity, 1.0)] if equity else []
    balances = hyperliquid.spot_balances(address)
    if not balances:
        return assets
    prices = {"USDC": 1.0}
    for market in hyperliquid.spot_markets():
        price = market["mid_price"] or market["mark_price"]
        if market["base"] and price:
            prices[market["base"]] = price
    for balance in balances:
        total = float(balance.get("total") or 0)
        if total:
            assets.append(_venue_asset("hyperliquid", balance.get("coin"), total, prices.get(balance.get("coin"))))
    return assets


def _scan_lighter(address: str) -> list[dict]:
    account = lighter.find_account(address)
    if account is None:
        return []
    equity = float(account.get("total_asset_value") or 0)
    assets = [_venue_asset("lighter", PERP_EQUITY, equity, 1.0)] if equity else []
    for balance in lighter.asset_balances(account):
        amount = balance["total"] - (balance["margin"] if balance["coin"] == "USDC" else 0)
        if amount:
            assets.append(_venue_asset("lighter", balance["coin"], amount, balance["price_usd"]))
    return assets


DEFI_SCANNERS = {"hyperliquid": _scan_hyperliquid, "lighter": _scan_lighter}


def _scan_job(address: str, source: str) -> list[dict]:
    if source in DEFI_SCANNERS:
        return DEFI_SCANNERS[source](address)
    if NETWORKS[source].kind == "solana":
        return _scan_solana(address)
    return _scan_evm(source, address)


def _resolve_target(value: str, networks: list[str] | None) -> Target:
    value = value.strip()
    if solana.looks_like_solana(value):
        kind, address = "solana", solana.resolve_solana_address(value)
    else:
        kind, address = "evm", resolve_address(value)
    if not networks:
        return Target(value, address, tuple(key for key, net in NETWORKS.items() if net.kind == kind))
    requested = [resolve_network(n) for n in networks]
    mismatched = [n.key for n in requested if n.kind != kind]
    if mismatched:
        raise ChainqError(
            f"{', '.join(mismatched)} cannot hold this address "
            f"({'base58 Solana pubkey' if kind == 'solana' else '0x EVM address'})"
        )
    return Target(value, address, tuple(n.key for n in requested))


def resolve_targets(inputs: list[str], networks: list[str] | None) -> list[Target]:
    targets: dict[str, Target] = {}
    invalid: list[str] = []
    for value in inputs:
        try:
            target = _resolve_target(value, networks)
        except ChainqError as exc:
            if len(inputs) == 1:
                raise
            invalid.append(f"{value} ({exc})")
            continue
        targets.setdefault(target.address, target)
    if invalid:
        raise ChainqError("cannot scan: " + "; ".join(invalid))
    return list(targets.values())


def scan_wallets(targets: list[Target], defi: bool, use_cache: bool) -> ScanResult:
    jobs = [(t.address, key) for t in targets for key in t.networks]
    if defi:
        jobs += [(t.address, source) for t in targets if t.address.startswith("0x") for source in DEFI_SCANNERS]
    keys = {job: cache.key_for("portfolio", *job) for job in jobs}
    cached = cache.get_many(list(keys.values())) if use_cache else {}
    assets: dict[str, list[dict]] = {t.address: [] for t in targets}
    unreachable: dict[str, list[str]] = {t.address: [] for t in targets}
    for (address, _), key in keys.items():
        assets[address].extend(cached.get(key, []))
    pending = [job for job in jobs if keys[job] not in cached]
    scanned: dict[tuple[str, str], list[dict]] = {}
    price_failures: list[str] = []
    if pending:
        wallets = len({address for address, _ in pending})
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
            price_failures = pricing.price_assets(
                [a for (_, source), found in scanned.items() if source not in DEFI_SCANNERS for a in found]
            )
        if not price_failures:
            cache.put_many({keys[job]: found for job, found in scanned.items()}, SCAN_TTL)
        for (address, _), found in scanned.items():
            assets[address].extend(found)
    return ScanResult(
        assets=assets,
        unreachable={address: sorted(sources) for address, sources in unreachable.items()},
        cache_hits=len(jobs) - len(pending),
        price_failures=price_failures,
    )
