# Roadmap

## Vision

Software for agents, not just people. chainq is one universal CLI where any agent (or human) can retrieve and transform data from the Web3 world: RPC state on popular networks with good predefined endpoints, asset prices and metadata, aggregated protocol data, and composable EVM primitives — with zero setup, one-line human output, and `--json` everywhere. Distribution is skill-first: a Claude Code skill instead of an MCP server, because a CLI is self-documenting, composable, costs no context until used, and works in any agent with a shell.

## Status

Per-version history lives in [CHANGELOG.md](CHANGELOG.md). Current surface: 25 EVM networks plus Solana (balances, cross-chain portfolio, tx lookup, gas, raw RPC; ENS/SNS/base58 addresses); CoinGecko market data with historical prices and OHLC candles; `chainq address` intelligence (EOA/contract/program, proxy resolution, token profile); EVM state queries, contract calls, ABI codecs, hashes, bytes, and conversions; protocols — Aave, Morpho, Uniswap (onchain v2/v3/v4 + indexed), Pendle, Hyperliquid (perps, spot, builder dexs, outcome markets), Lighter, Curve, Lido, Aerodrome, Sky, Ethena, DefiLlama; NFT floors via OpenSea; stablecoins overview. Release channels are live: a tag push publishes to PyPI (trusted publishing, attestations) and bumps the Homebrew tap.

## Next

- **Portfolio depth, part 2** — Hyperliquid folding shipped in v0.12; still to do: Aave/Morpho supplied positions (onchain aToken / UiPoolDataProvider reads or protocol user endpoints), and auto token lists per network from CoinGecko (top ~50 by mcap, cached daily) so the sweep catches far more than the curated registry. Solana portfolio pricing for long-tail mints (DexScreener batch lookup) would fold in here too.

## Later

- Address intelligence depth: deploy date and verified source for contracts (needs explorer APIs), NFT holdings summary.
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
