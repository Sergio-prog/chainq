# Plan 009: Add read-only Pump and PumpSwap state under `chainq protocols`

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update this plan's row in
> `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 745a0bb..HEAD -- chainq/solana.py chainq/providers/dexscreener.py chainq/providers/pump.py chainq/providers/uniswap.py chainq/commands/market.py chainq/commands/uniswap.py chainq/commands/pump.py chainq/commands/protocols.py tests/test_pump.py tests/test_solana.py tests/test_live.py README.md ROADMAP.md skills/chainq/SKILL.md site/public/llms.txt site/public/llms-full.txt`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: MED-HIGH (versioned binary account layouts plus third-party discovery)
- **Depends on**: `plans/001-solana-mints-in-price-asset.md`
- **Category**: direction
- **Planned at**: commit `745a0bb`, 2026-07-16 (reconciled after Plan 001)

## Why this matters

Pump tokens move through two distinct onchain phases: a Pump bonding curve and,
after graduation, a PumpSwap constant-product pool. Agents currently need to
know program IDs, derive PDAs, decode Anchor account bytes, and then find the
migrated pool elsewhere. A single read-only protocol surface can answer "what
phase is this mint in, what is its price/state, and where is its PumpSwap pool?"
without introducing signing or trading risk.

This plan intentionally uses official Solana program state as truth. DexScreener
is used only for pool discovery, token labels, and USD/activity enrichment,
matching the repository's source-order rule: official/onchain first, indexer
only for discovery and ranking that raw RPC cannot provide cheaply.

## Current state

- `chainq/solana.py:59-65` already derives Solana PDAs with
  `find_program_address`; `account_data` at lines 191-195 returns raw account
  bytes; `rpc_call` at lines 122-143 handles public-RPC fallback.
- `chainq/solana.py` lacks small wrappers for `getTokenSupply` and
  `getTokenAccountBalance`, both needed to turn raw pool reserves into
  human-scale prices.
- `chainq/providers/uniswap.py:7-62` currently owns generic DexScreener HTTP
  access (`search_pairs`, `token_pairs`, and `_pair_row`) alongside
  Uniswap-specific filtering. `chainq/commands/market.py:14-65` consumes those
  functions through the misleading `uniswap` module name. Completed Plan 001
  added `_token_address_matches`, `_contract_lookup_key`, and
  `_dexscreener_chain_slug` for case-sensitive SPL-mint routing. Keep those
  command-level helpers intact while moving only generic HTTP access to
  `providers/dexscreener.py`.
- `chainq/commands/protocols.py:3-20` mounts protocol apps; no Solana-native
  protocol is mounted.
- Official sources to re-read at execution time:
  - repository and latest IDLs:
    <https://github.com/pump-fun/pump-public-docs>
  - Pump program docs:
    <https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_PROGRAM_README.md>
  - PumpSwap docs:
    <https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_SWAP_README.md>
  - raw Pump IDL:
    <https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/idl/pump.json>
  - raw PumpSwap IDL:
    <https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/idl/pump_amm.json>
- Official program IDs and current account discriminators verified on
  2026-07-10:
  - Pump: `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`
  - PumpSwap: `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`
  - `BondingCurve` discriminator: `[23, 183, 248, 55, 96, 216, 172, 96]`
  - `Pool` discriminator: `[241, 154, 109, 4, 17, 177, 109, 188]`
- Current `BondingCurve` field order after the 8-byte discriminator:
  five `u64` values (`virtual_token_reserves`, `virtual_quote_reserves`,
  `real_token_reserves`, `real_quote_reserves`, `token_total_supply`), `bool`
  `complete`, `pubkey` `creator`, `bool` `is_mayhem_mode`, `bool`
  `is_cashback_coin`, and `pubkey` `quote_mint`. Accounts may contain trailing
  extension bytes; parse the known prefix and ignore trailing data.
- Current PumpSwap `Pool` field order after its discriminator: `u8` pool bump,
  `u16` index, pubkeys `creator`, `base_mint`, `quote_mint`, `lp_mint`,
  `pool_base_token_account`, `pool_quote_token_account`, `u64` LP supply,
  `pubkey` coin creator, `bool` mayhem mode, and `bool` cashback coin.
