from typing import Annotated

import typer
from eth_abi import encode
from web3 import Web3

from chainq.errors import ChainqError
from chainq.fmt import fmt_amount, fmt_pct, fmt_usd, humanize_usd, short_addr
from chainq.networks import resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import uniswap
from chainq.rpc import (
    connect,
    decode_address,
    decode_string,
    decode_uint,
    encode_call,
    encode_erc20,
    erc20,
    multicall,
)
from chainq.tokens import TOKENS

app = typer.Typer(no_args_is_help=True, help="Uniswap pools (onchain v2/v3/v4 + indexed discovery) and protocol stats.")

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

SORT_KEYS = {
    "liquidity": lambda p: p["liquidity_usd"] or 0,
    "volume": lambda p: p["volume_24h_usd"] or 0,
}


def _pool_line(p: dict) -> str:
    version = f" {p['version']}" if p["version"] else ""
    price = f"  price {fmt_usd(p['price_usd'])}" if p["price_usd"] is not None else ""
    return (
        f"{p['pair']} [{p['chain']}{version}]:{price}  24h {fmt_pct(p['change_24h_pct'])}  "
        f"vol {humanize_usd(p['volume_24h_usd'] or 0)}  liquidity {humanize_usd(p['liquidity_usd'] or 0)}"
    )


