# chainq

**One CLI for the crypto world — built for AI agents, pleasant for humans.**

Query asset prices, wallet balances, gas, transactions, raw EVM RPC, Aave markets, and Hyperliquid perps from a single tool. Zero setup: curated public RPC endpoints with automatic fallback are built in, and no command below needs an API key.

```console
$ chainq price eth btc hype
ETH (Ethereum): $1,691.88  24h +4.82%  mcap $204.11B
BTC (Bitcoin): $61,302.00  24h +1.85%  mcap $1.23T
HYPE (Hyperliquid): $65.79  24h +4.38%  mcap $14.63B

$ chainq balance vitalik.eth
vitalik.eth (0xd8dA…6045) on Ethereum: 5.6955 ETH (~$9,635.87)

$ chainq hl funding --limit 3
ME-PERP funding: -0.1713%/h (-1500.8% APR)  mark $0.0681  OI $371.51K
CELO-PERP funding: -0.0272%/h (-238.2% APR)  mark $0.061639  OI $146.98K
STABLE-PERP funding: -0.0162%/h (-142.3% APR)  mark $0.03519  OI $2.29M
```

## Why

Agents are terrible at juggling five different APIs, auth schemes, and SDKs — and great at running one predictable CLI. chainq gives every command three output modes:

| Mode | Flag | Output |
|---|---|---|
| human | *(default)* | one readable line per result |
| machine | `--json` | structured JSON for parsing |
| pipe | `-q` | bare primary value only |

Plus `-v` for provenance (RPC endpoint used, data source, explorer links). Errors go to stderr with exit code 1. Responses are cached briefly (30–60s) so repeated queries stay fast and under rate limits.

## Install

One-liner:

```bash
curl -LsSf https://raw.githubusercontent.com/Sergio-prog/chainq/main/install.sh | sh
```

Or directly with [uv](https://docs.astral.sh/uv/) / pipx:

```bash
uv tool install --from git+https://github.com/Sergio-prog/chainq chainq
pipx install git+https://github.com/Sergio-prog/chainq
```

From source:

```bash
git clone https://github.com/Sergio-prog/chainq && cd chainq
uv tool install .
```

Requires Python 3.12+ (the install script bootstraps uv, which handles that for you). Update any time with `chainq update` — chainq also checks for new versions once a day and prints a reminder, homebrew/pnpm style.

## Commands

### Market data (CoinGecko)

```bash
chainq price eth btc sol         # spot price, 24h change, market cap
chainq asset ethena              # full profile: price, mcap/FDV, supply, ATH, links
chainq search "sky protocol"     # resolve fuzzy names to asset ids
```

### Onchain (EVM)

```bash
chainq networks                                       # supported networks and aliases
chainq balance vitalik.eth                            # native balance, ENS supported
chainq balance 0x... --coin usdt -n arbitrum          # ERC-20 by symbol or contract address
chainq gas -n base                                    # gas price, base fee, transfer cost in USD
chainq tx 0xHASH -n ethereum                          # status, parties, value, fee, block
chainq rpc eth_blockNumber -n optimism                # raw JSON-RPC escape hatch
```

Networks: **ethereum, arbitrum, base, optimism, polygon, bsc, avalanche, gnosis, unichain** — by key, alias (`eth`, `arb`, `op`, ...), or chain id. Multiple public RPCs per network are tried in order; override with `CHAINQ_RPC_<NETWORK>`.

### Aave v3

```bash
chainq aave markets -n ethereum                # reserves: supply/borrow APY, size, utilization
chainq aave markets -c usdc -n base            # one asset across markets
chainq aave markets -s borrow-apy -l 10        # sort: supplied | supply-apy | borrow-apy | utilization
```

### Hyperliquid (perps, public data)

```bash
chainq hl price BTC ETH          # mark/oracle price, 24h change, volume, OI, funding
chainq hl markets -s oi          # top markets by volume | oi | funding | change
chainq hl funding                # most extreme funding rates (hourly + APR)
chainq hl positions 0xADDRESS    # account value, margin, open positions with PnL
```

## Configuration

Everything works without configuration. Optional env vars (or `.env` in cwd / `~/.config/chainq/.env`):

| Variable | Purpose |
|---|---|
| `COINGECKO_API_KEY` | raises CoinGecko rate limits (free demo key works) |
| `CHAINQ_RPC_<NETWORK>` | custom RPC endpoint, tried first (e.g. `CHAINQ_RPC_ETHEREUM`) |
| `CHAINQ_HTTP_TIMEOUT` / `CHAINQ_RPC_TIMEOUT` | timeouts in seconds |
| `CHAINQ_NO_UPDATE_CHECK` | disable the daily update check |
| `OPENSEA_API_KEY` | reserved for upcoming NFT commands |

## For AI agents

chainq ships a [Claude Code skill](skills/chainq/SKILL.md) that teaches agents when and how to use it:

```bash
ln -s "$(pwd)/skills/chainq" ~/.claude/skills/chainq
```

No skill installed? Agents can self-discover everything via `chainq -h` and `chainq <command> -h`.

## Roadmap

NFT floors, Uniswap pools, stablecoin protocols (Sky, Ethena), portfolio sweep, Solana, and more — see [ROADMAP.md](ROADMAP.md).

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
```

## License

[MIT](LICENSE)
