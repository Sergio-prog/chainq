# Plan 003: Add `chainq yields` — cross-protocol yield comparison in one command

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 7b4fb6f..HEAD -- chainq/commands/ chainq/providers/ skills/chainq/SKILL.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED (aggregates 6+ live providers; failure isolation and honest APY labeling are the risks)
- **Depends on**: `plans/008-kamino-lending.md`
- **Category**: direction
- **Planned at**: commit `7b4fb6f`, 2026-07-10 (refreshed to include Kamino)

## Why this matters

The single most common agent question class — "where's the best yield for X?" — currently requires 4–6 chainq invocations and manual JSON comparison. The repo's own skill file documents the workaround, which is the strongest possible signal the feature is missing: `skills/chainq/SKILL.md` says *"'Where to park stables' questions: compare `sky rate`, `ethena yield`, and lending APYs from aave/morpho"* and *"'Best yield on USDC' type questions: run `protocols aave markets -c usdc` on the relevant networks and compare `supply_apy_pct`"*. Every data source already exists as a provider; this plan adds only the aggregation layer: `chainq yields --asset usdc` returns one ranked table across protocols.

## Current state

All yield sources and their normalized field names (refreshed at `7b4fb6f` — re-verify against the files after Plan 008, they are the source of truth):

| Protocol | Call | APY fields | Where rows are built |
|----------|------|------------|----------------------|
| Aave v3 | `providers.aave.markets(chain_id)` | `supply_apy_pct`, `borrow_apy_pct` built in `chainq/commands/aave.py:25-40` (`_row`) | commands layer |
| Kamino | `providers.kamino.market_configs()` / `.reserve_metrics(market)` | `supply_apy_pct`, `borrow_apy_pct`, `supplied_usd` built by `_reserve_row` in `chainq/commands/kamino.py` after Plan 008 | commands layer |
| Morpho | `providers.morpho.markets(chain_id)` / `.vaults(chain_id)` | `supply_apy_pct`, `net_supply_apy_pct` (markets), vault `apy`/`netApy` — see `chainq/commands/morpho.py:25-45` | commands layer |
| Pendle | `providers.pendle.active_markets(chain_id)` | `implied_apy_pct`, `aggregated_apy_pct` built in `chainq/commands/pendle.py:20-40` | commands layer |
| Sky | `providers.sky.savings()` | `ssr_apy_pct`, `dsr_apy_pct` (provider returns final dict) | provider |
| Ethena | `providers.ethena.yields()` | `susde_apy_pct` | provider |
| Lido | `providers.lido.apr()` | `steth_apr_pct` | provider |
| Curve | `providers.curve.pools(network_key)` | `apy_base_pct`, `apy_crv_min_pct`/`apy_crv_max_pct` | provider |
| Aerodrome | `providers.aerodrome.top_pools(...)` | `apy_pct`, `apy_base_pct`, `apy_reward_pct` (see `chainq/commands/aerodrome.py:61-62`) | provider |

Key structural fact: **Aave, Kamino, Morpho, and Pendle normalize rows in their command files, not their providers.** The row-building helpers (`_row` in aave.py, `_reserve_row` in kamino.py, the market/vault mappers in morpho.py, and the market mapper in pendle.py) must be imported and reused by `yields`, NOT reimplemented. If a helper is module-private, importing it from another command module is fine (same package, existing style tolerates it) — do not copy-paste the mapping.

- `chainq/commands/portfolio.py` — the exemplar for fanning out across sources with `ThreadPoolExecutor` and tolerating per-source failure (read its network sweep before writing the fan-out).
- `chainq/commands/ethena.py` — exemplar thin command shape (`Out`, `out.emit(data, lines, quiet_value, verbose_lines)`).
- `chainq/networks.py` — `resolve_network`; each network has `.chain_id` (Aave/Morpho/Pendle need chain ids, Curve needs the network key).
- Output contract (AGENTS.md, non-negotiable): `--json`, `-q`, `-v`, `--format text|json|table|toon`; default text one line per result; errors → stderr exit 1.
- Conventions: no code comments; `ChainqError` for user-facing errors.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Lint | `uv run ruff check .` | exit 0 |
| Unit tests | `uv run pytest -q` | all pass |
| Live run | `uv run chainq yields ...` | see steps |

## Scope

**In scope**:
- `chainq/commands/yields.py` (create)
- `chainq/cli.py` (register top-level: `app.command()(yields.yields)`)
- Minimal, mechanical exports from `chainq/commands/aave.py` / `kamino.py` / `morpho.py` / `pendle.py` ONLY if a mapper is unusable as-is (e.g. rename `_row` → `row`); no behavior changes to those commands
- `tests/test_yields.py` (create)
- `skills/chainq/SKILL.md`, `README.md`

**Out of scope** (do NOT touch):
- Provider files (`chainq/providers/*`) — consume them as-is
- Hyperliquid/Lighter funding rates — perps funding is not "yield" in this sense; explicitly excluded from v1
- Risk scoring/recommendation logic — present data, never advice

## Git workflow

- Branch: `feat/yields-command`. Do NOT commit or push; leave uncommitted and report.

## Steps

### Step 1: Design the normalized row (do this on paper in the PR description first)

The unified row every source maps into:

```python
{"protocol": "aave", "network": "ethereum", "market": "USDC [Core]", "symbol": "usdc",
 "apy_pct": 4.21, "apy_reward_pct": None, "type": "lending",
 "tvl_usd": 1.2e9, "source": "aave"}
```