- Verified stable example from the official PumpSwap docs:
  - mint: `7LSsEoJGhLeZzGvDofTdNg7M3JttxQqGWNLo6vWMpump`
  - derived bonding curve:
    `3MUkKMbuornHohtAtzrToSzqkj1gEEhQqYVz8sZnmQg1`
  - PumpSwap pool: `GseMAnNDvntR5uFePZ51yZBXzNSn7GdFPkfHwfr6d77J`
  - DexScreener returned `chainId=solana`, `dexId=pumpswap`, and that pool
    address; Solana RPC confirmed the curve owner is the Pump program.
- `SOLANA_TOKENS` contains wrapped SOL at
  `So11111111111111111111111111111111111111112`. Older Pump curves can store a
  default/zero quote mint; official docs specify treating those as SOL-paired.
- Repo constraints: no code comments; no SDK/dependency addition without need;
  command flags and clean error behavior are mandatory; all new commands are
  live-tested against real endpoints.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| IDL check | `curl -fsS https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/idl/pump.json` | JSON with Pump address, BondingCurve account/type |
| AMM IDL check | `curl -fsS https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/idl/pump_amm.json` | JSON with PumpSwap address, Pool account/type |
| RPC probe | `uv run chainq rpc getAccountInfo 3MUkKMbuornHohtAtzrToSzqkj1gEEhQqYVz8sZnmQg1 '{"encoding":"base64"}' -n solana` | non-null account owned by Pump |
| Lint | `uv run ruff check .` | exit 0 |
| Tests | `uv run pytest -q` | all tests pass |
| Headless diagnostic | `env -u NO_COLOR TERM=xterm uv run pytest -q` | all pass if host exports `TERM=dumb` |
| Site | `pnpm --dir site build` | exit 0; full reference regenerated |

## Scope

**In scope**:
- `chainq/providers/dexscreener.py` (create)
- `chainq/providers/pump.py` (create)
- `chainq/providers/uniswap.py`
- `chainq/commands/market.py`
- `chainq/commands/uniswap.py`
- `chainq/commands/pump.py` (create)
- `chainq/commands/protocols.py`
- `chainq/solana.py`
- `tests/test_pump.py` (create)
- `tests/test_solana.py`
- `tests/test_live.py`
- `README.md`
- `ROADMAP.md`
- `skills/chainq/SKILL.md`
- `site/public/llms.txt`
- `site/public/llms-full.txt` (generated)

**Out of scope**:
- Buy/sell quotes, slippage, transaction construction, signing, coin creation,
  migration, fee collection, cashback, or any write instruction.
- Trending/top/new token discovery, event indexing, trade history, candles, or
  websocket streaming.
- General Anchor-IDL code generation or a generic Solana account decoder.
- Vendoring the full Pump IDLs into the package; pin only the field prefixes
  and discriminators required for read-only state.
- Pump token metadata beyond labels returned by discovery; do not add a
  Metaplex client in this plan.
- Unofficial Pump APIs or scraping pump.fun pages.

## Git workflow

- Branch: `feat/pump-protocols`
- Conventional commit if explicitly requested later:
  `feat: add Pump and PumpSwap protocol data`
- Do not commit, push, or open a PR without the owner's explicit instruction.

## Steps

### Step 1: Re-run the IDL and live-account spike

Download both official IDLs to temporary files and extract only the program
addresses, account discriminators, and field order for `BondingCurve` and
`Pool`. Re-run the documented mint/curve/pool probes. Confirm:

- the program IDs and discriminators exactly match "Current state";
- the curve is owned by the Pump program and begins with the BondingCurve
  discriminator;
- the pool is owned by PumpSwap and begins with the Pool discriminator;
- DexScreener still identifies the pair as `solana` / `pumpswap`.

Record the observed account byte lengths. Account length may grow, but the
known prefix and discriminator must remain stable.

**Verify**: all four identity checks pass; save no downloaded IDL under the
repository.

