# Changelog

Generated from conventional commits (`scripts/gen_changelog.py`).

## v0.21.0

### Features
- add Arc mainnet network

## v0.20.2

### Fixes
- per-request RPC failover and verified endpoint registry

### Documentation
- regenerate release references for v0.20.2

## v0.20.1

### Fixes
- add DexScreener mapping for Robinhood Chain

### Documentation
- regenerate release references for v0.20.1

## v0.20.0

### Features
- token catalog with catalog-wide sweeps, price cascade, and spam-free portfolios

### Documentation
- regenerate release references for v0.20.0
- record plan 010 execution and unblock 011

## v0.19.0

### Features
- add Robinhood Chain mainnet

### Documentation
- regenerate release references for v0.19.0

## v0.18.0

### Features
- decode ERC-20 transfers and called function in tx
- token buybacks, ETF flows, and configurable asset links

### Fixes
- make tx decode metadata and 4byte lookup fully best-effort

### Documentation
- regenerate release references for v0.18.0
- add tx decoding follow-up plans
- reconcile implementation plans

## v0.17.1

### Features
- colorize yields output
- align yields text output
- refine yields and update workflows

### Documentation
- regenerate changelog for v0.17.1

## v0.17.0

### Features
- add cross-protocol yields command
- add Kamino lending markets
- support Solana mints in market commands

### Documentation
- regenerate release references for v0.17.0
- mark completed plans merged
- reconcile implementation plans
- regenerate changelog for v0.16.0

## v0.16.0

### Features
- add EVM query and utility commands

### Documentation
- add Robinhood Kamino and Pump plans
- regenerate changelog for v0.15.1

## v0.15.1

### Fixes
- route hl funding, morpho and pendle percentages through fmt_pct

### Documentation
- regenerate changelog for v0.15.0

## v0.15.0

### Features
- add global --version and --no-color flags
- dim labels and bold values across all command output

### Fixes
- **site**: absolute og image url and og:url for scrapers
- **site**: use jpg og image for social card compatibility

### Documentation
- regenerate changelog for v0.14.0

## v0.14.0

### Features
- add windows install tab and social meta tags to site
- windows powershell installer and hardened install.sh
- colorize prices, mcap, and 24h change in tty output

### Documentation
- add implementation plans for six roadmap features
- slim roadmap to status and next, drop changelog duplication
- regenerate changelog for v0.13.1

### Refactoring
- move coingecko and uniswap static data to dedicated modules

## v0.13.1

### Features
- add one-screen landing page with llms.txt standard

### Documentation
- add website link to package metadata and README
- add chain emoji to README title
- regenerate changelog for v0.13.0

## v0.13.0

### Features
- resolve .sol domains via Solana Name Service
- add curve protocol commands
- add address intelligence command
- add solana support across core commands
- batch onchain reads with Multicall3

### Documentation
- compact the skill description
- regenerate changelog for v0.12.1

## v0.12.1

### Fixes
- detect homebrew installs in chainq update

## v0.12.0

### Features
- historical data, portfolio depth, lido/aerodrome, structured errors

### Fixes
- brew formula installs via python -m pip

### Documentation
- mark pypi and homebrew channels live, remove npx install

### CI
- drop npm publish job, registry rejects the unscoped name

## v0.11.0

### Features
- portfolio sweep across all networks with usd totals
- stablecoins overview, sky savings rate, ethena yield
- nft commands via opensea (floor, collection, top)
- defillama adapter, morpho, chainq config, retries, rpc racing, completions
- discover assets and pools by contract address
- uniswap pool reads v2, v3, and v4 onchain
- 25 networks, onchain uniswap pools, lighter, hl hip-3/hip-4
- uniswap and pendle under protocols group
- protocols group, hyperliquid spot, trending, table/toon formats
- aave v3 markets, ttl cache, self-update with daily reminder, installer
- chainq v1 — prices, EVM chain queries, hyperliquid, agent skill

### Documentation
- refresh roadmap with next/later/engineering suggestions
- add morpho and defillama to skill description

### CI
- npm launcher package, homebrew tap bump job
- release workflow with pypi trusted publishing, pypi-first install