`type` is the honesty mechanism — one of `lending` (Aave/Morpho markets supply side), `vault` (Morpho vaults), `staking` (Lido, Ethena, Sky), `lp` (Curve, Aerodrome — carries IL risk), `fixed` (Pendle implied APY to expiry). The text output must show it; the docs must say the types are not directly comparable.

**Verify**: nothing to run; the row shape appears verbatim in the module as the mapping target.

### Step 2: Implement the fan-out

`yields(asset: str | None = --asset/-a, networks: list[str] | None = -n repeatable, kind: str | None = --type, min_tvl: float = --min-tvl 0, limit: int = -l 15, ...contract flags)`.

- Default networks when none passed: `ethereum`, `base`, and `solana` (keeps EVM latency sane while including Kamino); `-n all` unsupported in v1. Only schedule providers compatible with each selected network: Kamino for Solana, EVM lending/DEX providers for their supported EVM chains, and chain-independent staking providers once.
- Fan out one task per compatible (protocol, network) pair with `ThreadPoolExecutor` (pattern: portfolio.py). Each task wraps its call in try/except `Exception` and returns `(rows, error_note)`; failures become `-v` verbose lines (`"morpho ethereum: <error>"`), never a command failure. If ALL sources fail, raise `ChainqError`.
- Asset filter: case-insensitive match against the row's `symbol` and `market` fields. Sky/Ethena/Lido rows carry fixed symbols (`usds`/`dai`, `usde`, `eth`/`steth`) — map them so `--asset usdc` does NOT return sUSDe, but `--asset usde` and `--asset eth` do the right thing.
- Sort by `apy_pct` desc, apply `--min-tvl` and `-l`.
- Text line shape: `4.21%  lending  aave USDC [Core] (ethereum)  tvl $1.2B` — APY first (it's the answer), via `fmt_pct(x, signed=False)` from `chainq/fmt.py`.
- `-q`: top row's `apy_pct`. `--json`/`--format table|toon` come free from `Out` as long as `data` is a list of flat dicts.

**Verify**: `uv run ruff check .` → exit 0; `uv run chainq yields --help` → shows all flags.

### Step 3: Live tests

- `uv run chainq yields` → ranked lines from ≥3 distinct protocols, exit 0
- `uv run chainq yields --asset usdc` → only USDC rows (lending/vault types), including a Kamino/Solana row
- `uv run chainq yields --asset eth -n ethereum` → includes Lido staking row and Aave WETH row
- `uv run chainq yields --type lp` → only Curve/Aerodrome rows
- `uv run chainq yields --json | python3 -m json.tool` → exit 0
- `uv run chainq yields --format toon` → toon table renders
- Cross-check two numbers manually: Aave via `uv run chainq protocols aave markets -c usdc -n ethereum --json` and Kamino via `uv run chainq protocols kamino markets -c usdc --json`; each supply APY must equal its row in `yields --asset usdc --json` from the same run window (small cache-window drift is fine; >0.5pp is a bug).

**Verify**: all commands exit 0; cross-check within tolerance.

### Step 4: Docs — replace the workaround with the feature

- SKILL.md: add a `## Yields (cross-protocol)` section near the stablecoins section; REWRITE the two hand-comparison instructions quoted in "Why this matters" to point at `chainq yields` (grep for `"Where to park stables"` and `"Best yield on USDC"` to find them). State plainly that `type` values are not risk-equivalent.
- README.md: one example in the commands overview.
- ROADMAP.md is out of scope (owner curates it).

**Verify**: `grep -n "yields" skills/chainq/SKILL.md` shows the new section; the two old workaround sentences are gone.

## Test plan

- `tests/test_yields.py` (pure logic only — unit tests never mock providers, repo rule):
  - asset filter: symbol match, market-name match, the sky/ethena/lido fixed-symbol mapping (`--asset usdc` excludes a `usde` row)
  - sorting + `--min-tvl` + limit applied in order
  - a failing source's `(None, error)` result yields a verbose note, not an exception (test the merge function directly)
- Model after `tests/test_output.py` structure.
- Verification: `uv run pytest -q` → all pass.

## Done criteria

- [ ] `uv run ruff check .` exits 0; `uv run pytest -q` exits 0 with new tests
- [ ] `uv run chainq yields --asset usdc` returns rows from ≥3 protocols including Kamino on Solana, ranked by APY, exit 0
- [ ] One protocol failing (unplug test: set `CHAINQ_HTTP_TIMEOUT=0.001`… if that kills all sources, instead verify via the merge-function unit test) does not fail the command
- [ ] Aave and Kamino cross-checks are each within 0.5pp
- [ ] SKILL.md workaround sentences replaced; README example added
- [ ] `git status` shows only in-scope files modified; `plans/README.md` updated

## STOP conditions

Stop and report back if:

- The row-mapping helpers in aave.py/kamino.py/morpho.py/pendle.py cannot be reused without behavior changes to those commands — report what refactor would be needed instead of doing it.
- Field names in the table above don't match the live code (drift) — reconcile from the code, and if a provider's schema changed upstream (live call returns different keys), report it.
- Latency with default networks exceeds ~15s consistently — report; don't silently cut sources.

## Maintenance notes

- Every future APY-bearing protocol integration should add a mapper here; Kamino is included from the first release because Plan 008 is a hard dependency.
- The `type` taxonomy is the contract; adding a new type value is a user-visible change (bump minor version per repo rule — version lives only in `pyproject.toml`).
- Deferred: `-n all` sweep, Aave/Morpho *user position* yields (separate roadmap item "Portfolio depth, part 2"), Hyperliquid funding as pseudo-yield.
