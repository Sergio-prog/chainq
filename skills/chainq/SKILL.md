---
name: chainq
description: Live crypto and onchain data through the chainq CLI. Use for token prices (spot, historical, OHLC), wallet balances and multi-chain portfolios (EVM + Solana), gas, transactions, raw RPC, what an address is, lending/borrowing and yield rates, DEX pools, TVL and fees of any protocol, perp funding and prediction markets (Hyperliquid, Lighter), NFT floors, stablecoins, token buybacks, and ETF flows.
---

# chainq

One CLI for onchain and market data. Public endpoints with RPC fallback are built in. Only `nft top` and long-tail NFT slugs need an API key.

If `chainq --version` fails, install it (Python 3.12+): `uv tool install chainq`, or `curl -LsSf https://raw.githubusercontent.com/Sergio-prog/chainq/main/install.sh | sh`.

## Output

- Default output is one plain line per result. Show it to the user as is.
- `--json` returns structured data to parse or compute over. `-f toon` is the same data in 2-3x fewer tokens; use it for long lists.
- `-q` prints the bare primary value. `-v` adds provenance: RPC endpoint, sources, explorer links.
- `-f table` aligns rows under headers for the user.
- Errors go to stderr with exit 1. With `--json`, the error is `{"error": "..."}` on stdout instead. Usage errors (bad flag or argument) exit 2.
- Partial failures are reported, not hidden. `portfolio` lists networks it could not reach in `unreachable` and failed price sources in `price_failures`. Rerun once before telling the user data is missing.
- A CoinGecko rate-limit error means wait a minute. It does not affect RPC commands.

## Finding the right command

`chainq schema` prints one usage line per command with every option. `chainq schema protocols hl --json` describes one subtree with types, defaults, and choices. Read the matching reference file below for usage notes before the first call in a domain.

| Question | Command | Reference |
| --- | --- | --- |
| Price, market cap, history, candles | `price`, `asset`, `candles`, `search`, `trending` | [market.md](references/market.md) |
| Stablecoin supply and pegs | `stables` | [market.md](references/market.md) |
| Token buybacks, ETF flows | `buybacks`, `etf` | [market.md](references/market.md) |
| Wallet balance or net worth | `balance`, `portfolio` | [onchain.md](references/onchain.md) |
| What an address is | `address` | [onchain.md](references/onchain.md) |
| Gas, transactions, raw RPC, EVM utilities | `gas`, `tx`, `rpc`, `evm ...` | [onchain.md](references/onchain.md) |
| Unknown token symbol | `tokens search` | [onchain.md](references/onchain.md) |
| Where to earn yield on an asset | `yields --asset X` | [defi.md](references/defi.md) |
| Lending markets, DEX pools, protocol TVL and fees | `protocols aave/morpho/kamino/pendle/uniswap/curve/aerodrome/llama` | [defi.md](references/defi.md) |
| Staking and savings rates | `protocols lido/sky/ethena` | [defi.md](references/defi.md) |
| NFT floors | `nft` | [defi.md](references/defi.md) |
| Perps, funding, prediction markets | `protocols hl`, `protocols lighter` | [perps.md](references/perps.md) |

Networks: 27 EVM chains plus Solana. `-n` takes a key, alias, or chain id and defaults to ethereum; `chainq networks` lists them. Solana addresses, `.sol` names, and signatures route to Solana automatically.

Settings persist with `chainq config set <key> <value>` (API keys, `CHAINQ_RPC_<NETWORK>` overrides, timeouts); `config get`, `unset`, `list`, and `path` manage them. `chainq update` upgrades chainq, and `chainq version` prints the installed one.