### Step 2: Extract the generic DexScreener provider

Create `chainq/providers/dexscreener.py` and move the generic pieces from
`providers/uniswap.py`:

- `SEARCH_URL`, `TOKEN_URL`, and a new pair endpoint base;
- `_get` with cache prefix `dexscreener` and DexScreener-specific errors;
- `token_pairs(address)`, `search_pairs(query)`, and
  `pair(chain_slug, pair_address)`;
- public `pair_row(pair)` containing pair labels, token objects/addresses,
  chain, dex ID, price, change, volume, liquidity, FDV/market cap, pair address,
  and URL.

Leave only Uniswap-specific DefiLlama stats and `uniswap_rows` filtering in
`providers/uniswap.py`; make `uniswap_rows` call `dexscreener.pair_row`.

Update:

- `commands/uniswap.py` to fetch through `dexscreener`, then normalize through
  `uniswap.uniswap_rows`;
- `commands/market.py` to fetch generic token pairs directly through
  `dexscreener`; preserve Plan 001's Solana-aware address matching and chain
  slug helpers unchanged.

Preserve all existing output shapes and cache TTLs. This is a mechanical move,
not a redesign.

**Verify**:

```bash
uv run chainq price 0xdAC17F958D2ee523a2206206994597C13D831ec7 --json
uv run chainq protocols uniswap pools "weth usdc" -n ethereum --json -l 2
```

Both commands exit 0 with the same field shapes as before. `rg -n
"token_pairs|search_pairs" chainq/commands` shows generic calls routed through
`dexscreener`, not `uniswap`.

### Step 3: Add minimal Solana token-amount primitives

In `chainq/solana.py`, add:

- `token_supply(mint: str) -> dict`: call `getTokenSupply`; return
  `raw_amount` as `int` and `decimals` as `int`.
- `token_account_balance(pubkey: str) -> dict`: call
  `getTokenAccountBalance`; return the same normalized keys.

Raise `ChainqError` on a missing/null value with the address in the message.
Do not return floating `uiAmount`; all price math must use integer raw amounts
and explicit decimal scaling.

Add unit tests for response-normalization helpers only if helpers are split
out; do not mock `rpc_call`. The live Pump tests exercise the real methods.

**Verify**: against the documented pool's base and quote token accounts (read
their addresses from the decoded Pool in Step 4), both methods return positive
integer balances and non-negative decimals.

### Step 4: Implement version-checked Pump account decoding

Create `chainq/providers/pump.py`. Keep it focused and below roughly 250 lines;
split only pure binary cursor helpers into a small private class/module if the
file would otherwise become a mixed parser/client god module.

Define program IDs, discriminators, wrapped SOL mint, and zero pubkey. Implement
pure functions:

- `bonding_curve_address(mint)`: PDA from `[b"bonding-curve", mint_bytes]` and
  the Pump program.
- `decode_bonding_curve(data: bytes) -> dict`: validate discriminator and
  minimum known-prefix length; parse little-endian integers, booleans, and
  32-byte pubkeys in the current order; reject invalid bool bytes; ignore
  trailing extension bytes.
- `decode_pool(data: bytes) -> dict`: same discipline for the PumpSwap Pool
  prefix.
- `scaled_amount(raw, decimals)` and `price_from_reserves(...)` using `Decimal`,
  not float.

Implement live wrappers:

- `bonding_curve(mint)`: validate base58 mint, derive/read the curve, verify the
  account owner through `solana.account_info`, decode raw bytes, fetch base and
  quote mint decimals, and return normalized state. Map an all-zero quote mint
  to wrapped SOL. Phase is `bonding-curve` when `complete` is false and
  `graduated` when true.
- `pool(pool_address)`: verify owner, decode Pool, fetch the two stored token
  account balances, and return human reserves plus quote-per-base price.

Return raw integer fields as strings in the final dict if they could exceed
safe JSON integer ranges. Include `source: "solana-rpc"`, program ID, account
address, mint addresses, and flags. Do not calculate a graduation percentage:
the relevant initial reserve configuration can differ by quote mint, and a
misleading percentage is worse than the explicit real/virtual reserves.

