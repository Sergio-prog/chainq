# Plan 001: Accept SPL mint addresses in `chainq price` and `chainq asset`

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 4b48de2..HEAD -- chainq/providers/coingecko.py chainq/providers/coingecko_data.py chainq/commands/market.py chainq/solana.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: direction
- **Planned at**: commit `4b48de2`, 2026-07-07

## Why this matters

chainq v0.13 shipped Solana support in `balance`, `portfolio`, `address`, `tx`, and `gas`, but the market-data commands stayed EVM-only: `chainq price <SPL mint>` fails because address detection only recognizes `0x…` strings. An agent that just swept a Solana portfolio and got back mint addresses cannot price them. Both data paths already support Solana — CoinGecko's contract endpoint has a `solana` platform (already present in `PLATFORM_IDS`) and DexScreener (already the token locator) indexes Solana pairs — so this is closing a seam, not building a feature.

## Current state

- `chainq/providers/coingecko.py` — CoinGecko HTTP client. Address detection is EVM-only:

  ```python
  # coingecko.py:99
  def is_address(query: str) -> bool:
      return query.startswith("0x") and len(query) == 42
  ```

  Contract lookup lowercases the address — correct for EVM, **corrupts case-sensitive base58 mints**:

  ```python
  # coingecko.py:103-112
  def by_contract(address: str, network_key: str | None = None) -> dict | None:
      keys = (network_key,) if network_key else CONTRACT_LOOKUP_ORDER
      for key in keys:
          platform = PLATFORM_IDS.get(key)
          if platform is None:
              continue
          result = _get(f"/coins/{platform}/contract/{address.lower()}", ttl=300, none_on_404=True)
  ```

- `chainq/providers/coingecko_data.py` — static maps. `PLATFORM_IDS` already contains `"solana": "solana"`. `CONTRACT_LOOKUP_ORDER` is EVM-only (`("ethereum", "base", ..., "hyperevm")`) — correct to leave as-is; mints will pass `network_key="solana"` explicitly.
- `chainq/commands/market.py` — `price`/`asset`/`candles` commands. Routing happens via `coingecko.is_address(query)` at `market.py:119`, `market.py:231`, and `_resolve_coin_id` at `market.py:55-61`. `_locate_contract` (market.py:43-52) combines a DexScreener best-pair lookup with the CoinGecko contract lookup. DexScreener side: `_dexscreener_best_pair` (market.py:15-24) filters `uniswap.token_pairs(address)` by `chainId`; for Solana the DexScreener `chainId` value is `solana`.
- `chainq/solana.py:95-98` — existing base58 pubkey detector, already used for routing in `portfolio.py:178`:

  ```python
  def looks_like_solana(value: str) -> bool:
      try:
          return len(base58_decode(value)) == 32
      except ValueError:
          return False
  ```

- Known SPL mints for live testing live in the `SOLANA_TOKENS` dict in `chainq/tokens.py` (symbols: usdc, usdt, jup, bonk, wif, msol, jitosol). Read that file for real mint values — do not invent mints.
- Conventions: **no code comments** (self-explanatory code only); every command keeps the `--json` / `-q` / `-v` / `--format` contract; errors raise `ChainqError` (chainq/errors.py); providers cache via `chainq/cache.py`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Lint | `uv run ruff check .` | exit 0, "All checks passed!" |
| Unit tests | `uv run pytest -q` | all pass |
| Live run | `uv run chainq <args>` | see per-step expectations |

## Scope

**In scope** (the only files you should modify):
- `chainq/providers/coingecko.py`
- `chainq/commands/market.py`
- `tests/test_tokens.py` or a new `tests/test_market_routing.py` (pure-function tests only)
- `skills/chainq/SKILL.md` (usage note), `README.md` (only if it documents `price` by address)

**Out of scope** (do NOT touch):
- `chainq/solana.py` — `looks_like_solana` is used by portfolio/balance routing; do not change its behavior.
- `chainq/providers/coingecko_data.py` — `CONTRACT_LOOKUP_ORDER` stays EVM-only.
- `chainq/commands/portfolio.py` — long-tail Solana portfolio pricing is a separate roadmap item.
- Historical paths (`price --at`, `candles`) beyond what falls out naturally from `_resolve_coin_id`.

## Git workflow

- Branch: `feat/solana-mints-price` (conventional branches; repo commits look like `feat: resolve .sol domains via Solana Name Service`).
- Do NOT commit or push — the repo rule (AGENTS.md) is that only the owner asks for commits. Leave the work uncommitted and report.

