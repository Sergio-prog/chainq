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

$ chainq protocols aave markets -n base --format table -l 3
network: base
market  symbol  supply_apy_pct  borrow_apy_pct    supplied_usd  utilization_pct
------  ------  --------------  --------------  --------------  ---------------
Base    USDC            3.1684          4.2507  176,010,037.57          83.2569
Base    WETH            1.5411          2.2608  160,504,459.31          80.4814
Base    cbBTC           0.0149          0.7126  144,452,332.80           4.2015
```

## Why

Agents are terrible at juggling five different APIs, auth schemes, and SDKs — and great at running one predictable CLI. chainq gives every command three output modes:

| Mode | Flag | Output |
|---|---|---|
| human | *(default)* | one readable line per result |
| machine | `--json` | structured JSON for parsing |
| table | `--format table` | aligned columns for humans scanning lists |
| toon | `--format toon` | compact tabular text — fewer tokens than JSON for LLM contexts |
| pipe | `-q` | bare primary value only |

Plus `-v` for provenance (RPC endpoint used, data source, explorer links). Errors go to stderr with exit code 1. Responses are cached briefly (30–60s) so repeated queries stay fast and under rate limits.

## Install

One-liner:

```bash
curl -LsSf https://raw.githubusercontent.com/Sergio-prog/chainq/main/install.sh | sh
```

Homebrew:

```bash
brew install sergio-prog/tap/chainq
```

Or directly with uv / pipx:

```bash
uv tool install chainq
pipx install chainq
```

From source:

```bash
git clone https://github.com/Sergio-prog/chainq && cd chainq
uv tool install .
```

Requires Python 3.12+ (the install script bootstraps uv, which handles that for you). Update any time with `chainq update` — chainq also checks for new versions once a day and prints a reminder, homebrew/pnpm style. Shell tab-completion: `chainq --install-completion`.

## Commands

### Market data (CoinGecko)

```bash
chainq price eth btc sol         # spot price, 24h change, market cap
chainq price 0xTokenAddress      # any token by contract address (DexScreener fallback for long-tail)
chainq trending                  # trending assets right now
chainq stables                   # stablecoins by mcap: peg price, supply changes, mechanism
chainq asset ethena              # full profile: price, mcap/FDV, supply, ATH, links
chainq search "sky protocol"     # resolve fuzzy names to asset ids
```

### Onchain (EVM)

```bash
chainq networks                                       # supported networks and aliases
chainq balance vitalik.eth                            # native balance, ENS supported
chainq balance 0x... --coin usdt -n arbitrum          # ERC-20 by symbol or contract address
chainq portfolio vitalik.eth                          # all networks: native + known tokens, USD total
chainq gas -n base                                    # gas price, base fee, transfer cost in USD
chainq tx 0xHASH -n ethereum                          # status, parties, value, fee, block
chainq rpc eth_blockNumber -n optimism                # raw JSON-RPC escape hatch
```

25 networks: **ethereum, arbitrum, base, optimism, polygon, bsc, avalanche, gnosis, unichain, linea, scroll, zksync, mantle, blast, sonic, berachain, worldchain, ink, soneium, celo, sei, hyperevm, monad, plasma, katana** — by key, alias (`eth`, `arb`, `op`, ...), or chain id. Multiple public RPCs per network are tried in order; override with `CHAINQ_RPC_<NETWORK>`.

### Protocols

Aave v3:

```bash
chainq protocols aave markets -n ethereum         # reserves: supply/borrow APY, size, utilization
chainq protocols aave markets -c usdc -n base     # one asset across markets
chainq protocols aave markets -s borrow-apy       # sort: supplied | supply-apy | borrow-apy | utilization
```

Uniswap and Pendle:

```bash
chainq protocols uniswap pool weth usdc           # onchain pool state: v2+v3+v4, price + reserves per fee tier
chainq protocols uniswap pool eth usdc -V v4      # native-currency v4 pools; -V v2|v3|v4|all
chainq protocols uniswap pool 0xPoolAddress       # one pool by address, v2/v3 auto-detected
chainq protocols uniswap pools "weth usdc"        # pool discovery: price, 24h volume, liquidity, v2/v3/v4
chainq protocols uniswap stats                    # protocol TVL + volumes
chainq protocols pendle markets -s implied-apy    # yield markets: implied APY, LP APY, expiry
```

Sky and Ethena:

```bash
chainq protocols sky rate                         # Sky Savings Rate (sUSDS) + legacy DSR, onchain
chainq protocols ethena yield                     # sUSDe APY, protocol yield, USDe supply/peg
```

Hyperliquid (public data, incl. HIP-3 builder dexs and HIP-4 outcome markets):

```bash
chainq protocols hl price BTC ETH                 # perps: mark price, 24h change, volume, OI, funding
chainq protocols hl markets -s oi                 # top perp markets by volume | oi | funding | change
chainq protocols hl funding                       # most extreme funding rates (hourly + APR)
chainq protocols hl positions 0xADDRESS           # perp account: value, margin, positions with PnL
chainq protocols hl dexs                          # HIP-3 builder-deployed perp dexs
chainq protocols hl markets --dex xyz             # markets on a builder dex (tokenized stocks etc.)
chainq protocols hl outcomes "world cup"          # HIP-4 prediction markets with live Yes/No prices
chainq protocols hl spot price HYPE               # spot pairs: price, 24h change, volume, mcap
chainq protocols hl spot markets                  # top spot markets by volume
chainq protocols hl spot balances 0xADDRESS       # spot token balances with USD values
```

Morpho and DefiLlama:

```bash
chainq protocols morpho markets -c usdc -n base   # Morpho lending markets: APYs, lltv, utilization
chainq protocols morpho vaults -c usdc            # Morpho vaults: APY, TVL
chainq protocols llama protocol lido              # any protocol's TVL/fees/volume via DefiLlama
chainq protocols llama top -c Lending             # top protocols by TVL
chainq protocols llama chains                     # chains ranked by DeFi TVL
```

NFTs (OpenSea):

```bash
chainq nft floor pudgypenguins azuki              # floor price (native + USD), 24h volume, owners
chainq nft collection pudgypenguins               # profile: floor, supply, volumes, contract, links
chainq nft top -s volume                          # top collections (requires OpenSea API key)
```

Lighter (public data):

```bash
chainq protocols lighter markets -s oi            # perp markets: last price, volume, OI, funding
chainq protocols lighter price BTC ETH            # single markets
chainq protocols lighter funding                  # funding rates (hourly + APR)
chainq protocols lighter positions 0xADDRESS      # account value, collateral, open positions
```

## Configuration

Everything works without configuration. To persist settings, use `chainq config`:

```bash
chainq config set coingecko-api-key CG-xxxx
chainq config set chainq-rpc-ethereum https://my-node.example.com
chainq config list        # secrets masked; --show-secrets to reveal
```

Values live in `~/.config/chainq/.env`; plain env vars and a `.env` in cwd work too:

| Variable | Purpose |
|---|---|
| `COINGECKO_API_KEY` | raises CoinGecko rate limits (free demo key works) |
| `CHAINQ_RPC_<NETWORK>` | custom RPC endpoint, tried first (e.g. `CHAINQ_RPC_ETHEREUM`) |
| `CHAINQ_HTTP_TIMEOUT` / `CHAINQ_RPC_TIMEOUT` | timeouts in seconds |
| `CHAINQ_NO_UPDATE_CHECK` | disable the daily update check |
| `OPENSEA_API_KEY` | unlocks `nft top` and long-tail collection slugs |

## For AI agents

chainq ships a [skill](skills/chainq/SKILL.md) that teaches agents when and how to use it:

```bash
npx skills add Sergio-prog/chainq
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
