from typing import Annotated

import typer
from eth_abi import encode
from web3 import Web3

from chainq.errors import ChainqError
from chainq.fmt import fmt_amount, fmt_pct, fmt_usd, humanize_usd
from chainq.networks import resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import uniswap
from chainq.rpc import connect, erc20
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


def _token_info(client, address: str, net, memo: dict) -> tuple[str, int]:
    if address not in memo:
        if int(address, 16) == 0:
            memo[address] = (net.native_symbol, 18)
        else:
            contract = erc20(client, address)
            memo[address] = (contract.functions.symbol().call(), contract.functions.decimals().call())
    return memo[address]


def _sqrt_price(sqrt_price_x96: int, dec0: int, dec1: int) -> float:
    return (sqrt_price_x96 / 2**96) ** 2 * 10 ** (dec0 - dec1)


def _v2_rows(client, net, address_a: str, address_b: str, memo: dict) -> list[dict]:
    factory = client.w3.eth.contract(
        address=Web3.to_checksum_address(uniswap.V2_FACTORIES[net.key]), abi=uniswap.V2_FACTORY_ABI
    )
    pair_address = factory.functions.getPair(
        Web3.to_checksum_address(address_a), Web3.to_checksum_address(address_b)
    ).call()
    if int(pair_address, 16) == 0:
        return []
    pair = client.w3.eth.contract(address=pair_address, abi=uniswap.V2_PAIR_ABI)
    token0 = pair.functions.token0().call()
    token1 = pair.functions.token1().call()
    sym0, dec0 = _token_info(client, token0, net, memo)
    sym1, dec1 = _token_info(client, token1, net, memo)
    reserve0_raw, reserve1_raw, _ = pair.functions.getReserves().call()
    reserve0 = reserve0_raw / 10**dec0
    reserve1 = reserve1_raw / 10**dec1
    if reserve0 == 0:
        return []
    return [
        {
            "version": "v2",
            "pool_address": pair_address,
            "fee_pct": 0.3,
            "pair": f"{sym0}/{sym1}",
            "price": reserve1 / reserve0,
            "reserve0": reserve0,
            "reserve1": reserve1,
            "token0": token0,
            "token1": token1,
        }
    ]


def _v3_rows(client, net, address_a: str, address_b: str, fees: list[int], memo: dict) -> list[dict]:
    factory = client.w3.eth.contract(
        address=Web3.to_checksum_address(uniswap.V3_FACTORIES[net.key]), abi=uniswap.V3_FACTORY_ABI
    )
    rows = []
    for tier in fees:
        pool_address = factory.functions.getPool(
            Web3.to_checksum_address(address_a), Web3.to_checksum_address(address_b), tier
        ).call()
        if int(pool_address, 16) == 0:
            continue
        pool_contract = client.w3.eth.contract(address=pool_address, abi=uniswap.V3_POOL_ABI)
        token0 = pool_contract.functions.token0().call()
        token1 = pool_contract.functions.token1().call()
        sym0, dec0 = _token_info(client, token0, net, memo)
        sym1, dec1 = _token_info(client, token1, net, memo)
        sqrt_price = pool_contract.functions.slot0().call()[0]
        if sqrt_price == 0:
            continue
        rows.append(
            {
                "version": "v3",
                "pool_address": pool_address,
                "fee_pct": tier / 10000,
                "pair": f"{sym0}/{sym1}",
                "price": _sqrt_price(sqrt_price, dec0, dec1),
                "reserve0": erc20(client, token0).functions.balanceOf(pool_address).call() / 10**dec0,
                "reserve1": erc20(client, token1).functions.balanceOf(pool_address).call() / 10**dec1,
                "token0": token0,
                "token1": token1,
            }
        )
    return rows


