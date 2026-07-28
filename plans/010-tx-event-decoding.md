# Plan 010: Make `chainq tx` name the action — swaps, approvals, lending, vaults, wraps

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat ec93976..HEAD -- chainq/commands/chain.py chainq/evm.py chainq/rpc.py chainq/providers/fourbyte.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: MED (extends a core command's output; the baseline tx readout must survive every decoder failure)
- **Depends on**: plans/004-tx-decode.md (merged via PR #6, in `main` at `ec93976`)
- **Category**: direction
- **Planned at**: commit `ec93976`, 2026-07-28
- **Status**: TODO

## Why this matters

Plan 004 answered "which tokens moved". It did not answer "what did this
transaction *do*". Three real mainnet transactions, run against `main` at
`ec93976` on 2026-07-28, show the exact gap:

```
$ chainq tx 0x8267e2a62909efc1fd394d146e7a5408b1468a23a598661f93efe894f417e630
  calls swap((uint8,address,address,address,uint24,int24,address,bytes)[],address,uint256,uint256,uint256)
  transfers:
    3,024,572.95 GOD: 0x18a2…5810 → 0x0000…8A90
```

A Uniswap v4 swap renders as a one-way token dump into an unnamed address. The
ETH leg is invisible (v4 settles natively through flash accounting, so there is
no `Transfer` log for it), and nothing says "swap".

```
$ chainq tx 0x8539701a7c29df5d44d3bba265ace0ea79b403839dc07db37e603ce390153349
  calls execTransaction(address,uint256,bytes,uint8,uint256,uint256,uint256,address,address,bytes)
```

The 4byte name is the only signal that this is a multisig execution, and 4byte
is explicitly best-effort garnish that plan 004's own maintenance notes forbid
branching on.

The fix is a topic0-keyed event registry. Every event in this plan was verified
live against Ethereum mainnet logs on 2026-07-28 (hit counts and emitters are
recorded in Step 1), so the executor is not decoding from memory.

## Current state

- `chainq/commands/chain.py:30` — one hardcoded topic, computed correctly by
  construction rather than pasted:

  ```python
  TRANSFER_TOPIC = Web3.keccak(text="Transfer(address,address,uint256)")
  ```

- `chainq/commands/chain.py:298-325` — `_decode_transfers(client, receipt)`.
  Filters `len(log["topics"]) == 3 and log["topics"][0] == TRANSFER_TOPIC`,
  caps at 10, appends `{"note": "+N more"}`, and wraps `_token_metadata` in
  `try/except Exception → {}` so a metadata failure degrades to
  `short_addr(token)` and a raw amount.
- `chainq/commands/chain.py:280-295` — `_token_metadata(client, addresses)`
  batches `symbol` + `decimals` through one `multicall`. It raises on RPC
  failure by design; the caller absorbs it.
- `chainq/commands/chain.py:368-374` — the wiring. Both enrichments are gated
  behind `receipt is not None`.
- `chainq/commands/chain.py:375-412` — `data` keys and text `lines`.
  `data["function"]` and `data["token_transfers"]` are part of the published
  JSON contract and **must keep their current shape and semantics**.
- `chainq/evm.py:72-77` — `decode_abi(types: list[str], data: str) -> tuple`.
  Note the signature: it takes a **hex string**, not bytes, and raises
  `ChainqError` on failure. `log["data"]` is `HexBytes`, so callers must pass
  `"0x" + bytes(log["data"]).hex()`.
- `chainq/evm.py:12-27` — `parse_abi_types` splits a comma-separated type list
  at depth 0, so it handles tuple types correctly. Use it; do not re-split.
- `chainq/evm.py:86-91` — `json_value` converts bytes → `0x…` and tuples →
  lists. Every decoded value that reaches `data` must pass through it or the
  `--json` output will fail to serialize.
- `chainq/rpc.py:101-117` — `decode_address(data)` (last 20 bytes of a 32-byte
  word, checksummed), `decode_uint`, `decode_string`.
- `chainq/fmt.py` — `fmt_amount`, `fmt_usd`, `short_addr`, `bold`, `dim`.
- Output contract (AGENTS.md, non-negotiable): `--json`, `-q`, `-v`,
  `--format text|json|table|toon`; errors → stderr, exit 1.
- Conventions: **no code comments**; errors via `ChainqError`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Lint | `uv run ruff check .` | exit 0 |
| Unit tests | `uv run pytest -q` | all pass (baseline: 140 passed, 24 deselected) |
| Live run | `uv run chainq tx <hash> -n <net>` | see steps |

## Scope

**In scope**:
- `chainq/decode.py` (create — pure, network-free event decoding)
- `chainq/commands/chain.py` (the EVM `tx` function and its helpers only)
- `tests/test_tx_events.py` (create)
- `skills/chainq/SKILL.md`, `README.md`

**Out of scope** (do NOT touch):
- `_solana_tx` and everything Solana
- ERC-4337 and Safe/multisig framing — **plan 011**, which depends on this one.
  Do not add `UserOperationEvent` or `ExecutionSuccess` here.
- Reading pool internals (`token0`/`token1`, `slot0`) to price swaps — see
  "Findings considered and rejected" in `plans/README.md`; amounts come from
  transfer logs, not from swap-event parameters
- Internal call traces (`debug_traceTransaction`) — most public RPCs reject it
- `chainq/providers/fourbyte.py` — consume as-is

## Git workflow

- Branch: `feat/tx-event-decoding`. Do NOT commit or push; leave uncommitted and
  report.

## Steps

### Step 1: The event registry

Create `chainq/decode.py`. Key the registry by **`(topic0, len(topics))`**, not
by `topic0` alone. This is not defensive over-engineering — Safe changed
`ExecutionSuccess` from non-indexed to `indexed` between contract versions
without changing the signature string, so one topic0 legitimately maps to two
different layouts, and plan 011 needs the same registry. Keying on the pair also
means a log whose layout does not match is simply not decoded, instead of being
mis-decoded into confident nonsense.

```python
@dataclass(frozen=True)
class EventSpec:
    name: str
    signature: str
    indexed: list[str]
    data: list[str]
    kind: str
```

Build `EVENTS: dict[tuple[bytes, int], EventSpec]` at import time by computing
`Web3.keccak(text=spec.signature)` — **never paste a topic hash as a literal**
(repo rule; and it is the whole reason the table below is signatures, not
hashes).

Every row was confirmed live on Ethereum mainnet on 2026-07-28 by
`eth_getLogs` over blocks 25627804–25627864 (60 blocks) unless noted. `topics`
is the observed topic count including topic0.

| kind | signature | topics | observed emitter | 60-block hits |
|------|-----------|--------|------------------|---------------|
| `approve` | `Approval(address,address,uint256)` | 3 | (many) | 2151 |
| `approve` | `ApprovalForAll(address,address,bool)` | 3 | `0x062E691c2054dE82F28008a8CCC6d7A1c8ce060D` | 20 |
| `approve` | `Approval(address,address,address,uint160,uint48)` | 4 | Permit2 `0x000000000022D473030F116dDEE9F6B43aC78BA3` | 30 |
| `approve` | `Permit(address,address,address,uint160,uint48,uint48)` | 4 | Permit2 `0x000000000022D473030F116dDEE9F6B43aC78BA3` | 30 |
| `swap` | `Swap(address,uint256,uint256,uint256,uint256,address)` | 3 | v2-style pair `0x2574c142F25a0111E73Dbf46C838646759bA1A6E` | 930 |
| `swap` | `Swap(address,address,int256,int256,uint160,uint128,int24)` | 3 | v3-style pool `0x4d68B530920D26c3b01C99fecC19e21011B72bBD` | 1555 |
| `swap` | `Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)` | 3 | Uniswap v4 PoolManager `0x000000000004444c5dc75cB358380D2e3dE08A90` | 1487 |
| `swap` | `TokenExchange(address,int128,uint256,int128,uint256)` | 2 | Curve `0x4d9f9D15101EEC665F77210cB999639f760F831E` | 69 |
| `swap` | `Swap(bytes32,address,address,uint256,uint256)` | 4 | Balancer Vault `0xBA12222222228d8Ba445958a75a0704d566BF2C8` | 27 |
| `wrap` | `Deposit(address,uint256)` | 2 | WETH `0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2` | 582 |
| `unwrap` | `Withdrawal(address,uint256)` | 2 | WETH `0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2` | 1081 |
| `deposit` | `Deposit(address,address,uint256,uint256)` | 3 | ERC-4626 vault `0xbeef00B5d83C1188F07A5184230a805639c39f04` | 9 |
| `withdraw` | `Withdraw(address,address,address,uint256,uint256)` | 4 | ERC-4626 vault `0xbeef088055857739C12CD3765F20b7679Def0f51` | 20 |
| `supply` | `Supply(address,address,address,uint256,uint16)` | 4 | Aave v3 Pool `0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2` | 8 |
| `withdraw` | `Withdraw(address,address,address,uint256)` | 4 | Aave v3 Pool | 6 |
| `borrow` | `Borrow(address,address,address,uint256,uint8,uint256,uint16)` | 4 | Aave v3 Pool | 7 |
| `repay` | `Repay(address,address,address,uint256,bool)` | 4 | Aave v3 Pool | 3 |
| `withdraw` | `Withdraw(address,address,uint256)` | 3 | Compound III `0x8707f238936c12c309bfc2B9959C35828AcFc512` | 1 (190-block window) |
| `borrow` | `Borrow(bytes32,address,address,address,uint256,uint256)` | 4 | Morpho Blue `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb` | 5 (190-block window) |
| `transfer` | `Transfer(address,address,uint256)` | 3 | (many) | — |
| `nft` | `TransferSingle(address,address,address,uint256,uint256)` | 4 | `0x33FD426905F149f8376e227d0C9D3340AaD17aF1` | 3 |
| `nft` | `TransferBatch(address,address,address,uint256[],uint256[])` | 4 | `0x55b4Dd2Fe0dE263c8C01e7a515B4Abe99f75eA3B` | 6 |
| `nft` | `Transfer(address,address,uint256)` | 4 | ERC-721 | — |

**The table above is the complete registry. Do not add rows to it.**

Four further candidates were computed and deliberately **excluded**:
`LiquidationCall(address,address,address,uint256,uint256,address,bool)` (Aave),
`Supply(address,address,uint256)` and
`SupplyCollateral(address,address,address,uint256)` (Compound III), and
`Supply(bytes32,address,address,address,uint256,uint256)` (Morpho Blue). Each
produced **zero hits** in the sampled window. They are rare rather than wrong,
but an unobserved signature is an unverified constant, and chasing one is
open-ended work with no bounded stopping point. A rare action that goes
undecoded falls through to `action call` with the 4byte function name — a
correct, honest degradation. A *wrongly* decoded rare action is confidently
wrong output, which is strictly worse.

If you find yourself wanting a row that is not in the table, that is a signal to
finish the plan as written and report the gap, not to add it.

Two facts the table encodes that are easy to get wrong:

- **A signature is not a protocol.** `Swap(address,uint256,uint256,uint256,uint256,address)`
  is emitted identically by every Uniswap v2 fork. Label it `v2-style`, never
  "Uniswap". The same applies to `v3-style`.
- **Name collisions are resolved by topic0, not by name.** `Deposit(address,uint256)`
  (WETH) and `Deposit(address,address,uint256,uint256)` (ERC-4626) are unrelated
  events that share a name; `Withdraw` has three distinct arities in this table.
  Since the registry is keyed by hash, this is handled — but do not "simplify"
  the registry to be keyed by event name.

**Verify**: `uv run python -c "from chainq.decode import EVENTS; print(len(EVENTS))"`
prints the row count, and every key is a `(bytes, int)` pair.

### Step 2: Decode a log

```python
def decode_log(log) -> dict | None
```

Pure and network-free. Steps:

1. Look up `EVENTS.get((bytes(log["topics"][0]), len(log["topics"])))`; return
   `None` when absent.
2. Indexed values come from `log["topics"][1:]`. For `address`, use
   `decode_address`; for `uint*`/`int*`/`bool`, decode the word; for **dynamic
   indexed types** (`bytes`, `string`, arrays) the topic is the keccak of the
   value, not the value — record it as the `0x…` hash and never present it as a
   decoded value.
3. Non-indexed values come from `decode_abi(spec.data, "0x" + bytes(log["data"]).hex())`.
   Wrap in `try/except Exception → return None`. `decode_abi` raises
   `ChainqError`, and a malformed log must never abort `tx`.
4. Return `{"event": spec.name, "kind": spec.kind, "address": log["address"], "args": {...}}`
   with every value passed through `json_value`.

Signed integers matter here: v3-style `Swap` carries `int256 amount0/amount1`
where the sign is the direction. `eth_abi` handles the two's-complement decode
as long as the type string says `int256` — do not coerce to `uint`.

**Verify**: unit tests from the Test plan pass.

### Step 3: Net token flow for the sender

This is the feature that answers "what did this tx do for me", and it costs
**zero extra RPC calls** — it is computed from transfer rows that
`_decode_transfers` already produced.

Add `_net_flow(transfers, address, native_value, native_symbol) -> list[dict]`:

- Sum signed amounts per token over the decoded transfers: `-amount` where
  `from == address`, `+amount` where `to == address`. Compare addresses
  case-insensitively.
- Fold in the native leg: a non-zero `transaction["value"]` is `-value` for the
  sender.
- Drop tokens whose net is zero (routers that receive and forward in the same
  tx), and sort by absolute value descending.

Be honest about the limits in the docs, not just the code: the net flow is
computed over the **capped** transfer list (10 rows), and protocols with
native/flash accounting — Uniswap v4 is the live example in "Why this matters" —
settle legs without emitting a `Transfer`, so one side can be missing. When the
`+N more` note is present, the net line must be marked partial.

### Step 4: Classify the action

`_classify(function_name, events, transfers, transaction) -> str`, first match
wins:

1. `swap` — any `kind == "swap"` event
2. `borrow`, `repay`, `supply`, `withdraw`, `deposit` — the matching lending or
   vault kind
3. `wrap` / `unwrap`
4. `mint` / `burn` — transfers whose `from` or `to` is the zero address and no
   other classified event
5. `approve` — approval events and no transfers
6. `nft` — only NFT-kind events
7. `transfer` — transfers only
8. `call` — calldata present, nothing recognized
9. `send` — no calldata

`action` is a **label, not a decision**: the same rule plan 004 set for the
4byte name applies here, and for the same reason. Nothing may branch on it.

### Step 5: Wire into `tx`

- Extend `data` with `"action": <str>`, `"events": [...]`, `"net_flow": [...]`.
  All three always present so `--json` consumers can rely on the keys.
- **Do not change** `function`, `token_transfers`, or any existing key or line.
  A tx that decodes to nothing new must print byte-identical output to `main` —
  this is a done criterion, and plan 004 was verified the same way.
- Text lines, after the existing `transfers:` block:
  ```
    action swap
    net for 0x18a2…5810: -3,024,572.95 GOD, +0.42 WETH
    events:
      swap  v3-style pool 0x88e6…5640
      approve  USDC → 0x0000…78BA3: unlimited
  ```
- Suppress the `action` line for `send` and `call` — those add no information
  over the existing lines and would be pure noise on the most common txs.
- Cap `events` at 10 with the same `+N more` note pattern as transfers.
- Render an approval whose value is `2**256 - 1` as `unlimited`. Do not
  threshold on "large" values; only the exact max is the idiom.
- `-q` still prints only the status. Unchanged.
- Colorize per AGENTS.md: dim the labels, green/red the signed net-flow amounts.

**Verify**: `uv run ruff check .` → exit 0; `uv run pytest -q` → pass.

### Step 6: Live tests

Find your own hashes — sample recent blocks with
`uv run chainq rpc eth_getBlockByNumber latest true -n ethereum`, or filter logs
by a topic from your registry. The three hashes quoted in "Why this matters" are
real and permanent, so use them as **regression fixtures** for the before/after
comparison, but do not let them be your only coverage.

- Plain ETH send → output **byte-identical** to `main`. Diff it:
  `diff <(git stash && uv run chainq tx 0xHASH; git stash pop) <(uv run chainq tx 0xHASH)`
  or run the same hash from a second checkout. This is the single most important
  check in the plan.
- v3-style swap → `action swap`, a `net for …` line with one negative and one
  positive leg, and a `swap  v3-style pool 0x…` event row.
- ERC-20 approval tx → `action approve`, and an `unlimited` render if the tx
  approved max.
- Aave supply and an ERC-4626 vault deposit → correct `action`.
- `0x8267e2a62909efc1fd394d146e7a5408b1468a23a598661f93efe894f417e630` (Uniswap
  v4) → `action swap`; confirm the native leg is missing from `net_flow` and
  that the output does not imply otherwise.
- One tx on `-n base` and one on `-n arbitrum` → exit 0.
- `--json | python3 -m json.tool` → exit 0 with all three new keys present;
  `--format table`, `--format toon`, `-q` → exit 0.
- Failure isolation: point `CHAINQ_RPC_ETHEREUM` at an unreachable host for the
  metadata multicall path, or feed a tx with a malformed log, and confirm the
  baseline readout still prints.

**Verify**: all runs behave as stated.

## Test plan

`tests/test_tx_events.py`, pure logic with synthetic log dicts — no network
(repo rule: unit tests never mock providers). Model on `tests/test_tx_decode.py`,
which already builds byte fixtures with a `_topic(address)` helper.

- registry keying: a log with a known topic0 but the wrong topic count returns
  `None` rather than a wrong decode
- both Safe-style layouts of one signature resolve to their own spec
- indexed address extraction; signed `int256` swap amounts decode negative
- dynamic indexed types surface as a hash, not a bogus value
- malformed `data` returns `None` and does not raise
- net flow: nets to zero for a pass-through router; signs are correct; the
  native leg is folded in; partial when the cap note is present
- classification precedence: a swap that also emits an approval classifies as
  `swap`
- the `2**256 - 1` approval renders `unlimited`; `2**255` does not

## Done criteria

- [ ] `uv run ruff check .` exits 0; `uv run pytest -q` exits 0 with new tests
- [ ] A plain ETH send and a plain ERC-20 transfer produce **byte-identical**
      output to `main` (demonstrate the comparison in your report)
- [ ] Live swap, approval, lending-supply, and vault-deposit txs each show the
      right `action` and a correct `net for …` line
- [ ] Every registry entry has been observed in a live log, or was dropped and
      reported
- [ ] `--json` gains `action`, `events`, `net_flow`; no existing key changed
- [ ] A malformed or undecodable log leaves the baseline readout intact
- [ ] `git status` shows only in-scope files modified; `plans/README.md` updated

## STOP conditions

Stop and report back if:

- A signature in the Step 1 table cannot be observed live and you cannot find a
  correct replacement — report the observed topic0 instead of guessing.
- `log["topics"]` or `log["data"]` are not `HexBytes` in the pinned web3
  version — report the actual types before adapting.
- Decoding requires an extra RPC round-trip to be useful (e.g. you conclude the
  net-flow line needs `token0`/`token1`) — that is explicitly out of scope;
  report the tradeoff rather than adding calls.
- `chain.py` has drifted materially from the excerpts above.

## Maintenance notes

- The registry is the extension point. A new protocol integration adds rows;
  it must not add branching in `tx`.
- Anything added to `tx` degrades silently or does not ship. `tx` is a core
  command and its baseline output — status, parties, value, fee, block — must
  survive a failing decoder, price lookup, or metadata call. This is the rule
  plan 004 established and it is not negotiable.
- `action` and the 4byte `function` are both labels. Never branch on either.
- ERC-721/1155 rows are in the registry for classification only. Rendering NFT
  transfers with token ids and collection names is a separate feature.
- Plan 011 (ERC-4337 + Safe) consumes `EVENTS` and `decode_log` unchanged. Keep
  `chainq/decode.py` free of network access so it stays reusable.
