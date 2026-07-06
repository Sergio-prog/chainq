# Roadmap

## Vision

Software for agents, not just people. chainq is one universal CLI where any agent (or human) can query the crypto world: RPC state on popular networks with good predefined endpoints, asset prices and metadata, and aggregated data from major protocols — with zero setup, one-line human output, and `--json` everywhere. Distribution is skill-first: a Claude Code skill instead of an MCP server, because a CLI is self-documenting, composable, costs no context until used, and works in any agent with a shell.

## Shipped

- **v0.1** — 9 EVM networks with curated fallback RPCs; `balance` (native + ERC-20, ENS), `gas`, `tx`, raw `rpc`; CoinGecko `price`/`asset`/`search`; Hyperliquid perps (`hl price/markets/funding/positions`); `--json` / `-q` / `-v` output contract; agent skill.
- **v0.2** — Aave v3 markets (official GraphQL API); TTL cache; `chainq update` + daily new-version reminder; `install.sh`.
- **v0.3** — `protocols` command group (aave, hl); Hyperliquid spot (prices, markets, balances); `trending`; `--format table|toon` output formats; AGENTS.md; banner installer.
- **v0.4** — Uniswap (pools via DexScreener, protocol stats via DefiLlama) and Pendle (active markets, implied/LP APY) under `protocols`.
- **v0.5** — 25 networks (added linea, scroll, zksync, mantle, blast, sonic, berachain, worldchain, ink, soneium, celo, sei, hyperevm, monad, plasma, katana); onchain Uniswap v3 `pool` command (factory + slot0); Lighter perps (markets, price, funding, positions); Hyperliquid HIP-3 builder dexs (`hl dexs`, `--dex`) and HIP-4 outcome markets (`hl outcomes`); skill install via `npx skills add`.
- **v0.6** — onchain Uniswap `pool` covers v2 + v3 + v4 (v2 pairs via getReserves, v4 via StateView + computed poolId, native-currency support with `eth`).
- **v0.7** — address-based discovery: `price`/`asset` accept token contract addresses (DexScreener locates the chain → CoinGecko contract lookup → DexScreener price fallback for long-tail tokens); `uniswap pool` accepts a bare pool address with v2/v3 auto-detection.
- **v0.8** — Morpho (markets + vaults via official GraphQL API); DefiLlama adapter (`llama protocol/top/chains` for any protocol); `chainq config` command; HTTP retry with backoff on all providers; parallel RPC endpoint racing; shell completions.
- **v0.9** — NFTs via OpenSea (`nft floor/collection/top`): floors with USD conversion, volumes, owners, supply; keyless for well-known collections, API key unlocks `top` and long-tail slugs.
- **v0.10** — stablecoins: `stables` overview (mcap ranking, peg price, supply changes via DefiLlama stablecoins API), `sky rate` (SSR + legacy DSR read onchain), `ethena yield` (sUSDe APY via official API, USDe supply/peg).
- **v0.11** — `portfolio`: parallel sweep of native + registry tokens across all 25 networks with one batched CoinGecko pricing call, sorted by USD value; `--min-usd` dust filter, `-n` repeatable network filter.
- **v0.12** — historical data (`candles <asset> --days N` OHLC, `price --at DATE`, `hl funding --history`); `portfolio --defi` folds in Hyperliquid perp equity + spot balances, plus `--hide-unpriced`; new protocols Lido (`lido apr`) and Aerodrome (`aerodrome stats/pools`); more filters (`hl spot balances --min-usd`, `stables --min-mcap`); structured JSON errors (`{"error": ...}` on stdout in `--json` mode); CHANGELOG generated from conventional commits; live smoke-test suite (`pytest -m live`).
- **v0.13** — Solana read-only support (SOL/SPL `balance`, `portfolio` sweeps all token accounts in one call, `tx` by signature, `gas` with priority fees, raw `rpc`; base58 addresses auto-route); `chainq address` intelligence (EOA vs contract vs program, EIP-1967/1167/ZeppelinOS proxy resolution, EIP-7702 delegation, ERC-20 profile, holdings, reverse ENS); Curve (`curve pools/stats` via official API, 13 chains); Multicall3 batching everywhere onchain (portfolio = 1 eth_call per network, uniswap `pool` = 3 batched roundtrips).

## Next

- **Release channels** — done since v0.11.0: tag-triggered workflow publishes to PyPI (trusted publishing, GitHub release with attestations) and bumps the Homebrew formula in [Sergio-prog/homebrew-tap](https://github.com/Sergio-prog/homebrew-tap) via `TAP_GITHUB_TOKEN`. npm launcher (`npm/`) is parked: the registry rejects unscoped `chainq` as too similar to `chai`; revisit with a scoped name or an npm support request.
- **Portfolio depth, part 2** — Hyperliquid folding shipped in v0.12; still to do: Aave/Morpho supplied positions (onchain aToken / UiPoolDataProvider reads or protocol user endpoints), and auto token lists per network from CoinGecko (top ~50 by mcap, cached daily) so the sweep catches far more than the curated registry. Solana portfolio pricing for long-tail mints (DexScreener batch lookup) would fold in here too.

## Later

- Address intelligence depth: deploy date and verified source for contracts (needs explorer APIs), NFT holdings summary.
- Generic ERC-4626 inspector: `chainq vault 0xADDR -n base` — asset, share price, APY from share-price delta, TVL; covers thousands of yield vaults with zero per-protocol work.
- NFT: wallet holdings and collection-by-contract-address lookup (both need a valid OpenSea key), floor cross-check via a second marketplace.
- CEX spot prices via ccxt as a CoinGecko alternative/cross-check.
- More protocols: bridge status (Curve shipped in v0.13; Lido and Aerodrome in v0.12).
- Watch/stream mode (`chainq gas --watch`) and threshold alerts (reuse PriceAlerts bot).
- Thin MCP wrapper over the CLI if demand appears from non-shell agents.

## Engineering improvements

- Wire the live smoke-test suite (`pytest -m live`, shipped in v0.12) into a weekly scheduled CI job to catch upstream API drift.
- Cross-platform check: Windows terminal output (the banner and `…` glyphs) and CI matrix entry.
