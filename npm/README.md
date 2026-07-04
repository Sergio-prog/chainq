# chainq (npm launcher)

Agent-friendly CLI for onchain and crypto market data: prices, balances, gas, transactions, raw RPC on 25 EVM networks, Aave/Morpho/Uniswap/Pendle/Sky/Ethena, Hyperliquid, Lighter, NFT floors, stablecoins, DefiLlama.

This package is a thin launcher: it runs the [Python CLI](https://github.com/Sergio-prog/chainq) pinned to the same version via `uvx` (or `pipx run`). It needs [uv](https://docs.astral.sh/uv/) or pipx on your PATH.

```bash
npx chainq price eth btc
npx chainq portfolio vitalik.eth
npx chainq gas -n base
```

For a permanent install, prefer the native route:

```bash
curl -fsSL https://raw.githubusercontent.com/Sergio-prog/chainq/main/install.sh | sh
```

Full docs and the agent skill: https://github.com/Sergio-prog/chainq