**Verify**: a temporary Python invocation decodes the documented curve and
pool; phase is `graduated`, pool base mint equals the documented mint, quote
mint is wrapped SOL, and computed price is positive.

### Step 5: Add the `protocols pump` command group

Create `chainq/commands/pump.py` with one Typer app covering both lifecycle
phases. Implement three commands, each with `--json`, `-q`, `-v`, and
`--format`:

1. `coin <mint>`
   - load authoritative bonding-curve state;
   - fetch DexScreener token pairs and keep `chainId == "solana"` with
     `dexId` in `{"pumpfun", "pumpswap"}`;
   - choose the highest-liquidity matching pair for enrichment;
   - emit phase, onchain quote price/reserves/flags, creator and quote mint,
     plus optional USD price, volume, liquidity, FDV, pair address, and URL;
   - `-q` is USD price when available, otherwise onchain quote price.

2. `pools <mint> --limit/-l 10`
   - discovery-only list of DexScreener pairs filtered to `solana` and
     `pumpswap`, with the mint as base or quote;
   - sort by liquidity descending;
   - state `source: dexscreener` in every row and verbose output;
   - `-q` is newline-separated pool addresses.

3. `pool <pool_address>`
   - load authoritative PumpSwap Pool state and reserves from Solana RPC;
   - optionally enrich labels/USD/activity using the exact DexScreener pair
     endpoint, but never replace onchain base/quote/reserve fields;
   - `-q` is the onchain quote-per-base price.

Text must make provenance and phase obvious, for example:

```text
Figure: graduated to PumpSwap  price 0.000000123 SOL ($0.00001697)
  pool GseM…d77J  liquidity $20.90K  24h volume $...
```

Mount as `protocols pump`; extend the parent help string. Use the official name
"Pump" in help and explain that the group covers PumpSwap too.

**Verify**: `uv run chainq protocols pump --help` lists `coin`, `pools`, and
`pool`; lint passes.

### Step 6: Add pure decoder tests and stable live coverage

Create `tests/test_pump.py` with synthetic binary fixtures built from the field
order pinned in Step 1. Cover:

- deterministic bonding-curve PDA for the documented mint;
- all BondingCurve fields, little-endian parsing, zero quote-mint mapping, and
  trailing-byte tolerance;
- all Pool fields and token-account addresses;
- discriminator mismatch, short data, and invalid boolean rejection;
- reserve price math with differing base/quote decimals and zero reserves;
- DexScreener filtering excludes non-Solana and non-Pump/PumpSwap pairs and
  picks the highest liquidity.

No test fixture should call or mock HTTP/RPC. Add one stable live smoke:

```python
"pump": [
    "protocols", "pump", "coin",
    "7LSsEoJGhLeZzGvDofTdNg7M3JttxQqGWNLo6vWMpump",
]
```

**Verify**: `uv run pytest -q tests/test_pump.py tests/test_solana.py` passes;
`uv run pytest -q -m live -k pump` returns valid JSON with phase `graduated`.

### Step 7: Live-test the full read-only surface

Run:

```bash
uv run chainq protocols pump coin 7LSsEoJGhLeZzGvDofTdNg7M3JttxQqGWNLo6vWMpump
uv run chainq protocols pump coin 7LSsEoJGhLeZzGvDofTdNg7M3JttxQqGWNLo6vWMpump --json
uv run chainq protocols pump pools 7LSsEoJGhLeZzGvDofTdNg7M3JttxQqGWNLo6vWMpump --format table
uv run chainq protocols pump pool GseMAnNDvntR5uFePZ51yZBXzNSn7GdFPkfHwfr6d77J --format toon
uv run chainq protocols pump coin EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
```

The documented Pump mint/pool must work in every mode. USDC must exit 1 with a
clean "not a Pump mint/bonding curve" error, not a decoder traceback. If a
currently active non-graduated Pump mint is available from the official UI or
DexScreener, also run `coin` on it and confirm phase `bonding-curve`; record the
mint in the implementation report but do not hardcode it in tests.

