# Plan 005: Add `chainq protocols uniswap quote` — amount-aware swap quotes

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 4b48de2..HEAD -- chainq/commands/uniswap.py chainq/providers/uniswap_data.py chainq/rpc.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (new curated contract addresses; wrong address = wrong numbers presented confidently)
- **Depends on**: none (plans/002 is unrelated; this uses its own ABI)
- **Category**: direction
- **Planned at**: commit `4b48de2`, 2026-07-07

## Why this matters

`chainq protocols uniswap pool` reports a pool's *mid-price* from `slot0`/reserves — it ignores fee and depth, so nobody can answer "what would 10 ETH actually get me in USDC?". Uniswap's QuoterV2 periphery contract computes exact-in quotes via `eth_call` (read-only, no key), which is precisely the second tier of the repo's stated data-source policy (AGENTS.md: official API → onchain helper/periphery contracts → indexers). This completes the DEX story: discovery (`pools`) → state (`pool`) → executable price (`quote`).

## Current state

- `chainq/commands/uniswap.py` — the command group (`app = typer.Typer(...)` at :24; `pools`, `pool`, `stats` commands). Reusable pieces:
  - `_resolve_pool_token(value, net, native_ok)` (:80-94) — symbol/address → checksummed address via the `TOKENS` registry.
  - `_token_infos(client, net, addresses, memo)` (:97-122) — batch symbol+decimals via multicall.
  - `_sqrt_price(sqrt_price_x96, dec0, dec1)` (:125-126) — mid-price math for the impact comparison.
  - `_onchain_rows(...)` (:144) — how v3 slot0 mid-prices are fetched today; `quote` compares against this.
