---
name: chainq
description: Query live crypto and onchain data via the chainq CLI - asset prices, trending tokens and market caps (CoinGecko), wallet balances (native + ERC-20, ENS supported), gas prices, transaction lookups, raw EVM JSON-RPC on 25 networks, lending markets on Aave v3 and Morpho (supply/borrow APY, vaults), Uniswap pools (onchain + indexed), Pendle yield markets (implied APY), Hyperliquid perps/spot/builder-dexs/prediction-markets, Lighter perps, and DefiLlama metrics (TVL/fees/volume) for any protocol or chain. Use whenever the user asks about crypto prices, token/wallet balances, gas costs, a transaction hash, onchain state, lending/borrowing rates, vault yields, DEX pools, TVL, funding rates, prediction markets, Hyperliquid, or Lighter.
---

# chainq

Agent-friendly CLI for onchain and crypto market data. No API keys or setup needed for any command below; public RPC endpoints with automatic fallback are built in.

## Output rules

- Default output is one human-readable line per result — safe to show the user as-is.
- Add `--json` to any command for structured output you need to parse or compute over.
- Add `-q` for the bare primary value (piping/arithmetic), `-v` for provenance (RPC endpoint, source, explorer links).
- `--format table` renders lists as aligned columns (good to show humans); `--format toon` is a compact tabular encoding that uses ~2-3x fewer tokens than JSON — prefer it when pulling large lists (e.g. `hl markets -l 50`) into your own context.
- Errors: stderr + exit code 1. A CoinGecko rate-limit error means wait ~1 minute (or `chainq config set coingecko-api-key <key>`); RPC commands are not affected by it.
- Persistent settings (API keys, custom RPCs, timeouts): `chainq config set/get/list/unset` — no manual .env editing needed.

## Market data (CoinGecko)

```bash
chainq price eth btc hype          # spot price, 24h change, mcap; accepts symbols or coingecko ids
chainq price 0xTokenAddress        # by contract address (any chain; -n hints the network)
chainq trending -l 10              # trending tokens right now
chainq asset ethena                # full profile: price, mcap/fdv, supply, ATH, links
chainq asset 0xTokenAddress -n base
chainq search "sky protocol"       # resolve fuzzy names to ids for price/asset
```

Contract addresses work everywhere: `price`/`asset` locate the token via DexScreener, then pull CoinGecko data for it; tokens unknown to CoinGecko fall back to DexScreener pair data (marked `[dexscreener/<chain>]`, price/mcap only).

Prefer `price` for "how much is X"; use `asset` when the user wants depth (supply, FDV, ATH). If a symbol is ambiguous or unknown, run `search` first and use the returned id.

## Onchain (EVM)

25 networks: ethereum, arbitrum, base, optimism, polygon, bsc, avalanche, gnosis, unichain, linea, scroll, zksync, mantle, blast, sonic, berachain, worldchain, ink, soneium, celo, sei, hyperevm, monad, plasma, katana. `--network`/`-n` accepts keys, aliases (eth, arb, op, matic, bnb, avax, hype...), or chain ids. Default is ethereum. `chainq networks` lists all.

```bash
chainq balance vitalik.eth                                    # native balance, ENS ok
chainq balance 0x... --coin usdt --network arbitrum           # ERC-20 by symbol
chainq balance 0x... --coin 0xTokenAddress -n base            # ERC-20 by contract address
chainq gas -n base                                            # gas price, base fee, transfer cost in USD
chainq tx 0xHASH -n ethereum                                  # status, parties, value, fee, block
chainq rpc eth_blockNumber -n optimism                        # raw JSON-RPC escape hatch, prints JSON
chainq rpc eth_getBlockByNumber latest false                  # params: JSON literals parsed, rest strings
```

Known token symbols per network are listed in the `balance` error message if a symbol misses; any ERC-20 works by address. Balances include a best-effort USD value.

## Aave v3 (lending)

```bash
chainq protocols aave markets -n ethereum        # reserves ranked by size: supply/borrow APY, utilization
chainq protocols aave markets -c usdc -n base    # one asset (all markets on the chain)
chainq protocols aave markets -s supply-apy      # sort: supplied | supply-apy | borrow-apy | utilization
```

"Best yield on USDC" type questions: run `protocols aave markets -c usdc` on the relevant networks and compare `supply_apy_pct` from `--json`. Data comes from Aave's official API and covers every market on the chain (e.g. Core, Prime, EtherFi on ethereum).

## Uniswap

