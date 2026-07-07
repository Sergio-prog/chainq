# Plan 004: Make `chainq tx` answer "what did this transaction do?"

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 4b48de2..HEAD -- chainq/commands/chain.py chainq/providers/ chainq/tokens.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (touches an existing core command; must not break its current output contract)
- **Depends on**: none
- **Category**: direction
- **Planned at**: commit `4b48de2`, 2026-07-07

## Why this matters

Most DeFi transactions carry `value: 0`, so today's `chainq tx` output for a swap or deposit is essentially "0 ETH from A to B: success" — it cannot answer the core agent question "what did this tx do?". The receipt is already fetched and its logs are silently dropped. Decoding ERC-20 `Transfer` events plus naming the called function (via the keyless 4byte.directory API) covers the large majority of real transactions with no API key and no explorer dependency.

## Current state

- `chainq/commands/chain.py:270-345` — the `tx` command (EVM path). Facts that matter:
  - `receipt = client.w3.eth.get_transaction_receipt(tx_hash)` is already fetched (chain.py:~291); `receipt["logs"]` is available and unused.
  - `transaction["input"]` (calldata) is available and unused.
  - Output today: status, from → to, native value + USD, fee + USD, block/time, explorer link. `data` dict keys at chain.py:308-325; text `lines` at chain.py:326-337.
  - Solana txs branch earlier into `_solana_tx` (chain.py:~280-282) — untouched by this plan.