- `chainq/providers/uniswap_data.py` — ALL static Uniswap data lives here (factories, StateViews, ABIs, fee tiers). New QuoterV2 addresses and the QuoterV2 ABI go in this file. `V3_FACTORIES` covers: ethereum, arbitrum, optimism, polygon, base, bsc, avalanche, unichain, celo — quote should target this same set, minus any network whose quoter you cannot verify.
- `chainq/rpc.py` — `connect`, `encode_call`, `decode_uint`. QuoterV2's quote functions are **not view** (they use revert-state tricks internally) but are designed to be called with `eth_call`; `client.w3.eth.call({"to": ..., "data": ...})` returns their ABI-encoded outputs normally.
- QuoterV2 `quoteExactInputSingle` takes a struct `(address tokenIn, address tokenOut, uint256 amountIn, uint24 fee, uint160 sqrtPriceLimitX96)` and returns `(uint256 amountOut, uint160 sqrtPriceX96After, uint32 initializedTicksCrossed, uint256 gasEstimate)`. Encode the struct as a single `components` tuple in the ABI entry (same style web3 handles for `MULTICALL3_ABI`'s tuple[] in `chainq/rpc.py:52-86`).
- **Addresses must not come from memory** (repo rule: "do not trust remembered addresses"). Canonical source: the Uniswap deployments documentation at `https://docs.uniswap.org/contracts/v3/reference/deployments/` (per-chain pages list "QuoterV2"). Every address gets a live verification step below.
- Conventions: no code comments; `--json`/`-q`/`-v`/`--format` contract; `ChainqError` for errors; checksummed addresses in registries (tests enforce checksums in `tokens.py`/`networks.py` — mirror that by storing checksummed quoter addresses).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Lint | `uv run ruff check .` | exit 0 |
| Unit tests | `uv run pytest -q` | all pass |
| Live run | `uv run chainq protocols uniswap quote ...` | see steps |
| Code check | `uv run chainq rpc eth_getCode <addr> latest -n <net>` | non-`0x` bytecode |

## Scope

**In scope**:
- `chainq/providers/uniswap_data.py` (add `V3_QUOTERS`, `QUOTER_V2_ABI`)
- `chainq/commands/uniswap.py` (add the `quote` command)
- `tests/test_uniswap_quote.py` (create — pure math/encoding tests)
- `skills/chainq/SKILL.md`, `README.md`

**Out of scope** (do NOT touch):
- v4 quoting (different quoter contract and pathing) — record as deferred, reject `-V v4` with a clear error
- v2 quoting — v1 of this feature is v3-only; the constant-product math shortcut is deferred
- Multi-hop paths (`quoteExactInput` with encoded paths) — single-pool quotes only
- Aggregator APIs (0x/1inch) — different data-source tier, separate decision

## Git workflow

- Branch: `feat/uniswap-quote`. Do NOT commit or push; leave uncommitted and report.

## Steps

### Step 1: Collect and verify quoter addresses (the spike)

For each network in `V3_FACTORIES` (list them from the live file):

1. Get the QuoterV2 address from the Uniswap deployments docs page for that chain.
2. Verify bytecode exists: `uv run chainq rpc eth_getCode <addr> latest -n <net>` → long hex string, not `0x`.
3. Functional check (per network, one representative): quote 1 WETH→USDC (or the chain's canonical pair from `chainq/tokens.py`) via a raw `eth_call` and confirm `amountOut` is within ~2% of the `pool` command's mid-price for the same fee tier.

Record the verified set as `V3_QUOTERS = {...}` (checksummed) in `uniswap_data.py`, and the `QUOTER_V2_ABI` with the tuple-input entry from "Current state". Drop (don't guess) any network that fails verification; list dropped networks in your final report.

**Verify**: every address in `V3_QUOTERS` passed both checks; a table of results is in your report.

### Step 2: The `quote` command

```python
@app.command()
def quote(
    amount: Annotated[float, typer.Argument(help="amount of TOKEN_IN to sell")],
    token_in: Annotated[str, typer.Argument(help="token symbol or address")],
    token_out: Annotated[str, typer.Argument(help="token symbol or address")],
    network: ... = "ethereum",
    fee: Annotated[int | None, typer.Option("--fee", help="fee tier; default: best of 100|500|3000|10000")] = None,
    ...contract flags,
):
    """Quote an exact-input swap on Uniswap v3 (fee- and depth-aware, via QuoterV2 onchain)."""
```

- Resolve tokens with `_resolve_pool_token(..., native_ok=False)`; fetch decimals/symbols with `_token_infos`.
- Scale `amount` by token_in decimals (use `Decimal` for the scaling; the repo avoids float wei math — see `chain.py`'s `Decimal` usage).
- One `eth_call` per candidate fee tier (all four when `--fee` absent — sequential is fine, they're single calls; a failed/reverted call means no pool at that tier → skip).
- For each successful tier also compute mid-price from `slot0` (reuse the existing v3 discovery calls from `_onchain_rows`, or a factory `getPool` + `slot0` pair of multicalled reads) and derive `impact_pct = (effective_price / mid_price - 1) * 100` where `effective_price = amount_out / amount_in`.
- Output rows: `{"fee_pct", "amount_in", "amount_out", "effective_price", "mid_price", "impact_pct", "gas_estimate", "pool_version": "v3"}`, sorted by `amount_out` desc.
- Text: `10 WETH → 17,742.11 USDC (0.05% tier, impact -0.12%)` per tier, best first; `-q` prints best `amount_out`.
- Every text output ends with the line `quote only — not a guaranteed execution price` **in `-v` mode only**; in JSON add `"source": "uniswap-quoter-v2"`.
- No pool at any tier → `ChainqError(f"no v3 pool for {token_in}/{token_out} on {net.name}")`.

**Verify**: `uv run ruff check .` → exit 0; `uv run chainq protocols uniswap quote --help` shows the command.

### Step 3: Live tests

- `uv run chainq protocols uniswap quote 1 weth usdc` → amount_out ≈ current ETH price (cross-check `uv run chainq price eth`, within a few %)
- `uv run chainq protocols uniswap quote 1000 usdc weth -n base` → sane inverse
- `uv run chainq protocols uniswap quote 5000 weth usdc --fee 500` vs `--fee 10000` → the 1% tier shows worse or similar effective price (depth check)
- `--json | python3 -m json.tool` → exit 0
- Unknown pair: `... quote 1 weth <random-registry-token-with-no-pool>` → clean error, exit 1

**Verify**: all behave as stated; record the numbers in the report.

## Test plan

- `tests/test_uniswap_quote.py` (offline): decimal scaling (6↔18 decimals both directions), impact computation sign (selling into the pool → negative impact), row sorting. Use synthetic numbers; model file structure on `tests/test_fmt.py`.
- Verification: `uv run pytest -q` → all pass.

## Done criteria

- [ ] `V3_QUOTERS` contains only live-verified checksummed addresses (report includes the verification table)
- [ ] `uv run ruff check .` exits 0; `uv run pytest -q` exits 0 with new tests
- [ ] Live quotes cross-check against `chainq price` within a few percent
- [ ] SKILL.md + README document `quote`, including the not-a-guaranteed-price caveat
- [ ] `git status` shows only in-scope files modified; `plans/README.md` updated

## STOP conditions

Stop and report back if:

- The Uniswap deployments docs are unreachable or no longer list QuoterV2 — do NOT fall back to remembered addresses or third-party lists; report.
- `eth_call` against a verified quoter reverts for a pair that `pool` shows as existing and liquid — the ABI encoding assumption is wrong; report the raw revert.
- Quotes differ from mid-price by >20% on a deep pool (WETH/USDC 0.05% mainnet) — something structural is wrong; do not ship numbers you can't explain.

## Maintenance notes

- Quoter addresses are curated data like `V3_FACTORIES` — when a network is added there, `quote` support requires the same verify-then-add flow, never copy-paste from memory.
- Reviewer: check the decimal scaling on both legs (classic 1e12 bug with USDC/WETH) and that revert-per-tier is treated as "no pool", not an error.
- Deferred: v4 quoter, v2 math, multi-hop `quoteExactInput`, exact-output quotes, aggregator cross-check.
