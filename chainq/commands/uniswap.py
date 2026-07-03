from typing import Annotated

import typer

from chainq.errors import ChainqError
from chainq.fmt import fmt_amount, fmt_pct, fmt_usd, humanize_usd
from chainq.networks import resolve_network
from chainq.output import FormatOpt, JsonOpt, Out, QuietOpt, VerboseOpt
from chainq.providers import uniswap
from chainq.rpc import connect, erc20
from chainq.tokens import TOKENS

app = typer.Typer(no_args_is_help=True, help="Uniswap pools and protocol stats.")

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


def _resolve_pool_token(value: str, net) -> str:
    if value.startswith("0x") and len(value) == 42:
        return value
    address = TOKENS.get(net.key, {}).get(value.lower())
    if address is None:
        raise ChainqError(f"unknown token '{value}' on {net.name}; pass the contract address")
    return address


@app.command()
def pool(
    token_a: Annotated[str, typer.Argument(help="token symbol or address")],
    token_b: Annotated[str, typer.Argument(help="token symbol or address")],
    network: Annotated[str, typer.Option("--network", "-n", help="network key, alias, or chain id")] = "ethereum",
    fee: Annotated[int | None, typer.Option("--fee", help="fee tier in hundredths of a bip: 100 | 500 | 3000 | 10000")] = None,
    json_out: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    format: FormatOpt = "text",
):
    """Read Uniswap v3 pools directly onchain: price, reserves, per fee tier."""
    out = Out(json_out, quiet, verbose, format)
    net = resolve_network(network)
    factory_address = uniswap.V3_FACTORIES.get(net.key)
    if factory_address is None:
        raise ChainqError(f"no Uniswap v3 factory known on {net.name} (known: {', '.join(uniswap.V3_FACTORIES)})")
    client = connect(net)
    address_a = _resolve_pool_token(token_a, net)
    address_b = _resolve_pool_token(token_b, net)
    factory = client.w3.eth.contract(
        address=client.w3.to_checksum_address(factory_address), abi=uniswap.V3_FACTORY_ABI
    )
    fees = [fee] if fee else list(uniswap.V3_FEE_TIERS)
    rows = []
    token_meta: dict[str, tuple[str, int]] = {}
    for tier in fees:
        pool_address = factory.functions.getPool(
            client.w3.to_checksum_address(address_a), client.w3.to_checksum_address(address_b), tier
        ).call()
        if int(pool_address, 16) == 0:
            continue
        pool_contract = client.w3.eth.contract(address=pool_address, abi=uniswap.V3_POOL_ABI)
        token0 = pool_contract.functions.token0().call()
        token1 = pool_contract.functions.token1().call()
        for token in (token0, token1):
            if token not in token_meta:
                token_contract = erc20(client, token)
                token_meta[token] = (token_contract.functions.symbol().call(), token_contract.functions.decimals().call())
        sym0, dec0 = token_meta[token0]
        sym1, dec1 = token_meta[token1]
        sqrt_price = pool_contract.functions.slot0().call()[0]
        price = (sqrt_price / 2**96) ** 2 * 10 ** (dec0 - dec1)
        reserve0 = erc20(client, token0).functions.balanceOf(pool_address).call() / 10**dec0
        reserve1 = erc20(client, token1).functions.balanceOf(pool_address).call() / 10**dec1
        rows.append(
            {
                "pool_address": pool_address,
                "fee_pct": tier / 10000,
                "pair": f"{sym0}/{sym1}",
                "price": price,
                "price_description": f"1 {sym0} = {fmt_amount(price)} {sym1}",
                "reserve0": reserve0,
                "reserve1": reserve1,
                "token0": token0,
                "token1": token1,
            }
        )
    if not rows:
        raise ChainqError(f"no Uniswap v3 pool for {token_a}/{token_b} on {net.name}")
    lines = [
        f"{r['pair']} {r['fee_pct']}% [{net.key} v3]: 1 {r['pair'].split('/')[0]} = {fmt_amount(r['price'])} "
        f"{r['pair'].split('/')[1]}  reserves {fmt_amount(r['reserve0'])} / {fmt_amount(r['reserve1'])}"
        for r in rows
    ]
    out.emit(
        rows,
        lines,
        quiet_value="\n".join(r["pool_address"] for r in rows),
        verbose_lines=[f"{r['fee_pct']}%: pool {r['pool_address']}  rpc {client.url}" for r in rows],
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