## Steps

### Step 1: Teach the provider about mints

In `chainq/providers/coingecko.py`:
1. Import `looks_like_solana` from `chainq.solana` and add:
   ```python
   def is_solana_mint(query: str) -> bool:
       return not query.startswith("0x") and looks_like_solana(query)
   ```
2. In `by_contract`, preserve case for Solana: replace `address.lower()` with a variable computed once — `address.lower()` when `platform != "solana"`, `address` unchanged otherwise.

Check for circular imports: `chainq/solana.py` must not import from `chainq.providers`. Run `uv run python -c "import chainq.providers.coingecko"` → exit 0.

**Verify**: `uv run ruff check .` → exit 0.

### Step 2: Route mints in market commands

In `chainq/commands/market.py`:
1. Everywhere the code branches on `coingecko.is_address(query)` (`price` at :119, `asset` at :231, `_resolve_coin_id` at :55), extend the branch to also accept `coingecko.is_solana_mint(query)`.
2. In `_locate_contract` (market.py:43), when the query is a mint, force `lookup_key = "solana"` (skip the EVM `SLUG_TO_NETWORK` inference; DexScreener `chainId` for Solana pairs is the string `solana`).
3. In `_dexscreener_best_pair` (market.py:15), the `p["baseToken"]["address"].lower() == address.lower()` comparison is fine for EVM but must compare case-sensitively for mints — compare exactly when the query is a mint.

**Verify**: `uv run ruff check .` → exit 0; `uv run pytest -q` → all pass.

### Step 3: Live-test against real endpoints

Read `SOLANA_TOKENS` in `chainq/tokens.py` and pick the `jup` mint. Then:

- `uv run chainq price <JUP_MINT>` → one line with a plausible JUP price (compare magnitude with `uv run chainq price jup`).
- `uv run chainq asset <JUP_MINT>` → full profile lines (rank, price, mcap).
- `uv run chainq price <JUP_MINT> --json` → valid JSON (`| python3 -m json.tool` exits 0) containing `"source"`.
- `uv run chainq price 0xdAC17F958D2ee523a2206206994597C13D831ec7` → USDT ≈ $1.00 (EVM regression).
- `uv run chainq price bitcoin eth` → unchanged behavior for symbols.

**Verify**: all five commands exit 0 with sensible output.

### Step 4: Docs

Add one line to `skills/chainq/SKILL.md` in the Market data section, e.g. `chainq price <SPL mint>  # Solana mints work like contract addresses`, and extend the "Contract addresses work everywhere" paragraph to mention Solana mints. Match the file's existing terse style.

**Verify**: `grep -n "mint" skills/chainq/SKILL.md` → shows the new lines.

## Test plan

- Pure-function unit tests (no network — repo unit tests never mock providers, so only test offline logic):
  - `is_solana_mint("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")` is True (USDC mint, 32-byte base58)
  - `is_solana_mint("0xdAC17F958D2ee523a2206206994597C13D831ec7")` is False
  - `is_solana_mint("bitcoin")` is False, `is_address("bitcoin")` is False
- Model the test file after `tests/test_tokens.py` (plain asserts, no fixtures).
- Verification: `uv run pytest -q` → all pass including new tests.

## Done criteria

- [ ] `uv run ruff check .` exits 0
- [ ] `uv run pytest -q` exits 0 with new mint-detection tests
- [ ] `uv run chainq price <JUP mint from tokens.py>` prints a priced line, exit 0
- [ ] `uv run chainq price 0xdAC17F958D2ee523a2206206994597C13D831ec7` still works
- [ ] `git status` shows only in-scope files modified
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- CoinGecko `/coins/solana/contract/<mint>` returns 404 for well-known mints like JUP — the platform id assumption is wrong; report the observed response.
- DexScreener `latest/dex/tokens/<mint>` returns no Solana pairs for JUP — the fallback path assumption is wrong.
- `looks_like_solana` returns True for any plain CoinGecko id used in `tests/` (would break symbol routing).
- The excerpts in "Current state" don't match the live code.

## Maintenance notes

- The roadmap's "Solana portfolio pricing for long-tail mints (DexScreener batch lookup)" should reuse `is_solana_mint` and the case-preservation rule from this plan.
- Reviewer: scrutinize every `.lower()` on the query path — one missed lowercase silently breaks mint lookups (404s), it doesn't error.
- Deferred: `candles <mint>` works only for CoinGecko-listed mints (inherits `_resolve_coin_id`); DexScreener-only tokens still have no candles — acceptable, matches EVM behavior.