@app.command()
def pools(
    query: Annotated[str, typer.Argument(help="pair like 'weth usdc' or 'weth/usdc', a token symbol, or a token address")],
    network: Annotated[str, typer.Option("--network", "-n", help="network key, alias, or chain id")] = "ethereum",
    sort: Annotated[str, typer.Option("--sort", "-s", help="liquidity | volume")] = "liquidity",
    limit: Annotated[int, typer.Option("--limit", "-l")] = 10,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Find Uniswap pools: price, 24h volume, liquidity (via DexScreener)."""
    out = Out(json_out, quiet, verbose, format)
    if sort not in SORT_KEYS:
        raise ChainqError(f"unknown sort '{sort}' (use: {', '.join(SORT_KEYS)})")
    net = resolve_network(network)
    chain_slug = uniswap.CHAIN_SLUGS.get(net.key)
    if chain_slug is None:
        raise ChainqError(f"no DexScreener mapping for {net.name}")
    parts = query.replace("/", " ").split()
    base, quote = parts[0], parts[1] if len(parts) > 1 else None
    if base.startswith("0x") and len(base) == 42:
        address = base
    else:
        address = TOKENS.get(net.key, {}).get(base.lower())
    pairs = uniswap.token_pairs(address) if address else uniswap.search_pairs(query)
    rows = sorted(uniswap.uniswap_rows(pairs, chain_slug, quote), key=SORT_KEYS[sort], reverse=True)[:limit]
    if not rows:
        raise ChainqError(f"no Uniswap pools found for '{query}' on {net.name}")
    out.emit(
        rows,
        [_pool_line(p) for p in rows],
        quiet_value="\n".join(p["pair_address"] or p["pair"] for p in rows),
        verbose_lines=[f"{p['pair']}: {p['pair_address']}  {p['url']}" for p in rows],
    )


def _resolve_pool_token(value: str, net, native_ok: bool) -> str:
    v = value.strip().lower()
    if v in ("eth", "native"):
        if native_ok:
            return ZERO_ADDRESS
        weth = TOKENS.get(net.key, {}).get("weth")
        if weth is None:
            raise ChainqError(f"'{value}' needs a wrapped-native address on {net.name}; pass the contract address")
        return weth
    if value.startswith("0x") and len(value) == 42:
        return value
    address = TOKENS.get(net.key, {}).get(v)
    if address is None:
        raise ChainqError(f"unknown token '{value}' on {net.name}; pass the contract address")
    return address


def _token_infos(client, net, addresses: list[str], memo: dict) -> None:
    pending = []
    for address in addresses:
        if int(address, 16) == 0:
            memo[address] = (net.native_symbol, 18)
        elif address not in memo and address not in pending:
            pending.append(address)
    if not pending:
        return
    calls = []
    for address in pending:
        calls.append((address, encode_erc20("symbol")))
        calls.append((address, encode_erc20("decimals")))
    try:
        results = multicall(client, calls)
    except Exception:
        for address in pending:
            contract = erc20(client, address)
            memo[address] = (contract.functions.symbol().call(), contract.functions.decimals().call())
        return
    for i, address in enumerate(pending):
        symbol, decimals = results[2 * i], results[2 * i + 1]
        memo[address] = (
            decode_string(symbol) if symbol else short_addr(address),
            decode_uint(decimals) if decimals else 18,
        )


def _sqrt_price(sqrt_price_x96: int, dec0: int, dec1: int) -> float:
    return (sqrt_price_x96 / 2**96) ** 2 * 10 ** (dec0 - dec1)


def _v4_pool_id(currency0: str, currency1: str, tier: int, tick_spacing: int) -> bytes:
    return Web3.keccak(
        encode(
            ["address", "address", "uint24", "int24", "address"],
            [
                Web3.to_checksum_address(currency0),
                Web3.to_checksum_address(currency1),
                tier,
                tick_spacing,
                ZERO_ADDRESS,
            ],
        )
    )


def _onchain_rows(client, net, version: str, token_a: str, token_b: str, fees: list[int], supported: dict) -> list[dict]:
    memo: dict = {}
    erc_a = erc_b = None
    if any(version in (v, "all") and supported[v] for v in ("v2", "v3")):
        erc_a = Web3.to_checksum_address(_resolve_pool_token(token_a, net, False))
        erc_b = Web3.to_checksum_address(_resolve_pool_token(token_b, net, False))
    use_v4 = version in ("v4", "all") and supported["v4"]
    currency0 = currency1 = None
    if use_v4:
        v4_a = _resolve_pool_token(token_a, net, True)
        v4_b = _resolve_pool_token(token_b, net, True)
        currency0, currency1 = sorted((v4_a, v4_b), key=lambda a: int(a, 16))
    discovery: list[tuple[str, int | None]] = []
    calls: list[tuple[str, bytes]] = []
    if version in ("v2", "all") and supported["v2"]:
        discovery.append(("v2", None))
        calls.append((uniswap.V2_FACTORIES[net.key], encode_call(uniswap.V2_FACTORY_ABI, "getPair", [erc_a, erc_b])))
    if version in ("v3", "all") and supported["v3"]:
        for tier in fees:
            discovery.append(("v3", tier))
            calls.append(
                (uniswap.V3_FACTORIES[net.key], encode_call(uniswap.V3_FACTORY_ABI, "getPool", [erc_a, erc_b, tier]))
            )
    found = []
    if calls:
        for (ver, tier), result in zip(discovery, multicall(client, calls), strict=True):
            if result is not None and int.from_bytes(result[12:32], "big"):
                found.append((ver, tier, decode_address(result)))
    meta_addresses = []
    if found:
        meta_addresses += [erc_a, erc_b]
    if use_v4:
        meta_addresses += [currency0, currency1]
    _token_infos(client, net, meta_addresses, memo)
    state_plan: list[tuple] = []
    state_calls: list[tuple[str, bytes]] = []
    token0 = token1 = None
    if found:
        token0, token1 = sorted((erc_a, erc_b), key=lambda a: int(a, 16))
    for ver, tier, pool_address in found:
        if ver == "v2":
            state_plan.append(("v2", tier, pool_address, 1))
            state_calls.append((pool_address, encode_call(uniswap.V2_PAIR_ABI, "getReserves")))
        else:
            state_plan.append(("v3", tier, pool_address, 3))
            state_calls.append((pool_address, encode_call(uniswap.V3_POOL_ABI, "slot0")))
            state_calls.append((token0, encode_erc20("balanceOf", [pool_address])))
            state_calls.append((token1, encode_erc20("balanceOf", [pool_address])))
    if use_v4:
        state_view = uniswap.V4_STATE_VIEWS[net.key]
        for tier in fees:
            tick_spacing = uniswap.V4_FEE_TICK_SPACING.get(tier)
            if tick_spacing is None:
                continue
            pool_id = _v4_pool_id(currency0, currency1, tier, tick_spacing)
            state_plan.append(("v4", tier, f"0x{pool_id.hex().removeprefix('0x')}", 2))
            state_calls.append((state_view, encode_call(uniswap.V4_STATE_VIEW_ABI, "getSlot0", [pool_id])))
            state_calls.append((state_view, encode_call(uniswap.V4_STATE_VIEW_ABI, "getLiquidity", [pool_id])))
    results = multicall(client, state_calls)
    rows = []
    cursor = 0
    for ver, tier, pool_address, width in state_plan:
        chunk = results[cursor : cursor + width]
        cursor += width
        if ver == "v2":
            if chunk[0] is None:
                continue
            sym0, dec0 = memo[token0]
            sym1, dec1 = memo[token1]
            reserve0 = decode_uint(chunk[0][:32]) / 10**dec0
            reserve1 = decode_uint(chunk[0][32:64]) / 10**dec1
            if not reserve0:
                continue
            rows.append(
                {
                    "version": "v2",
                    "pool_address": pool_address,
                    "fee_pct": 0.3,
                    "pair": f"{sym0}/{sym1}",
                    "price": reserve1 / reserve0,
                    "reserve0": reserve0,
                    "reserve1": reserve1,
                    "token0": token0,
                    "token1": token1,
                }
            )
        elif ver == "v3":
            slot0, balance0, balance1 = chunk
            if slot0 is None or not decode_uint(slot0):
                continue
            sym0, dec0 = memo[token0]
            sym1, dec1 = memo[token1]
            rows.append(
                {
                    "version": "v3",
                    "pool_address": pool_address,
                    "fee_pct": tier / 10000,
                    "pair": f"{sym0}/{sym1}",
                    "price": _sqrt_price(decode_uint(slot0), dec0, dec1),
                    "reserve0": decode_uint(balance0) / 10**dec0 if balance0 else None,
                    "reserve1": decode_uint(balance1) / 10**dec1 if balance1 else None,
                    "token0": token0,
                    "token1": token1,
                }
            )
        else:
            slot0, liquidity = chunk
            if slot0 is None or not decode_uint(slot0):
                continue
            sym0, dec0 = memo[currency0]
            sym1, dec1 = memo[currency1]
            rows.append(
                {
                    "version": "v4",
                    "pool_address": pool_address,
                    "fee_pct": tier / 10000,
                    "pair": f"{sym0}/{sym1}",
                    "price": _sqrt_price(decode_uint(slot0), dec0, dec1),
                    "reserve0": None,
                    "reserve1": None,
                    "in_range_liquidity": decode_uint(liquidity) if liquidity else None,
                    "token0": currency0,
                    "token1": currency1,
                }
            )
    return rows


def _pool_by_address(client, net, address: str, memo: dict) -> list[dict]:
    checksummed = Web3.to_checksum_address(address)
    slot0, fee_raw, reserves, token0_raw, token1_raw = multicall(
        client,
        [
            (checksummed, encode_call(uniswap.V3_POOL_ABI, "slot0")),
            (checksummed, encode_call(uniswap.V3_POOL_ABI, "fee")),
            (checksummed, encode_call(uniswap.V2_PAIR_ABI, "getReserves")),
            (checksummed, encode_call(uniswap.V2_PAIR_ABI, "token0")),
            (checksummed, encode_call(uniswap.V2_PAIR_ABI, "token1")),
        ],
    )
    if token0_raw is None or token1_raw is None or (slot0 is None and reserves is None):
        raise ChainqError(
            f"{address} is not a readable Uniswap v2/v3 pool on {net.name} "
            "(v4 pools have no address — pass the two tokens instead)"
        )
    token0, token1 = decode_address(token0_raw), decode_address(token1_raw)
    _token_infos(client, net, [token0, token1], memo)
    sym0, dec0 = memo[token0]
    sym1, dec1 = memo[token1]
    if slot0 is not None and fee_raw is not None:
        balance0, balance1 = multicall(
            client,
            [(token0, encode_erc20("balanceOf", [checksummed])), (token1, encode_erc20("balanceOf", [checksummed]))],
        )
        return [
            {
                "version": "v3",
                "pool_address": checksummed,
                "fee_pct": decode_uint(fee_raw) / 10000,
                "pair": f"{sym0}/{sym1}",
                "price": _sqrt_price(decode_uint(slot0), dec0, dec1),
                "reserve0": decode_uint(balance0) / 10**dec0 if balance0 else None,
                "reserve1": decode_uint(balance1) / 10**dec1 if balance1 else None,
                "token0": token0,
                "token1": token1,
            }
        ]
    reserve0 = decode_uint(reserves[:32]) / 10**dec0
    reserve1 = decode_uint(reserves[32:64]) / 10**dec1
    return [
        {
            "version": "v2",
            "pool_address": checksummed,
            "fee_pct": 0.3,
            "pair": f"{sym0}/{sym1}",
            "price": reserve1 / reserve0 if reserve0 else None,
            "reserve0": reserve0,
            "reserve1": reserve1,
            "token0": token0,
            "token1": token1,
        }
    ]


@app.command()
def pool(
    token_a: Annotated[str, typer.Argument(help="token symbol/address, 'eth' for native (v4), or a pool address alone")],
    token_b: Annotated[str | None, typer.Argument(help="second token; omit when TOKEN_A is a pool address")] = None,
    network: Annotated[str, typer.Option("--network", "-n", help="network key, alias, or chain id")] = "ethereum",
    version: Annotated[str, typer.Option("--version", "-V", help="v2 | v3 | v4 | all")] = "all",
    fee: Annotated[int | None, typer.Option("--fee", help="fee tier in hundredths of a bip: 100 | 500 | 3000 | 10000")] = None,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Read Uniswap v2/v3/v4 pools directly onchain: price and reserves per version and fee tier."""
    out = Out(json_out, quiet, verbose, format)
    if version not in ("v2", "v3", "v4", "all"):
        raise ChainqError(f"unknown version '{version}' (use: v2 | v3 | v4 | all)")
    net = resolve_network(network)
    if token_b is None:
        if not (token_a.startswith("0x") and len(token_a) == 42):
            raise ChainqError("pass two tokens, or a single 0x pool address")
        client = connect(net)
        rows = _pool_by_address(client, net, token_a, {})
        lines = []
        for r in rows:
            sym0, sym1 = r["pair"].split("/")
            lines.append(
                f"{r['pair']} {r['fee_pct']}% [{net.key} {r['version']}]: 1 {sym0} = {fmt_amount(r['price'])} {sym1}"
                f"  reserves {fmt_amount(r['reserve0'])} / {fmt_amount(r['reserve1'])}"
            )
        out.emit(
            rows,
            lines,
            quiet_value="\n".join(str(r["price"]) for r in rows),
            verbose_lines=[f"{r['version']}: {r['pool_address']}  rpc {client.url}" for r in rows],
        )
        return
    supported = {
        "v2": net.key in uniswap.V2_FACTORIES,
        "v3": net.key in uniswap.V3_FACTORIES,
        "v4": net.key in uniswap.V4_STATE_VIEWS,
    }
    if version != "all" and not supported[version]:
        raise ChainqError(f"no known Uniswap {version} deployment on {net.name}")
    if not any(supported.values()):
        raise ChainqError(f"no known Uniswap deployment on {net.name}")
    client = connect(net)
    fees = [fee] if fee else list(uniswap.V3_FEE_TIERS)
    rows = _onchain_rows(client, net, version, token_a, token_b, fees, supported)
    if not rows:
        raise ChainqError(f"no Uniswap pool for {token_a}/{token_b} on {net.name} (version: {version})")
    lines = []
    for r in rows:
        sym0, sym1 = r["pair"].split("/")
        line = f"{r['pair']} {r['fee_pct']}% [{net.key} {r['version']}]: 1 {sym0} = {fmt_amount(r['price'])} {sym1}"
        if r["reserve0"] is not None:
            line += f"  reserves {fmt_amount(r['reserve0'])} / {fmt_amount(r['reserve1'])}"
        lines.append(line)
    out.emit(
        rows,
        lines,
        quiet_value="\n".join(r["pool_address"] for r in rows),
        verbose_lines=[f"{r['version']} {r['fee_pct']}%: {r['pool_address']}  rpc {client.url}" for r in rows],
    )


@app.command()
def stats(
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Uniswap protocol totals: TVL and volumes (via DefiLlama)."""
    out = Out(json_out, quiet, verbose, format)
    data = uniswap.stats()
    text = (
        f"Uniswap: TVL {humanize_usd(data['tvl_usd'] or 0)}  24h vol {humanize_usd(data['volume_24h_usd'] or 0)} "
        f"({fmt_pct(data['volume_change_1d_pct'])})  7d vol {humanize_usd(data['volume_7d_usd'] or 0)}  "
        f"30d vol {humanize_usd(data['volume_30d_usd'] or 0)}"
    )
    out.emit(data, text, quiet_value=data["tvl_usd"])
