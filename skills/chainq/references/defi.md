# DeFi: yields, lending, DEXs, protocol metrics, NFTs

## Cross-protocol yields

```bash
chainq yields                           # sorted by TVL; minimum TVL defaults to $1M
chainq yields --asset usdc              # one asset across protocols and yield types
chainq yields --asset eth -n ethereum   # includes stETH staking
chainq yields --type lp -s apy          # sort: tvl | apy
chainq yields --min-tvl 0
```

Start "best yield on X" questions here. The `type` values (`lending`, `vault`, `staking`, `lp`, `fixed`) carry different risks: LP yields have impermanent loss and fixed yields expire. Say which type a rate is when comparing.

## Lending markets

```bash
chainq protocols aave markets -n ethereum        # reserves by size: supply/borrow APY, utilization
chainq protocols aave markets -c usdc -n base    # one asset, every Aave market on the chain
chainq protocols morpho markets -n base -c usdc  # supply/borrow APY, LLTV, utilization
chainq protocols morpho vaults -c usdc           # curated vaults: gross and net APY, TVL
chainq protocols kamino markets -c usdc          # Solana lending reserves; -c takes a symbol or mint
```

`-s` sorts by `supplied`, `supply-apy`, `borrow-apy`, or `utilization`. Aave data comes from Aave's official API and covers every market on the chain (Core, Prime, EtherFi on ethereum). Kamino covers lending reserves only, not wallet positions, strategies, or vaults.

## Fixed yield (Pendle)

```bash
chainq protocols pendle markets -n ethereum             # implied APY, LP APY, liquidity, expiry
chainq protocols pendle markets -c usde -s implied-apy  # sort: liquidity | implied-apy | expiry
```

Implied APY is the fixed rate you lock by buying PT. Compare `implied_apy_pct` from `--json`.

## Staking and savings rates

```bash
chainq protocols lido apr       # stETH APR (7d SMA), TVL, wstETH/stETH rate
chainq protocols sky rate       # Sky Savings Rate (sUSDS) and legacy DSR, read onchain
chainq protocols ethena yield   # sUSDe APY (current, 30d, 90d), USDe supply and peg
```

## DEX pools

```bash
chainq protocols uniswap pool weth usdc -n ethereum    # onchain state for v2, v3, and v4 fee tiers
chainq protocols uniswap pool eth usdc -V v4           # 'eth' is the native currency; -V v2|v3|v4|all
chainq protocols uniswap pool weth usdc --fee 500      # one tier: 100 | 500 | 3000 | 10000
chainq protocols uniswap pool 0xPoolAddress            # v2/v3 detected from the address
chainq protocols uniswap pools "weth usdc" -n ethereum # indexed discovery: 24h volume, liquidity
chainq protocols uniswap pools usdc -n base -s volume  # sort: liquidity | volume
chainq protocols uniswap stats                         # TVL and 24h/7d/30d volume
chainq protocols curve pools -n ethereum -l 10         # coins, 24h volume, base and CRV APY
chainq protocols curve pools -c usdc -s volume         # sort: tvl | volume | apy
chainq protocols curve stats                           # TVL, volume, fees, crvUSD TVL, CRV price
chainq protocols aerodrome pools -p cl --min-tvl 1000000  # Base; -p all | v1 (AMM) | cl (Slipstream)
chainq protocols aerodrome stats
```

- `uniswap pool` reads factory, pool, and StateView contracts, so its prices and reserves are authoritative. v4 reports price and in-range liquidity without reserves, and its deepest pools use native `eth`, not `weth`. Thin tiers can show stale prices; compare tiers before quoting one.
- `uniswap pools` ranks through DexScreener. Prefer addresses for long-tail tokens.
- Curve `apy_base_pct` is the swap-fee APY; `apy_crv_min_pct` and `apy_crv_max_pct` bound the CRV emissions (max is fully boosted). Curve covers 13 chains.
- Aerodrome `apy_base_pct` is swap fees and `apy_reward_pct` is AERO emissions.

## Any protocol or chain (DefiLlama)

```bash
chainq protocols llama protocol lido     # TVL, chains, fees, DEX volume
chainq protocols llama top -c Lending -l 10
chainq protocols llama chains
```

Use `llama protocol` for any protocol without a dedicated command; DefiLlama tracks thousands.

## NFTs (OpenSea)

```bash
chainq nft floor pudgypenguins azuki   # floor (native and USD), 24h volume, owners
chainq nft collection pudgypenguins    # floor, supply, volumes, contract, links
chainq nft top -s volume -l 10         # sort: volume | 7d-volume | market-cap | owners
```

Collections are OpenSea slugs, the last part of an opensea.io/collection/... URL. `floor` and `collection` work without a key for well-known collections. `nft top` and long-tail slugs need one: `chainq config set opensea-api-key <key>`.
