# Onchain (EVM and Solana)

Networks: ethereum, arbitrum, base, optimism, polygon, bsc, avalanche, gnosis, unichain, linea, scroll, zksync, mantle, blast, sonic, berachain, worldchain, ink, soneium, celo, sei, hyperevm, monad, plasma, katana, robinhood, arc, and solana. `-n` also takes aliases (eth, arb, op, matic, bnb, avax, hype, rh, sol) and chain ids.

## Balances and portfolios

```bash
chainq balance vitalik.eth                         # native balance; ENS and .sol names resolve
chainq balance 0x... --coin usdt -n arbitrum       # token by symbol, or pass the contract address
chainq portfolio vitalik.eth                       # every network: native + every catalog token, USD total
chainq portfolio 0x... -n ethereum -n base --min-usd 10
chainq portfolio 0x... --all                       # include unpriced tokens and dust
chainq portfolio 0x... --defi                      # add Hyperliquid and Lighter equity and spot balances
chainq portfolio 0xA.. 0xB.. 0xC..                 # many wallets: wallet x network USD matrix
chainq portfolio -F wallets.txt --by total         # addresses from a file (one per line, commas ok; - is stdin)
chainq portfolio -F wallets.txt --by token --json  # one row per wallet and token
chainq portfolio --paste --by total                # addresses from the clipboard
```

- `portfolio` is the answer to "what's in this wallet" and "net worth". `total_usd` is in `--json`. Use `balance` for one token on one network.
- Multi-wallet views: `--by network` (default), `total`, or `token`. Order wallets with `-s balance|input|address`; `--short` abbreviates addresses.
- It sweeps the token catalog (thousands of tokens per network) with Multicall3, so holdings outside a curated list are found. Only catalog tokens are swept, which keeps airdrop spam out.
- Prices come from CoinGecko, then DefiLlama or Jupiter, then Pendle, then DexScreener with a $1k liquidity floor. Each asset carries `price_source` and `kind` (`token`, `atoken`, `stata`, `pt`, `yt`, `sy`, `lp`).
- Unpriced assets and assets below `--min-usd` (default $1) are hidden and counted in `hidden_assets`.
- Results are cached for 5 minutes per wallet and network; `--no-cache` rescans. A scan priced during a source outage is not cached.

## Token catalog

```bash
chainq tokens search cat -n base   # symbol or name; curated and exact matches come first
chainq tokens status               # catalog size, sources, cache age per network
chainq tokens refresh -n base      # re-download the lists (they refresh daily)
```

Symbols resolve against a curated registry first (so `usdc` is always the canonical USDC), then the catalog: CoinGecko per-network lists, Aave aTokens and stata tokens, Pendle PT/YT/SY/LP, and Jupiter-verified Solana mints. A symbol with several matches errors and lists the candidates; pass the address instead. Any ERC-20 or SPL mint works by address. If the lists cannot be downloaded, everything falls back to the curated registry.

## Address intelligence

```bash
chainq address 0xADDR -n base
chainq address 9WzDX...            # Solana: wallet vs program, owner program, token accounts
```

On EVM it reports EOA vs contract (with EIP-7702 delegation), proxy implementation (EIP-1967, EIP-1167, ZeppelinOS), the ERC-20 profile, tx count, native and catalog holdings with USD values (`holdings_hidden` counts unpriced ones), reverse ENS on ethereum, and an explorer link. Run it before interacting with an unknown address.

## Gas, transactions, RPC

```bash
chainq gas -n base                        # gas price, base fee, transfer cost in USD
chainq tx 0xHASH -n ethereum              # status, parties, value, fee, block, decoded ERC-20 transfers, called function
chainq tx 5UfDuX94A1Qfq...                # Solana signature: status, signer, fee, slot
chainq rpc eth_blockNumber -n optimism    # raw JSON-RPC; prints the JSON result
chainq rpc eth_getBlockByNumber latest false
chainq rpc getSlot -n solana
```

- For "is it a good time to transact", quote the transfer cost from `gas`.
- For "did my tx go through", check `status` and give the explorer link from `tx -v`.
- `rpc` parses params that are JSON literals and passes the rest as strings. Use it for anything chainq has no command for.

## EVM utilities

`chainq schema evm` prints the usage of each one:

- Chain state: `block-number`, `block`, `find-block`, `client`, `chain-id`, `nonce`, `code`, `storage`, `call`, `estimate`.
- Encoding and hashing: `abi-encode`, `abi-decode`, `sig`, `sig-event`, `keccak`, `hash-message`, `hash-zero`, `namehash`, `checksum`.
- Bytes and numbers: `to-hex`, `to-dec`, `to-wei`, `from-wei`, `shl`, `shr`, `to-bytes32`, `format-bytes32-string`, `parse-bytes32-string`, `parse-bytes32-address`, `from-utf8`, `to-utf8`, `max-int`, `min-int`, `max-uint`.

```bash
chainq evm sig 'transfer(address,uint256)'
chainq evm call 0xToken 'balanceOf(address)' '["0xHolder"]' --returns uint256 -n base
chainq evm abi-decode 'address,uint256' 0x...
```

## Time travel

`evm call`, `evm storage`, `evm code`, `evm nonce`, and `balance` take `--at <time>` (ISO-8601, Unix seconds, or `3d ago`). They read state at the last block at or before that time. `evm find-block <time>` returns the closest block plus `at_or_before`. The block lookup is a batched interpolation search over headers, cached per chain, and usually takes 150–400 ms. Old state needs an archive RPC. Most networks have a public one and chainq fails over to it. Arbitrum, Blast, and Robinhood don't, so set `CHAINQ_RPC_<NETWORK>` there. `balance --at` omits USD values.

```bash
chainq evm call 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 'totalSupply()' --returns uint256 --at 2023-01-01
chainq balance vitalik.eth -c usdc --at "2024-06-01 12:00"
chainq evm find-block "7d ago" -n base -q
```
