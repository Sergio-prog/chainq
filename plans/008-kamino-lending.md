# Plan 008: Add Kamino lending markets under `chainq protocols`

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update this plan's row in
> `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 7b4fb6f..HEAD -- chainq/providers/kamino.py chainq/commands/kamino.py chainq/commands/protocols.py chainq/commands/aave.py tests/test_kamino.py tests/test_live.py README.md ROADMAP.md skills/chainq/SKILL.md site/public/llms.txt site/public/llms-full.txt`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED (new upstream API integration; no existing behavior changes)
- **Depends on**: none
- **Category**: direction
- **Planned at**: commit `7b4fb6f`, 2026-07-10
- **Implemented**: branch `feat/kamino-markets`, commit `69dd211`; reviewed and
  verified, not merged into `main`

## Why this matters

Solana is supported across chainq's generic onchain commands, but the dedicated
DeFi protocol surface is almost entirely EVM. Kamino is a major Solana lending
protocol and exposes an official, keyless API with the exact reserve metrics
chainq already presents for Aave and Morpho: supply/borrow APY, supplied and
borrowed USD, utilization, and maximum LTV. A focused lending-markets MVP adds
useful Solana yield data without taking on Kamino's much broader liquidity,
vault, leverage, and transaction surfaces.

## Current state

- `chainq/commands/protocols.py:3-20` imports and mounts every dedicated
  protocol Typer app. There is no Kamino entry.
- `chainq/providers/aave.py:34-50` is the provider pattern to follow: cache by
  request identity, use `chainq.http`, translate `httpx.HTTPError` and HTTP/API
  errors into `ChainqError`, and cache market data for 60 seconds.
- `chainq/commands/aave.py:25-97` is the closest command exemplar. Its public
  row shape is supply/borrow APY, supplied/borrowed/available USD,
  utilization, collateral eligibility, and market label; its command supports
  `--coin`, `--sort`, `--limit`, and all output-contract flags.
- Official API documentation:
  <https://github.com/Kamino-Finance/kamino-api-docs>
  - market discovery: `GET https://api.kamino.finance/kamino-market?programId=<PROGRAM_ID>`
  - reserve metrics: `GET https://api.kamino.finance/kamino-market/<MARKET>/reserves/metrics?env=mainnet-beta`
  - current KLend program ID used by the official docs:
    `KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD`
- Live probes on 2026-07-10 established the current shape:
  - market discovery returned one object with keys `description`, `isPrimary`,
    `lendingMarket`, and `name`; the primary market was
    `7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF`.
  - reserve metrics returned 58 rows with keys `reserve`, `liquidityToken`,
    `liquidityTokenMint`, `maxLtv`, `borrowApy`, `supplyApy`, `totalSupply`,
    `totalBorrow`, `totalBorrowUsd`, and `totalSupplyUsd`.
  - APYs and LTV are decimal fractions (`0.04` means 4%); numeric values arrive
    as strings and must be normalized before sorting or output.
- `chainq/output.py:121-167` automatically provides JSON, table, toon, quiet,
  and verbose rendering when the command emits flat row dictionaries.
- `tests/test_live.py:12-35` has one keyless smoke command per provider. Unit
  tests deliberately do not mock providers; test pure mapping/filtering logic
  offline and cover HTTP only in the live suite.
- `ROADMAP.md:13` prioritizes portfolio depth, but Kamino user obligations are
  raw protocol state with scaled-fraction fields. They are not suitable for a
  quick add-on to this market-data plan.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Market probe | `curl -fsS 'https://api.kamino.finance/kamino-market?programId=KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD'` | JSON array with at least one market |
| Reserve probe | `curl -fsS 'https://api.kamino.finance/kamino-market/7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF/reserves/metrics?env=mainnet-beta'` | JSON array with reserve rows |
| Lint | `uv run ruff check .` | exit 0 |
| Tests | `uv run pytest -q` | all tests pass |
| Headless diagnostic | `env -u NO_COLOR TERM=xterm uv run pytest -q` | all tests pass if host exports `TERM=dumb` |
| Site | `pnpm --dir site build` | exit 0; generated full reference updated |

## Scope

**In scope**:
- `chainq/providers/kamino.py` (create)
- `chainq/commands/kamino.py` (create)
- `chainq/commands/protocols.py`
- `tests/test_kamino.py` (create)
- `tests/test_live.py`
- `README.md`
- `ROADMAP.md`
- `skills/chainq/SKILL.md`
- `site/public/llms.txt`
- `site/public/llms-full.txt` (generated)

**Out of scope**:
- Kamino Liquidity strategies, KVaults, leverage/multiply vaults, farms, Limo,
  staking yield, transaction history, and PnL.
