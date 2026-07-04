# AGENTS.md

chainq is an agent-first CLI for onchain and crypto market data. Python 3.12+, uv, Typer, httpx, web3.py. Vision and priorities live in [ROADMAP.md](ROADMAP.md) — keep it in sync when shipping features.

## Rules

- No code comments; code must be self-explanatory.
- Conventional commits, branches, and PR titles. Never commit, push, or open a PR without the owner's explicit ask.
- Before any commit: `uv run ruff check .` and `uv run pytest -q` must pass.
- Live-test every new or changed command against real endpoints (`uv run chainq ...`) — unit tests deliberately don't mock providers.
- Version is defined only in `pyproject.toml` (read at runtime via importlib.metadata). Bump semver on user-visible changes.
- `.env` holds real keys and is gitignored; never commit it, never print its values.
- Data sources, in order of preference: the protocol's official API (Aave GraphQL, Pendle, Hyperliquid/Lighter info APIs) → onchain helper/periphery contracts (most protocols deploy them — e.g. Uniswap v3 factory/pool, Aave UiPoolDataProvider) → third-party indexers (DexScreener, DefiLlama) only for discovery/ranking that the first two can't do. Verify new RPC endpoints and API shapes live before shipping (`eth_chainId`, sample responses) — do not trust remembered addresses or schemas.

## Output contract (do not break)

- Every query command supports `--json`, `-q`, `-v`, and `--format text|json|table|toon`; default text is one human-readable line per result.
- Errors go to stderr with exit code 1; stdout stays clean for parsing.
- A new command ships with: the contract flags above, an entry in `skills/chainq/SKILL.md`, and a README example.

## Architecture

- `chainq/cli.py` registers commands; `chainq/commands/*` are thin Typer layers; protocol commands (aave, hl) mount under the `protocols` group.
- `chainq/providers/*` are HTTP clients (CoinGecko, Hyperliquid, Aave GraphQL) using `chainq/cache.py` (TTL 30–300s, `~/.cache/chainq/`).
- `chainq/networks.py` and `chainq/tokens.py` are curated registries (checksummed addresses — tests enforce); `chainq/rpc.py` wraps web3 with RPC fallback; `chainq/output.py` owns all formatting.
- `chainq/update.py` — self-update + once-daily version reminder (disable via `CHAINQ_NO_UPDATE_CHECK`).

## Important files

- `ROADMAP.md` — vision, shipped versions, what to build next.
- `skills/chainq/SKILL.md` — the agent skill, primary distribution channel; update on any command change.
- `install.sh` — public installer (PyPI-first via uv/pipx, git fallback).
