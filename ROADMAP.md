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

## Next

- **PyPI release** — release workflow (tag-triggered, trusted publishing) and PyPI-first install.sh are in place; owner must add a PyPI trusted publisher (project `chainq`, repo `Sergio-prog/chainq`, workflow `release.yml`, environment `pypi`) and push a `v*` tag. Then a Homebrew tap.

## Later

- Solana support (balances, token accounts, prices).
- CEX spot prices via ccxt as a CoinGecko alternative/cross-check.
- Historical data: OHLC candles, price at date, funding history.
- More protocols: Lido/staking yields, Pendle, Morpho, bridges status.
- Watch/stream mode (`chainq gas --watch`) and threshold alerts (reuse PriceAlerts bot).
- Thin MCP wrapper over the CLI if demand appears from non-shell agents.

## Engineering improvements

- Auto token lists from CoinGecko per network instead of the hand-curated registry.
- CI (ruff + pytest + release automation); versioned CHANGELOG.
- Structured error output in `--json` mode (`{"error": ...}` on stdout).
