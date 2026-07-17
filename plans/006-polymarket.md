# Plan 006: Add Polymarket under `chainq protocols` — complete the prediction-markets category

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat d3e341e..HEAD -- chainq/commands/protocols.py chainq/providers/ chainq/commands/hl.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: M
- **Risk**: LOW-MED (new integration, no existing behavior changes; risk is upstream API shape drift)
- **Depends on**: none
- **Category**: direction
- **Planned at**: commit `d3e341e`, 2026-07-16 (reconciled; finding still present)

## Why this matters

chainq's skill description advertises "prediction markets", but coverage is only Hyperliquid's HIP-4 outcome markets (`chainq protocols hl outcomes`) — a small market set. Polymarket dominates the category and its Gamma API is official and keyless, i.e. the first tier of the repo's data-source policy (AGENTS.md: official API → onchain → indexers). "What are the odds of X?" is a growing agent query class chainq currently barely answers.

This is a deliberate category expansion beyond DeFi-native data — the maintainer has accepted that trade-off by selecting this plan.

## Current state

- `chainq/commands/protocols.py` — protocol subcommands mount here:

  ```python
  # protocols.py:9-20
  app.add_typer(hl.app, name="hl")
  app.add_typer(aave.app, name="aave")
  ...
  ```

  Add `app.add_typer(polymarket.app, name="polymarket")` and extend the help string at protocols.py:7.
- `chainq/providers/pendle.py` (~30 lines) — the minimal provider exemplar: `http.get` (from `chainq/http.py`, has retry/backoff), `httpx.HTTPError` → `ChainqError`, `cache.key_for`/`get`/`put` (TTL 30–300s for market data), `settings.http_timeout`.
- `chainq/commands/hl.py` — the closest command-layer exemplar (its `outcomes` command renders prediction markets; match its vocabulary: outcome, probability/price, volume, resolution).
- `chainq/commands/ethena.py` — minimal command file shape (`Out`, `out.emit(data, lines, quiet_value, verbose_lines)`).
- Output contract (non-negotiable): `--json` / `-q` / `-v` / `--format text|json|table|toon`; one human-readable line per result; errors → stderr, exit 1.
- Conventions: no code comments; a new command ships with a SKILL.md entry and a README example; live-test every command against real endpoints before finishing.
- Polymarket API (verify live in Step 1 — do not trust this from memory): Gamma API base `https://gamma-api.polymarket.com`; `/markets` and `/events` endpoints with query params for active/closed, ordering, and text search. Prices come back as outcome prices in [0,1] — an outcome price IS the implied probability.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Lint | `uv run ruff check .` | exit 0 |
| Unit tests | `uv run pytest -q` | all pass |
| Live run | `uv run chainq protocols polymarket ...` | see steps |
| API probe | `curl -s "https://gamma-api.polymarket.com/markets?limit=2&active=true&closed=false"` | JSON array of markets |

## Scope

**In scope**:
- `chainq/providers/polymarket.py` (create)
- `chainq/commands/polymarket.py` (create)
- `chainq/commands/protocols.py` (mount + help string)
- `tests/test_polymarket.py` (create — pure mapping logic)
- `skills/chainq/SKILL.md`, `README.md`

**Out of scope** (do NOT touch):
- `chainq/commands/hl.py` — HL outcomes stay as they are; no unification layer in v1
- Order books / CLOB API, user positions, historical price series — v2 material
- Any API-key-gated Polymarket surface

## Git workflow

- Branch: `feat/polymarket`. Do NOT commit or push; leave uncommitted and report.

## Steps

### Step 1: Probe the live API and pin the shape (the spike)

Run the curl probe above plus a search variant. Record in your report: the exact field names for question/title, slug, outcomes, outcome prices, 24h/total volume, liquidity, end date, and whether prices arrive as stringified JSON arrays (Gamma is known for `outcomes` / `outcomePrices` being JSON-encoded strings inside JSON — confirm and handle). Pin the 3–5 fields the provider will map. If the endpoints 404 or require auth, STOP.

**Verify**: probe returns market objects; field list recorded.

