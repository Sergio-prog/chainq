# ⛓️ chainq

**One CLI for the crypto world — built for AI agents, pleasant for humans.**

[chainq.serhiifotex.dev](https://chainq.serhiifotex.dev/)

Query and transform Web3 data from one predictable CLI: asset prices, wallet balances and portfolios (EVM + Solana), gas, transactions, raw RPC, address intelligence, DeFi protocols, perps, and EVM utilities. Zero setup: curated public RPC endpoints with automatic fallback are built in, and no command below needs an API key.

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

In interactive terminals the text output is colorized — dim labels, bold values, green/red price changes. Piped output stays plain automatically; disable colors explicitly with `chainq --no-color <command>` or the `NO_COLOR` env var. `chainq --version` prints the version.

## Install

One-liner (macOS / Linux):

```bash
curl -LsSf https://raw.githubusercontent.com/Sergio-prog/chainq/main/install.sh | sh
```

Windows:

```powershell
powershell -c "irm https://raw.githubusercontent.com/Sergio-prog/chainq/main/install.ps1 | iex"
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

The install scripts bootstrap uv if it's missing (whether or not Python is already installed — uv provisions Python 3.12+ as needed). Update any time with `chainq update` — chainq also checks for new versions once a day and prints a reminder, homebrew/pnpm style. Shell tab-completion: `chainq --install-completion`.

## Commands

### Market data (CoinGecko)

```bash
chainq price eth btc sol         # spot price, 24h change, market cap
chainq price 0xTokenAddress      # any token by contract address (DexScreener fallback for long-tail)
chainq price btc --at 2025-03-01 # historical price on a date (last 365 days)
chainq candles btc --days 30     # OHLC candles; granularity auto-scales with the window
chainq trending                  # trending assets right now
chainq stables --min-mcap 1e9    # stablecoins by mcap: peg price, supply changes, mechanism
chainq yields --asset usdc       # cross-protocol yields ranked by APY; types are not risk-equivalent
chainq asset ethena              # full profile: price, mcap/FDV, supply, ATH, links
chainq search "sky protocol"     # resolve fuzzy names to asset ids
```

### Onchain (EVM + Solana)

```bash
chainq networks                                       # supported networks and aliases
chainq balance vitalik.eth                            # native balance, ENS supported
chainq balance toly.sol                               # .sol domains too (SNS), auto-routed to Solana
chainq balance 0x... --coin usdt -n arbitrum          # ERC-20 by symbol or contract address
chainq balance 9WzDX... -n solana --coin usdc         # SOL and SPL token balances
chainq portfolio vitalik.eth                          # all networks: native + known tokens, USD total
chainq portfolio 9WzDX...                             # Solana wallets: SOL + every SPL token account
chainq portfolio 0x... --defi --hide-unpriced         # fold in Hyperliquid perp+spot; drop dust/unpriced
chainq address 0x... -n base                          # EOA vs contract, proxies, EIP-7702, holdings
chainq address TokenkegQ...                           # Solana: wallet vs program, token accounts
chainq gas -n base                                    # gas price, base fee, transfer cost in USD
chainq tx 0xHASH -n ethereum                          # status, parties, value, fee, block
chainq tx 5Ufd... -n solana                           # Solana signature lookup
chainq rpc eth_blockNumber -n optimism                # raw JSON-RPC escape hatch (getSlot on solana)
```

### EVM queries and utilities

`chainq evm` exposes common EVM primitives for agent workflows. Run `chainq evm --help` for the complete command catalog instead of loading it into agent context up front.

```bash
chainq evm block-number -n base                       # latest block
chainq evm find-block 2026-07-01T12:00:00Z            # block closest to a timestamp
chainq evm code 0xContract -n base                    # contract bytecode
chainq evm storage 0xContract 0 -n base               # storage word at a slot
chainq evm call 0xToken 'balanceOf(address)' '["0xHolder"]' --returns uint256
chainq evm estimate 0xToken 'transfer(address,uint256)' '["0xTo",1]'
chainq evm sig 'transfer(address,uint256)'             # 0xa9059cbb
chainq evm abi-encode 'address,uint256' '["0xTo",1]'
chainq evm keccak 'hello'                              # Keccak-256 of UTF-8 text
chainq evm to-wei 1.5 ether                            # 1500000000000000000
```

Every subcommand supports `--json`, `-q`, `-v`, and `--format`. Existing `chainq balance`, `chainq gas`, `chainq tx`, and `chainq rpc` remain the canonical cross-chain commands.

25 EVM networks: **ethereum, arbitrum, base, optimism, polygon, bsc, avalanche, gnosis, unichain, linea, scroll, zksync, mantle, blast, sonic, berachain, worldchain, ink, soneium, celo, sei, hyperevm, monad, plasma, katana** — plus **solana** — by key, alias (`eth`, `arb`, `op`, `sol`, ...), or chain id. Multiple public RPCs per network are tried in order; override with `CHAINQ_RPC_<NETWORK>`. Onchain token reads batch through Multicall3, so portfolio sweeps cost one RPC call per network.

### Protocols

Aave v3:

```bash
chainq protocols aave markets -n ethereum         # reserves: supply/borrow APY, size, utilization
chainq protocols aave markets -c usdc -n base     # one asset across markets
chainq protocols aave markets -s borrow-apy       # sort: supplied | supply-apy | borrow-apy | utilization
```

Kamino lending on Solana:

```bash
chainq protocols kamino markets                   # reserves: supply/borrow APY, supplied USD, utilization
chainq protocols kamino markets -c usdc           # exact symbol or mint filter across discovered markets
chainq protocols kamino markets -s supply-apy     # sort: supplied | supply-apy | borrow-apy | utilization
```

Uniswap, Curve, and Pendle:

```bash
chainq protocols uniswap pool weth usdc           # onchain pool state: v2+v3+v4, price + reserves per fee tier
chainq protocols uniswap pool eth usdc -V v4      # native-currency v4 pools; -V v2|v3|v4|all
chainq protocols uniswap pool 0xPoolAddress       # one pool by address, v2/v3 auto-detected
chainq protocols uniswap pools "weth usdc"        # pool discovery: price, 24h volume, liquidity, v2/v3/v4
chainq protocols uniswap stats                    # protocol TVL + volumes
chainq protocols curve pools -c usdc -s volume    # Curve pools: TVL, 24h volume, base + CRV APY
chainq protocols curve stats                      # Curve TVL, volume, fees, crvUSD, CRV price
chainq protocols pendle markets -s implied-apy    # yield markets: implied APY, LP APY, expiry
```

Sky and Ethena:

```bash
chainq protocols sky rate                         # Sky Savings Rate (sUSDS) + legacy DSR, onchain
chainq protocols ethena yield                     # sUSDe APY, protocol yield, USDe supply/peg
chainq protocols lido apr                         # stETH staking APR (7d SMA), TVL, wstETH rate
chainq protocols aerodrome stats                  # Base DEX: TVL (AMM+CL), 24h volume, fees, AERO price
chainq protocols aerodrome pools -l 10            # top Aerodrome pools by TVL, fee vs emission APY split
```

Hyperliquid (public data, incl. HIP-3 builder dexs and HIP-4 outcome markets):

```bash
chainq protocols hl price BTC ETH                 # perps: mark price, 24h change, volume, OI, funding
chainq protocols hl markets -s oi                 # top perp markets by volume | oi | funding | change
chainq protocols hl funding                       # most extreme funding rates (hourly + APR)
chainq protocols hl funding BTC --history -D 30    # historical funding: cumulative, mean, APR, range
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

ERC-4626 vault inspector, DeFi positions in portfolio, CEX prices, and more — see [ROADMAP.md](ROADMAP.md).

## Development

```bash
uv sync
uv run pytest                       # unit tests (provider calls are not mocked)
uv run pytest -m live              # live smoke tests: one command per provider against real endpoints
uv run ruff check .
uv run python scripts/gen_changelog.py   # regenerate CHANGELOG.md from conventional commits
```

Release notes live in [CHANGELOG.md](CHANGELOG.md), generated from conventional commit history.

## License

[MIT](LICENSE)
