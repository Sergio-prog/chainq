---
name: chainq
description: Query live crypto and onchain data via the chainq CLI - asset prices and market caps (CoinGecko), wallet balances (native + ERC-20, ENS supported), gas prices, transaction lookups, raw EVM JSON-RPC on 9 networks, and Hyperliquid perp markets, funding rates, and account positions. Use whenever the user asks about crypto prices, token/wallet balances, gas costs, a transaction hash, onchain state, or Hyperliquid.
---

# chainq

Agent-friendly CLI for onchain and crypto market data. No API keys or setup needed for any command below; public RPC endpoints with automatic fallback are built in.

## Output rules

- Default output is one human-readable line per result — safe to show the user as-is.
- Add `--json` to any command for structured output you need to parse or compute over.
- Add `-q` for the bare primary value (piping/arithmetic), `-v` for provenance (RPC endpoint, source, explorer links).
- Errors: stderr + exit code 1. A CoinGecko rate-limit error means wait ~1 minute (or set `COINGECKO_API_KEY`); RPC commands are not affected by it.

## Market data (CoinGecko)

```bash
chainq price eth btc hype          # spot price, 24h change, mcap; accepts symbols or coingecko ids
chainq asset ethena                # full profile: price, mcap/fdv, supply, ATH, links
chainq search "sky protocol"       # resolve fuzzy names to ids for price/asset
```

Prefer `price` for "how much is X"; use `asset` when the user wants depth (supply, FDV, ATH). If a symbol is ambiguous or unknown, run `search` first and use the returned id.

## Onchain (EVM)

Networks: ethereum, arbitrum, base, optimism, polygon, bsc, avalanche, gnosis, unichain. `--network`/`-n` accepts keys, aliases (eth, arb, op, matic, bnb, avax...), or chain ids. Default is ethereum. `chainq networks` lists all.

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

## Hyperliquid (public data, perps)

```bash
chainq hl price BTC ETH            # mark/oracle price, 24h change, volume, OI, funding
chainq hl markets -l 10 -s oi      # top markets; sort: volume | oi | funding | change
chainq hl funding                  # most extreme funding rates (hourly % and APR)
chainq hl funding BTC ETH          # funding for specific coins
chainq hl positions 0xADDRESS      # account value, margin, open positions with PnL/liq price
```

Funding is shown as hourly rate and annualized APR; negative funding means shorts pay longs.

## Recipes

- "What's in this wallet?" — run `balance` for native plus likely stables (`usdt`, `usdc`) on the relevant networks, `--json` and sum `value_usd`.
- "Is it a good time to transact?" — `gas -n <network>`; the transfer-cost USD figure is the answer for simple sends.
- "Did my tx go through?" — `tx 0xHASH -n <network>`; check `status` and quote the explorer link from `-v`.
- Anything chainq lacks a command for on EVM — `chainq rpc <method> [params...]`.
