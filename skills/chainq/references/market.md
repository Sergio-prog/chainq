# Market data

## Prices and assets (CoinGecko)

```bash
chainq price eth btc hype              # spot price, 24h change, mcap; symbols or CoinGecko ids
chainq price 0xTokenAddress -n base    # contract address; -n hints the network
chainq price <SPL mint>                # Solana mints work like contract addresses
chainq price btc eth --at 2025-03-01   # historical price on a date (last 365 days)
chainq asset ethena                    # profile: price, mcap/FDV, supply, ATH, links
chainq asset btc --links tradingview,binance,coingecko
chainq search "sky protocol"           # fuzzy name to CoinGecko id
chainq trending -l 10
chainq candles btc --days 30           # OHLC; granularity scales with --days (30d gives 4h candles)
chainq candles eth -d 7 -l 24 --json   # last 24 candles
```

- Use `price` for "how much is X" and `asset` for depth (supply, FDV, ATH).
- For an ambiguous or unknown symbol, run `search` first and pass the returned id.
- `price` and `asset` find contract addresses and mints through DexScreener, then pull CoinGecko data. A token CoinGecko does not list falls back to DexScreener pair data, marked `[dexscreener/<chain>]`, with price and mcap only.
- `--at` and `candles` need a CoinGecko-listed asset, and the public API covers only the last 365 days.
- `asset` prints a TradingView link by default. Set other defaults with `chainq config set asset-links binance,coingecko`.

## Stablecoins

```bash
chainq stables                          # ranked by mcap: peg price, 7d supply change, mechanism
chainq stables usde                     # one stablecoin, or a name filter
chainq stables -m crypto-backed         # fiat-backed | crypto-backed | algorithmic
chainq stables --min-mcap 1000000000
```

For depeg questions, read `price_usd` from `stables <symbol> --json` and compare it with 1.0. For "where to park stables", use `yields --asset <symbol>` ([defi.md](defi.md)).

## Buybacks

```bash
chainq buybacks hype -d 30          # pick one or more programs; -d is the daily lookback (hype, sky, uni)
chainq buybacks hype sky uni        # several programs, each at its own cadence
chainq buybacks zro -f toon         # LayerZero, monthly rows
```

Programs are `hype`, `sky`, `uni`, `zro`, and `lit`. There is no default, so name the ones you need. Every row has `source`, `source_url`, `cadence`, and `provenance`; read `provenance` before quoting a number.

| Program | Data | Cadence |
| --- | --- | --- |
| hype | Hyperliquid Assistance Fund spot fills, live | daily |
| sky | Smart Burn Engine `Exec` events on Ethereum, live | about every 4h, bucketed per UTC day |
| uni | Firepit `Released` burn events on Ethereum, live | daily |
| zro | LayerZero tracker page, live, with a labeled snapshot if the page is down | monthly |
| lit | Returns a data limitation: Lighter treasury TWAP fills require auth | none |

The onchain programs (sky, uni) read Ethereum logs and take a few seconds.

## ETF flows

```bash
chainq etf btc -d 14       # daily US spot BTC ETF net flows, per issuer plus total
chainq etf eth --json
chainq etf btc -q          # latest day's net flow only
```

Rows carry `net_flow_usd` and one column per issuer. Data comes from The Block.
