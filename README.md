# chainq

Agent-friendly CLI for onchain and crypto market data. One tool for balances, gas, transactions, raw EVM RPC, asset prices, and Hyperliquid — with curated public RPC endpoints and no setup required.

Built for AI agents first (predictable one-line output, `--json` everywhere, meaningful exit codes), pleasant for humans too.

## Install

```bash
uv tool install chainq
```

or from source:

```bash
git clone <repo> && cd chainq
uv tool install .
```

## Quickstart

```bash
chainq price eth btc hype
chainq balance vitalik.eth
chainq balance 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 --coin usdt --network arbitrum
chainq gas --network base
chainq tx 0x... --network ethereum
chainq rpc eth_blockNumber --network optimism
chainq asset ethena
chainq search "sky protocol"
chainq hl price BTC ETH
chainq hl funding --limit 10
chainq hl positions 0x...
chainq networks
```

## Output modes

Every command supports three modes:

```bash
$ chainq price eth
ETH (Ethereum): $2,543.12  24h +1.20%  mcap $306.51B

$ chainq price eth -q
2543.12

$ chainq price eth --json
[{"id": "ethereum", "symbol": "eth", "price_usd": 2543.12, ...}]
```

`-v` adds detail (RPC endpoint used, extra market fields, explorer links). Errors go to stderr with exit code 1.

## Networks

EVM chains with curated public RPCs and automatic fallback: ethereum, arbitrum, base, optimism, polygon, bsc, avalanche, gnosis, unichain. Accepts aliases (`eth`, `arb`, `op`, ...) and chain ids. Override any RPC with `CHAINQ_RPC_<NETWORK>`, e.g. `CHAINQ_RPC_ETHEREUM=https://...`.

## Configuration

Optional. Env vars, or a `.env` in the working directory or `~/.config/chainq/.env`:

| Variable | Purpose |
|---|---|
| `COINGECKO_API_KEY` | raises CoinGecko rate limits (free demo key works) |
| `OPENSEA_API_KEY` | reserved for upcoming NFT commands |
| `CHAINQ_RPC_<NETWORK>` | custom RPC endpoint, tried first |
| `CHAINQ_HTTP_TIMEOUT` / `CHAINQ_RPC_TIMEOUT` | timeouts in seconds |

## Agent skill

`skills/chainq/` contains a Claude Code skill teaching agents when and how to use chainq. Install it:

```bash
ln -s "$(pwd)/skills/chainq" ~/.claude/skills/chainq
```

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
```