```bash
chainq protocols uniswap pool weth usdc -n ethereum      # ONCHAIN pool state, all of v2+v3+v4 per fee tier
chainq protocols uniswap pool eth usdc -V v4             # 'eth' = native currency (v4 pools use it); -V v2|v3|v4|all
chainq protocols uniswap pool weth usdc --fee 500        # one fee tier (100 | 500 | 3000 | 10000)
chainq protocols uniswap pool 0xPoolAddress              # single pool/pair address, v2/v3 auto-detected
chainq protocols uniswap pools "weth usdc" -n ethereum   # discovery via indexer: 24h vol, liquidity
chainq protocols uniswap pools usdc -n base -s volume    # all pools for one token; sort: liquidity | volume
chainq protocols uniswap stats                           # protocol TVL + 24h/7d/30d volume
```

`pool` (singular) reads factory/pool/StateView contracts directly — authoritative prices and reserves (v4 reports price + in-range liquidity, no reserves; its biggest pools use native 'eth', not weth). `pools` (plural) uses DexScreener for discovery/ranking (symbols resolve through the built-in token registry; prefer addresses for long-tail tokens). Thin low-liquidity tiers can show stale prices — compare across tiers/versions.

## Pendle (yields)

```bash
chainq protocols pendle markets -n ethereum              # active markets: implied APY, LP APY, liquidity, expiry
chainq protocols pendle markets -c usde -s implied-apy   # filter by name; sort: liquidity | implied-apy | expiry
```

"Fixed yield on X" questions: implied APY is the fixed rate you lock by buying PT. Filter with `-c` and compare `implied_apy_pct` from `--json`.

## Morpho (lending)

```bash
chainq protocols morpho markets -n base -c usdc          # markets: supply/borrow APY, lltv, utilization
chainq protocols morpho markets -s borrow-apy            # sort: supplied | supply-apy | borrow-apy | utilization
chainq protocols morpho vaults -c usdc                   # curated vaults: APY (gross + net), TVL
```

## DefiLlama (any protocol/chain)

```bash
chainq protocols llama protocol lido                     # TVL, chains, fees, dex volume for ANY protocol
chainq protocols llama top -c Lending -l 10              # top protocols by TVL, optional category
chainq protocols llama chains                            # chains ranked by DeFi TVL
```

Use `llama protocol` when the user asks about a protocol chainq has no dedicated command for — DefiLlama tracks thousands.

## Hyperliquid (public data)

```bash
chainq protocols hl price BTC ETH            # perps: mark/oracle price, 24h change, volume, OI, funding
chainq protocols hl markets -l 10 -s oi      # top perp markets; sort: volume | oi | funding | change
chainq protocols hl funding                  # most extreme funding rates (hourly % and APR)
chainq protocols hl funding BTC ETH          # funding for specific coins
chainq protocols hl positions 0xADDRESS      # perp account value, margin, positions with PnL/liq price
chainq protocols hl spot price HYPE PURR     # spot pairs: price, 24h change, volume, mcap
chainq protocols hl spot markets -l 10       # top spot markets by volume
chainq protocols hl spot balances 0xADDRESS  # spot token balances with USD values
chainq protocols hl dexs                     # HIP-3 builder-deployed perp dexs (xyz, flx, vntl...)
chainq protocols hl markets --dex xyz        # builder dex markets (tokenized stocks, commodities)
chainq protocols hl price TSLA --dex xyz     # coin names are dex:COIN; bare COIN works with --dex
chainq protocols hl outcomes [QUERY]         # HIP-4 prediction markets, Yes price = implied probability
```

## Lighter (public data, perps)

```bash
chainq protocols lighter markets -l 10 -s oi   # perp markets: last price, 24h change, volume, OI, funding
chainq protocols lighter price BTC ETH
chainq protocols lighter funding               # hourly funding + APR
chainq protocols lighter positions 0xADDRESS   # account value, collateral, open positions
```

Funding is shown as hourly rate and annualized APR; negative funding means shorts pay longs.

## Recipes

- "What's in this wallet?" — run `balance` for native plus likely stables (`usdt`, `usdc`) on the relevant networks, `--json` and sum `value_usd`.
- "Is it a good time to transact?" — `gas -n <network>`; the transfer-cost USD figure is the answer for simple sends.
- "Did my tx go through?" — `tx 0xHASH -n <network>`; check `status` and quote the explorer link from `-v`.
- Anything chainq lacks a command for on EVM — `chainq rpc <method> [params...]`.