- `chainq/rpc.py` — `multicall(client, calls)` and `encode_erc20("symbol"|"decimals")` for batch token metadata; `decode_uint`, `decode_string` for responses.
- `chainq/tokens.py` — `TOKENS[network_key][symbol] = checksummed address` registry; useful for labeling known tokens without an RPC roundtrip, but metadata should come from multicall so unknown tokens work too.
- `chainq/providers/` pattern — small module with `_get`-style cached HTTP; see `chainq/providers/pendle.py` (30 lines) as the minimal exemplar: `http.get`, `httpx.HTTPError` → `ChainqError`, `cache.key_for`/`cache.get`/`cache.put`.
- `chainq/fmt.py` — `fmt_amount`, `fmt_usd`, `short_addr` for output lines.
- ERC-20 `Transfer(address,address,uint256)` topic0 is `keccak("Transfer(address,address,uint256)")` — compute it with `Web3.keccak(text=...)` at module import rather than hardcoding a remembered hash (repo rule: don't trust remembered constants; computing it makes it correct by construction).
- Conventions: no code comments; `--json`/`-q`/`-v`/`--format` contract must keep working; errors via `ChainqError`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Lint | `uv run ruff check .` | exit 0 |
| Unit tests | `uv run pytest -q` | all pass |
| Live run | `uv run chainq tx <hash> -n <net>` | see steps |

## Scope

**In scope**:
- `chainq/commands/chain.py` (the EVM `tx` function only)
- `chainq/providers/fourbyte.py` (create)
- `tests/test_tx_decode.py` (create — pure decode logic)
- `skills/chainq/SKILL.md`, `README.md` (mention the enriched output)

**Out of scope** (do NOT touch):
- `_solana_tx` and everything Solana
- Full calldata *argument* decoding, internal call traces, NFT (ERC-721/1155) transfers — v2 material
- `chainq/providers/coingecko.py` — reuse `try_price_usd` as the existing code does; no new pricing logic

## Git workflow

- Branch: `feat/tx-decode`. Do NOT commit or push; leave uncommitted and report.

## Steps

### Step 1: 4byte provider

Create `chainq/providers/fourbyte.py` modeled on `chainq/providers/pendle.py`:

```python
BASE_URL = "https://www.4byte.directory/api/v1/signatures/"

def signature(selector: str) -> str | None: ...
```

- `selector` is `0x`-prefixed 4 bytes hex. GET `?hex_signature=<selector>&ordering=created_at`; response JSON has `results: [{"text_signature": "transfer(address,uint256)", ...}]`. Take `results[0]["text_signature"]` (oldest entry — earliest registration is the least likely to be a spoofed collision); `None` on empty results, HTTP error, or timeout (**never raise** — decoding is best-effort garnish; the tx command must work offline from 4byte).
- Cache with `ttl=86400` (selectors are immutable; the repo's 30–300s TTL guidance in AGENTS.md is for market data — a mapping that cannot change is exempt, note this in the PR description, not a code comment).
- **Verify the API shape live before wiring** (repo rule): `uv run python -c "from chainq.providers import fourbyte; print(fourbyte.signature('0xa9059cbb'))"` → `transfer(address,uint256)`.

**Verify**: the one-liner above prints `transfer(address,uint256)`.

### Step 2: Decode transfers from the receipt

In `chain.py`, add a helper `_decode_transfers(client, receipt) -> list[dict]`:

1. Filter `receipt["logs"]` where `log["topics"][0] == TRANSFER_TOPIC` and `len(log["topics"]) == 3` (ERC-721 Transfer has 4 topics incl. indexed tokenId — the length check excludes NFTs).
2. From/to are the last 20 bytes of topics 1 and 2 (`decode_address` from rpc.py works on 32-byte words); amount is `decode_uint(log["data"])` — guard empty data.
3. Batch-fetch `symbol`+`decimals` for the unique token addresses in one `multicall` (pattern: `_token_infos` in `chainq/commands/uniswap.py:97-122`); tokens whose metadata calls fail render as `short_addr(token)` with raw amount.
4. Cap at 10 transfers; when more exist, append a count row (`{"note": "+N more"}` → text `… +N more transfers`).

Return rows: `{"token": addr, "symbol": "USDT", "amount": 500.0, "from": ..., "to": ...}`.

### Step 3: Wire into `tx`

- Function name: when `transaction["input"]` has ≥4 bytes, call `fourbyte.signature(selector)`; fall back to the bare selector string when unresolved.
- Extend `data` with `"function": <sig or selector or None>` and `"token_transfers": [...]` (always present, possibly empty, so `--json` consumers can rely on the key).
- Extend text `lines`, after the value/fee line:
  - `  calls transfer(address,uint256)` (only when input ≥4 bytes)
  - `  transfers:` then one indented line per transfer: `    500 USDT: 0xd8dA…6045 → 0x28C6…21d7` using `fmt_amount` + `short_addr`.
- `-q` still prints only the status (unchanged). `-v` unchanged plus nothing new required.
- Pending txs (no receipt): skip both enrichments cleanly.

**Verify**: `uv run ruff check .` → exit 0; `uv run pytest -q` → pass.

### Step 4: Live tests

Find current hashes yourself (do not reuse remembered ones): `uv run chainq rpc eth_getBlockByNumber latest true -n ethereum` and pick from `transactions`: (a) one with `input == "0x"` (plain ETH send), (b) one whose `input` starts with `0xa9059cbb` (ERC-20 transfer).

- Plain send: output identical in shape to before this change (no `calls`/`transfers` lines beyond the existing ones), exit 0.
- ERC-20 transfer tx: shows `calls transfer(address,uint256)` and one `transfers:` row whose amount/symbol you sanity-check on the explorer link printed by the command.
- Same two with `--json | python3 -m json.tool` → exit 0, `token_transfers` key present in both (empty for the plain send).
- One tx on another network (`-n base`) → exit 0.
- Kill-switch check: temporarily set `BASE_URL` in fourbyte.py to an unreachable host, rerun the ERC-20 tx → command still succeeds showing the raw selector; **revert the edit** afterward (`git diff chainq/providers/fourbyte.py` → clean).

**Verify**: all runs behave as stated.

## Test plan

- `tests/test_tx_decode.py` — pure logic with synthetic log dicts (no network): topic filtering (2-topic and 4-topic logs excluded, 3-topic included), address extraction from 32-byte topics, empty-`data` guard, the 10-transfer cap. Model after `tests/test_rpc.py` for constructing byte fixtures.
- Verification: `uv run pytest -q` → all pass.

## Done criteria

- [ ] `uv run ruff check .` exits 0; `uv run pytest -q` exits 0 with new decode tests
- [ ] Live ERC-20 transfer tx shows function name + decoded transfer row
- [ ] Plain ETH send output has no new noise; `--json` gains `token_transfers: []`
- [ ] 4byte unreachable → command still succeeds (selector shown raw)
- [ ] `git status` shows only in-scope files modified; `plans/README.md` updated

## STOP conditions

Stop and report back if:

- 4byte.directory's response shape differs from Step 1's description (verify live first — if the API is gone or now requires a key, report; do not swap in a different service unilaterally).
- `receipt["logs"]` from web3 doesn't expose `topics`/`data` as bytes in the pinned web3 version — report the actual types before adapting.
- The `tx` function has drifted from the excerpt locations (chain.py:270-345).

## Maintenance notes

- Selector collisions are real: the function line is best-effort labeling, never load-bearing — reviewers should reject any future logic that *branches* on the 4byte name.
- Adding ERC-721/1155 support later = relax the 3-topic filter + tokenId decoding; the cap and multicall metadata batch already generalize.
- If a `chainq read`-style ABI layer lands (plans/002), revisit argument decoding for the top ~20 selectors.