- `protocols kamino positions` and `portfolio --defi` integration. Plan these
  after a reliable normalized current-position endpoint or verified
  scaled-fraction decoder exists.
- Deposits, borrows, repayments, withdrawals, quotes, or transaction building.
- Adding the TypeScript SDK or any Python dependency; the official HTTP API is
  enough for the MVP.
- DefiLlama as a fallback for reserve data; it is less authoritative than the
  official Kamino API.

## Git workflow

- Branch: `feat/kamino-markets`
- Conventional commit if explicitly requested later:
  `feat: add Kamino lending markets`
- Do not commit, push, or open a PR without the owner's explicit instruction.

## Steps

### Step 1: Probe and pin the live response contracts

Run both probes from the command table. Record the market and reserve field
sets in the implementation report. Confirm:

- the API is keyless;
- every market has a base58 `lendingMarket`;
- every reserve has a symbol, mint, APYs, LTV, and USD totals;
- decimal fields are string-encoded fractions.

Do not copy sample values into production constants except the official KLend
program ID. Market addresses must come from discovery so future additional
markets work without a release.

**Verify**: both responses are JSON arrays; at least one market and one reserve
exist; `jq -e '.[0].lendingMarket'` and
`jq -e '.[0] | .liquidityToken and .supplyApy and .totalSupplyUsd'` succeed.

### Step 2: Add the official API provider

Create `chainq/providers/kamino.py`, modeled on `providers/aave.py` and
`providers/pendle.py`, with:

```python
BASE_URL = "https://api.kamino.finance"
KLEND_PROGRAM_ID = "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD"
```

Implement:

- `_get(path: str, params: dict | None = None, ttl: float = 60) -> object`:
  use `cache.key_for("kamino", path, params)`, `http.get`,
  `settings.http_timeout`, and protocol-specific `ChainqError` messages.
- `market_configs() -> list[dict]`: request `/kamino-market` with `programId`;
  require a list response and keep only objects with a valid-looking
  `lendingMarket` string.
- `reserve_metrics(market: str) -> list[dict]`: request
  `/kamino-market/{market}/reserves/metrics` with `env=mainnet-beta`; require a
  list response.

Keep raw API mapping in the provider and user-facing normalization in the
command module, matching the Aave/Pendle architecture. Cache discovery for 300
seconds and reserve metrics for 60 seconds.

**Verify**:

```bash
uv run python -c "from chainq.providers import kamino; ms=kamino.market_configs(); rs=kamino.reserve_metrics(ms[0]['lendingMarket']); print(len(ms), len(rs), rs[0]['liquidityToken'])"
```

The command exits 0 and prints positive market/reserve counts plus a symbol.

### Step 3: Implement the `markets` command

Create `chainq/commands/kamino.py` with
`app = typer.Typer(no_args_is_help=True, help="Kamino lending markets on Solana.")`.

Add a pure `_reserve_row(market: dict, reserve: dict) -> dict | None` that emits:

```python
{
    "market": market["name"],
    "market_address": market["lendingMarket"],
    "symbol": reserve["liquidityToken"],
    "mint": reserve["liquidityTokenMint"],
    "supply_apy_pct": float(reserve["supplyApy"]) * 100,
    "borrow_apy_pct": float(reserve["borrowApy"]) * 100,
    "supplied_usd": float(reserve["totalSupplyUsd"]),
    "borrowed_usd": float(reserve["totalBorrowUsd"]),
    "utilization_pct": borrowed_usd / supplied_usd * 100 if supplied_usd else None,
    "max_ltv_pct": float(reserve["maxLtv"]) * 100,
    "reserve_address": reserve["reserve"],
}
```

Use defensive `.get()` and explicit numeric conversion. Return `None` for a
partial or malformed reserve instead of converting missing values to zero; the
command must count skipped rows and expose that count in verbose output.

Implement `markets` with:

- `--coin/-c`: case-insensitive exact symbol or mint match;
- `--market/-m`: case-insensitive address or name-substring match against the
  discovered configs;
- `--sort/-s`: `supplied | supply-apy | borrow-apy | utilization`, default
  `supplied`;
- `--limit/-l`: default 15; do not apply the limit when an exact coin filter is
  present, matching `commands/aave.py`;
- `--json`, `-q`, `-v`, and `--format` using the shared option aliases.

Fetch reserve metrics for all selected markets. Output JSON as:

```python
{"network": "solana", "total_supplied_usd": total, "reserves": rows}
```

Text starts with a one-line Kamino/Solana total, followed by one line per
reserve: `USDC [Primary market on mainnet]: supply 4.21%  borrow 6.18%  supplied $1.2B  util 72.4%`.
Quiet output is newline-separated symbols. Verbose output includes mint,
reserve address, market address, max LTV, and `source: api.kamino.finance`.

