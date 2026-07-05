# Changelog

Generated from conventional commits (`scripts/gen_changelog.py`).

## Unreleased

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
