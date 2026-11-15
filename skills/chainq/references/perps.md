# Perps and prediction markets

Both venues use public APIs; no key is needed. Funding is shown as an hourly rate and as APR. Negative funding means shorts pay longs.

## Hyperliquid

```bash
chainq protocols hl price BTC ETH                 # mark/oracle price, 24h change, volume, OI, funding
chainq protocols hl markets -l 10 -s oi           # sort: volume | oi | funding | change
chainq protocols hl funding                       # most extreme funding rates
chainq protocols hl funding BTC --history -D 30   # cumulative, mean, APR, and range over N days
chainq protocols hl positions 0xADDRESS           # account value, margin, positions with PnL and liquidation price
chainq protocols hl spot price HYPE PURR
chainq protocols hl spot markets -l 10
chainq protocols hl spot balances 0xADDRESS --min-usd 10
chainq protocols hl dexs                          # HIP-3 builder dexs (xyz, flx, vntl, ...)
chainq protocols hl markets --dex xyz             # builder dex markets: tokenized stocks, commodities
chainq protocols hl price TSLA --dex xyz          # names are dex:COIN; a bare COIN works with --dex
chainq protocols hl outcomes [QUERY]              # HIP-4 prediction markets; the Yes price is the implied probability
```

## Lighter

```bash
chainq protocols lighter markets -l 10 -s oi      # last price, 24h change, volume, OI, funding
chainq protocols lighter price BTC ETH
chainq protocols lighter funding
chainq protocols lighter positions 0xADDRESS      # account value, collateral, open positions
chainq protocols lighter spot markets
chainq protocols lighter spot price ETH LIT/USDC
chainq protocols lighter spot balances 0xADDRESS --min-usd 1
```

`spot balances` is the full view of what an address holds on Lighter. Each asset splits into `available`, `locked` (in open spot orders), and `margin` (perp collateral), priced at Lighter index prices. USDC `margin` is the same collateral `positions` reports, so do not add the two. The `positions` account value excludes spot holdings and non-USDC margin.

For a combined view, `chainq portfolio 0x... --defi` adds Hyperliquid and Lighter equity and spot balances to the onchain sweep.