**Verify**: four positive commands exit 0; the negative command exits 1;
onchain pool price is directionally consistent with enrichment after converting
SOL to USD, allowing live-market drift.

### Step 8: Document the read-only boundary and regenerate site references

- `README.md`: add Pump/PumpSwap examples under protocols and state that
  `coin` follows lifecycle while `pool` reads exact onchain AMM reserves.
- `skills/chainq/SKILL.md`: add Pump/PumpSwap to the frontmatter DEX/protocol
  description and a section explaining when to use `coin`, `pools`, and `pool`,
  plus the source/provenance distinction.
- `ROADMAP.md`: add the shipped read-only Pump/PumpSwap surface to Status; do
  not claim trading or trending discovery.
- `site/public/llms.txt`: add the capability to the compact summary.
- Run `pnpm --dir site build` to regenerate `site/public/llms-full.txt`.

No docs may imply that chainq can trade, quote slippage, or recommend tokens.

**Verify**: `rg -ni "pump" README.md ROADMAP.md skills/chainq/SKILL.md site/public/llms*.txt`
shows the intended surfaces; `rg -ni "buy|sell|trade"` around the new docs finds
only explicit statements that writes are unsupported; site build exits 0.

## Test plan

- Pure binary-layout and price-math tests in `tests/test_pump.py`.
- Existing Solana tests remain green after adding token amount wrappers.
- Regression live/manual checks for generic DexScreener consumers (`price` and
  `uniswap pools`).
- Stable Pump live smoke using the official documented migrated mint.
- Manual active-curve check when a non-graduated mint is available.
- Full gates: `uv run ruff check .`, `uv run pytest -q`, and the site build.

## Done criteria

- [ ] Official IDLs still match the pinned program IDs, discriminators, and
  field prefixes.
- [ ] Generic DexScreener code lives in `providers/dexscreener.py`; existing
  market and Uniswap output shapes regress cleanly.
- [ ] Pump/PumpSwap decoders validate owner, discriminator, minimum length,
  booleans, and trailing extensions.
- [ ] `coin`, `pools`, and `pool` implement every required output mode and
  return clean errors for non-Pump accounts.
- [ ] Onchain data is authoritative; DexScreener is labeled as discovery or
  enrichment.
- [ ] `uv run ruff check .` and `uv run pytest -q` pass.
- [ ] Stable live smoke and all Step 7 commands behave as specified.
- [ ] README, skill, roadmap, compact llms, and generated full reference are
  updated within the read-only boundary.
- [ ] `git status --short` contains only in-scope files plus the pre-existing
  untracked media file.
- [ ] `plans/README.md` status row is updated.

## STOP conditions

Stop and report back if:

- Either official program ID or account discriminator changed.
- The latest IDL removed/reordered a pinned prefix field, or multiple live
  account versions require ambiguous decoding.
- The public Solana RPC cannot read the documented curve/pool/token accounts
  reliably enough for zero-setup use.
- DexScreener no longer labels PumpSwap pairs or cannot discover the documented
  pool; do not replace it with an unofficial Pump API or scraper.
- Price direction cannot be established unambiguously from base/quote reserves.
- The feature appears to require signing, SDK transaction builders, event
  indexing, or a new dependency.
- The live Plan 001 helpers differ from the reconciled `745a0bb` versions;
  refresh the extraction around the new helpers instead of overwriting them.

## Maintenance notes

- Pump upgrades frequently add trailing account fields. Prefix parsing plus
  discriminator/owner checks is deliberate; reviewers should reject exact-size
  assertions and silent decoding of unknown discriminators.
- Re-check the official IDLs whenever live smoke fails. Do not "fix" drift by
  guessing offsets from one account.
- DexScreener may report several pools. `pools` is discovery/ranking; `pool`
  verifies any selected address onchain.
- A later trade/quote feature is a separate security-sensitive product decision
  requiring slippage, fee, account, signing, and simulation design. It is not a
  natural extension inside this read-only PR.
- Version bumping remains a release-cut decision; this is a user-visible minor
  feature, but batched plans should update `pyproject.toml` once.