### Step 2: Provider

`chainq/providers/polymarket.py`, modeled on pendle.py:

- `_get(path, params, ttl=60)` with the standard cache/error wrapper (name the cache key prefix `polymarket`).
- `markets(query: str | None, limit: int) -> list[dict]` — active markets, ordered by volume (use the ordering param confirmed in Step 1; when `query` is set use the search param confirmed in Step 1).
- `market(slug_or_id: str) -> dict | None` — single market lookup.
- Normalize each market to: `{"question", "slug", "outcomes": [{"name", "probability_pct"}], "volume_24h_usd", "liquidity_usd", "end_date", "url"}` (url: `https://polymarket.com/market/<slug>`). Parse the stringified arrays here so the command layer sees clean lists.

**Verify**: `uv run python -c "from chainq.providers import polymarket; ms = polymarket.markets(None, 3); print(len(ms), ms[0]['question'], ms[0]['outcomes'][0])"` → 3 markets with parsed outcomes.

### Step 3: Commands

`chainq/commands/polymarket.py` with `app = typer.Typer(no_args_is_help=True, help="Polymarket prediction markets: odds, volume, resolution dates.")`:

- `markets [QUERY] -l 10` — top active markets by volume, optional text search. Text line: `Will X happen by June? — Yes 62.0% / No 38.0%  vol $1.2M  ends 2026-08-01`. Quiet: slugs.
- `market <slug-or-id>` — one market in detail (all outcomes, liquidity, end date, url). Quiet: top outcome's probability.

Mount in `protocols.py`; extend its help string to include Polymarket.

**Verify**: `uv run ruff check .` → exit 0; `uv run chainq protocols polymarket --help` shows both commands.

### Step 4: Live tests

- `uv run chainq protocols polymarket markets` → 10 lines, probabilities sum ≈ 100% per binary market
- `uv run chainq protocols polymarket markets "bitcoin"` → bitcoin-related markets
- `uv run chainq protocols polymarket market <slug from previous output>` → detail view, exit 0
- `--json | python3 -m json.tool` and `--format toon` on `markets` → exit 0
- Nonsense slug → clean `ChainqError`, exit 1

**Verify**: all behave as stated.

### Step 5: Docs

- SKILL.md: add Polymarket to the frontmatter description's prediction-markets clause and a `## Polymarket` section with 2–3 examples ("odds of X" phrasing — that's the agent trigger).
- README.md: one example line.

**Verify**: `grep -in "polymarket" skills/chainq/SKILL.md README.md` → hits in both.

## Test plan

- `tests/test_polymarket.py` (offline, pure mapping): stringified `outcomes`/`outcomePrices` parsing into the normalized shape, probability_pct scaling, malformed/missing fields → row skipped not crash. Feed synthetic dicts copied from the Step 1 probe (scrub nothing — it's public data). Model on `tests/test_solana.py` style.
- Verification: `uv run pytest -q` → all pass.

## Done criteria

- [ ] `uv run ruff check .` exits 0; `uv run pytest -q` exits 0 with new mapping tests
- [ ] All Step 4 live commands behave as stated
- [ ] SKILL.md frontmatter + section and README updated
- [ ] `git status` shows only in-scope files modified; `plans/README.md` updated

## STOP conditions

Stop and report back if:

- The Gamma API requires authentication, is geo-blocked from your environment, or the `/markets` shape has no outcome-price data — report the observed responses; do not switch to scraping or an unofficial mirror.
- Probabilities in the response are not interpretable as [0,1] prices (e.g. only order-book data available) — the normalization assumption fails; report.

## Maintenance notes

- Upstream shape drift is the main risk — this integration belongs in the live smoke-test suite (`pytest -m live`); add one live test if the suite's pattern (see `tests/test_live.py`) makes it a one-liner, otherwise note it for the owner.
- If HL outcomes and Polymarket ever need a unified `chainq odds <query>` front door, both command layers already normalize to name+probability — that's the seam.
- Deferred: CLOB/order-book depth, historical odds series, event grouping (Gamma `/events`).