def _v4_rows(client, net, address_a: str, address_b: str, fees: list[int], memo: dict) -> list[dict]:
    state_view = client.w3.eth.contract(
        address=Web3.to_checksum_address(uniswap.V4_STATE_VIEWS[net.key]), abi=uniswap.V4_STATE_VIEW_ABI
    )
    currency0, currency1 = sorted((address_a, address_b), key=lambda a: int(a, 16))
    sym0, dec0 = _token_info(client, currency0, net, memo)
    sym1, dec1 = _token_info(client, currency1, net, memo)
    rows = []
    for tier in fees:
        tick_spacing = uniswap.V4_FEE_TICK_SPACING.get(tier)
        if tick_spacing is None:
            continue
        pool_id = Web3.keccak(
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
        sqrt_price = state_view.functions.getSlot0(pool_id).call()[0]
        if sqrt_price == 0:
            continue
        liquidity = state_view.functions.getLiquidity(pool_id).call()
        rows.append(
            {
                "version": "v4",
                "pool_address": pool_id.hex() if pool_id.hex().startswith("0x") else f"0x{pool_id.hex()}",
                "fee_pct": tier / 10000,
                "pair": f"{sym0}/{sym1}",
                "price": _sqrt_price(sqrt_price, dec0, dec1),
                "reserve0": None,
                "reserve1": None,
                "in_range_liquidity": liquidity,
                "token0": currency0,
                "token1": currency1,
            }
        )
    return rows


def _pool_by_address(client, net, address: str, memo: dict) -> list[dict]:
    checksummed = Web3.to_checksum_address(address)
    pool_v3 = client.w3.eth.contract(address=checksummed, abi=uniswap.V3_POOL_ABI)
    try:
        sqrt_price = pool_v3.functions.slot0().call()[0]
        tier = pool_v3.functions.fee().call()
        token0 = pool_v3.functions.token0().call()
        token1 = pool_v3.functions.token1().call()
        sym0, dec0 = _token_info(client, token0, net, memo)
        sym1, dec1 = _token_info(client, token1, net, memo)
        return [
            {
                "version": "v3",
                "pool_address": checksummed,
                "fee_pct": tier / 10000,
                "pair": f"{sym0}/{sym1}",
                "price": _sqrt_price(sqrt_price, dec0, dec1),
                "reserve0": erc20(client, token0).functions.balanceOf(checksummed).call() / 10**dec0,
                "reserve1": erc20(client, token1).functions.balanceOf(checksummed).call() / 10**dec1,
                "token0": token0,
                "token1": token1,
            }
        ]
    except Exception:
        pass
    pair = client.w3.eth.contract(address=checksummed, abi=uniswap.V2_PAIR_ABI)
    try:
        token0 = pair.functions.token0().call()
        token1 = pair.functions.token1().call()
        reserve0_raw, reserve1_raw, _ = pair.functions.getReserves().call()
        sym0, dec0 = _token_info(client, token0, net, memo)
        sym1, dec1 = _token_info(client, token1, net, memo)
        reserve0 = reserve0_raw / 10**dec0
        reserve1 = reserve1_raw / 10**dec1
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
    except Exception as exc:
        raise ChainqError(
            f"{address} is not a readable Uniswap v2/v3 pool on {net.name} "
            "(v4 pools have no address — pass the two tokens instead)"
        ) from exc


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
    memo: dict = {}
    rows: list[dict] = []
    if version in ("v2", "all") and supported["v2"]:
        rows += _v2_rows(client, net, _resolve_pool_token(token_a, net, False), _resolve_pool_token(token_b, net, False), memo)
    if version in ("v3", "all") and supported["v3"]:
        rows += _v3_rows(
            client, net, _resolve_pool_token(token_a, net, False), _resolve_pool_token(token_b, net, False), fees, memo
        )
    if version in ("v4", "all") and supported["v4"]:
        rows += _v4_rows(
            client, net, _resolve_pool_token(token_a, net, True), _resolve_pool_token(token_b, net, True), fees, memo
        )
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