Mount the app as `protocols kamino` and extend the protocol help string.

**Verify**: `uv run ruff check .` exits 0 and
`uv run chainq protocols kamino --help` lists `markets`.

### Step 4: Add offline mapping tests and a live smoke

Create `tests/test_kamino.py`, using a small synthetic API row with string
numbers. Cover:

- APY/LTV fraction-to-percent conversion;
- USD string conversion;
- utilization calculation and zero-supply handling;
- sorting by each key;
- symbol and mint filtering;
- malformed/partial reserve rows return `None`, increment the skipped count,
  and never surface `KeyError`/`TypeError`.

Keep all network calls out of unit tests. Add
`"kamino": ["protocols", "kamino", "markets", "-l", "3"]` to
`tests/test_live.py`.

**Verify**: `uv run pytest -q tests/test_kamino.py` passes and
`uv run pytest -q -m live -k kamino` returns valid JSON with at least one
reserve.

### Step 5: Live-test every output mode

Run:

```bash
uv run chainq protocols kamino markets -l 3
uv run chainq protocols kamino markets -c usdc --json
uv run chainq protocols kamino markets -s supply-apy --format table -l 5
uv run chainq protocols kamino markets -s utilization --format toon -l 5
uv run chainq protocols kamino markets -c definitely-not-a-token
```

Cross-check the USDC APY and supplied USD against the raw official reserve
response from the same run window. The nonsense token must exit 1 with a clean
message on stderr and no traceback.

**Verify**: four successful commands render the expected modes; normalized
values match the API; the error command obeys the output contract.

### Step 6: Document and advertise the supported slice

- `README.md`: add a Kamino subsection/example under protocols, stating this is
  lending reserve data on Solana.
- `skills/chainq/SKILL.md`: add Kamino to the frontmatter lending list and a
  short `## Kamino (Solana lending)` section with markets, coin filter, sort,
  and JSON field guidance.
- `ROADMAP.md`: add Kamino lending markets to Status; do not claim positions,
  liquidity strategies, or vaults shipped.
- `site/public/llms.txt`: add Kamino to the compact capability summary.
- Run `pnpm --dir site build` to regenerate `site/public/llms-full.txt`.

If Plan 003 (`chainq yields`) is still TODO, its executor should consume
Kamino's `_reserve_row` so Kamino supply APYs join cross-protocol comparisons;
do not implement `yields` in this plan.

**Verify**: `rg -ni "kamino" README.md ROADMAP.md skills/chainq/SKILL.md site/public/llms*.txt`
shows all four surfaces; the site build exits 0.

## Test plan

- Offline unit tests in `tests/test_kamino.py` for pure mapping, filtering,
  sorting, percentages, and missing values.
- Provider live smoke in `tests/test_live.py`.
- Manual cross-check of one USDC row against the official API.
- Full gates: `uv run ruff check .` and `uv run pytest -q`.

## Done criteria

- [ ] Official market and reserve probes are still keyless and match the pinned
  field contracts.
- [ ] `protocols kamino markets` supports coin, market, sort, limit, and every
  required output flag.
- [ ] APY, LTV, USD, and utilization values are numerically correct.
- [ ] `uv run ruff check .` and `uv run pytest -q` pass.
- [ ] Kamino live smoke and all manual output-mode commands pass.
- [ ] README, skill, roadmap, compact llms, and generated full reference are
  updated without claiming deferred products.
- [ ] `git status --short` contains only in-scope files plus the pre-existing
  untracked media file.
- [ ] `plans/README.md` status row is updated.

## STOP conditions

Stop and report back if:

- The official API requires authentication, redirects to a private endpoint,
  or no longer exposes current reserve APYs and USD totals.
- The discovery response no longer identifies market addresses, or the reserve
  response no longer identifies token mints.
- APY units cannot be verified as decimal fractions; do not guess whether to
  multiply by 100.
- Completing the market command requires the TypeScript SDK, raw KLend account
  decoding, or a third-party indexer.
- The API returns multiple incompatible market schemas that cannot share one
  normalized row without losing meaning.

## Maintenance notes

- The official API is the source of truth. A future onchain fallback should use
  the official KLend SDK/IDL semantics and be planned separately; do not silently
  switch to DefiLlama.
- Kamino API docs cover many unrelated products. Reviewers should reject scope
  creep into strategies, vaults, PnL, or transactions in this PR.
- The most valuable follow-up is normalized current wallet positions, then
  `portfolio --defi` integration. The live obligations endpoint currently
  returns raw scaled-fraction state, so that follow-up needs its own spike and
  accounting tests.
- Version bumping remains a release-cut decision; if this ships alone it is a
  minor feature, but a batch should update `pyproject.toml` once.
