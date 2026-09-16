# Roadmap

## Vision

Software for agents, not just people. chainq is one universal CLI where any agent (or human) can retrieve and transform data from the Web3 world: RPC state on popular networks with good predefined endpoints, asset prices and metadata, aggregated protocol data, and composable EVM primitives — with zero setup, one-line human output, and `--json` everywhere. Distribution is skill-first: a Claude Code skill instead of an MCP server, because a CLI is self-documenting, composable, costs no context until used, and works in any agent with a shell.

## Status

Per-version history lives in [CHANGELOG.md](CHANGELOG.md). Current surface: 27 EVM networks plus Solana (balances, cross-chain portfolio, tx lookup with decoded ERC-20 transfers and called function, gas, raw RPC; ENS/SNS/base58 addresses); CoinGecko market data with historical prices and OHLC candles; `chainq address` intelligence (EOA/contract/program, proxy resolution, token profile); EVM state queries, contract calls, ABI codecs, hashes, bytes, and conversions; protocols — Aave, Morpho, Kamino lending markets, Uniswap (onchain v2/v3/v4 + indexed), Pendle, Hyperliquid (perps, spot, builder dexs, outcome markets), Lighter, Curve, Lido, Aerodrome, Sky, Ethena, DefiLlama; NFT floors via OpenSea; stablecoins overview; token buyback tracking by reporting period, explicit program selection (HYPE Assistance-Fund fills, SKY Smart Burn Engine execs and UNI Firepit burns live onchain, ZRO parsed live from the LayerZero tracker with a labeled snapshot fallback; LIT reports its data limitation rather than fabricating) and daily US spot crypto ETF net flows (BTC/ETH via The Block); configurable `asset` links (TradingView/Binance/CoinGecko). Release channels are live: a tag push publishes to PyPI (trusted publishing, attestations) and bumps the Homebrew tap.

## Next

- **Portfolio depth, part 2** — Hyperliquid folding shipped in v0.12; the token catalog (v0.20: CoinGecko per-network lists + Aave/Pendle/Jupiter, catalog-wide sweeps, Jupiter/DefiLlama pricing, spam hidden by default) shipped the token-list and long-tail Solana pricing halves. Still to do: Aave/Morpho supplied positions with debt and health factor (aTokens already show as balances; use UiPoolDataProvider or protocol user endpoints).
- **Catalog-driven features** — the catalog (`chainq/catalog.py`, `chainq tokens`) is the base for token ranking/scoring and a token/protocol index; both need a market-cap or liquidity signal per entry (CoinGecko markets, Jupiter `organicScore`) that the catalog does not carry yet.

## Later

- Address intelligence depth: deploy date and verified source for contracts (needs explorer APIs), NFT holdings summary.
- Explorer-based holder discovery (Blockscout/Etherscan "tokens held by address") for tokens outside the catalog: deliberately not done — public instances are unreliable and it is where airdrop spam comes from. Revisit only behind an explicit `--discover` flag if unlisted holdings turn out to matter.
- Generic ERC-4626 inspector: `chainq vault 0xADDR -n base` — asset, share price, APY from share-price delta, TVL; covers thousands of yield vaults with zero per-protocol work.
- NFT depth: wallet holdings and collection-by-contract-address lookup (both need a valid OpenSea key), floor cross-check via a second marketplace.
- CEX spot prices via ccxt as a CoinGecko alternative/cross-check.
- More protocols: bridge status.
- npm launcher: parked — the registry rejects unscoped `chainq` as too similar to `chai`; revisit with a scoped name or an npm support request.
- Watch/stream mode (`chainq gas --watch`) and threshold alerts (reuse PriceAlerts bot).
- Thin MCP wrapper over the CLI if demand appears from non-shell agents.

## Engineering improvements

- Wire the live smoke-test suite (`pytest -m live`, shipped in v0.12) into a weekly scheduled CI job to catch upstream API drift.
- Cross-platform check: Windows terminal output (the banner and `…` glyphs) and CI matrix entry.
