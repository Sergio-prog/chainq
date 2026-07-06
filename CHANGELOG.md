# Changelog

Generated from conventional commits (`scripts/gen_changelog.py`).

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
