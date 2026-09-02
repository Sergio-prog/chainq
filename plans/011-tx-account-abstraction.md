# Plan 011: Make `chainq tx` see through bundlers and multisigs — ERC-4337 and Safe

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat ec93976..HEAD -- chainq/commands/chain.py chainq/decode.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (changes which address a user reads as "the sender" — getting this wrong is worse than not shipping it)
- **Depends on**: **plans/010-tx-event-decoding.md** (hard — this plan consumes `chainq/decode.py`)
- **Category**: direction
- **Planned at**: commit `ec93976`, 2026-07-28
- **Status**: TODO — blocked on 010

## Why this matters

Plans 004 and 010 assume the transaction sender is the actor. For account
abstraction and multisigs that assumption is false, and the output is actively
misleading. Both examples below were run against `main` at `ec93976` on
2026-07-28.

A bundled ERC-4337 transaction:

```
$ chainq tx 0xa25346f322aee5733a72030c6e68346f4b0bcc062b207aa1eb214bf16799b512
  0x4337002C5702CE424Cb62A56CA038e31e1D4A93d → 0x0000000071727De22E5E9d8BAf0edAc6f37da032
  value 0 ETH, fee 0.0000520408 ETH (~$0.0976826)
  calls handleOps((address,uint256,bytes,bytes,bytes32,uint256,bytes32,bytes,bytes)[],address)
  transfers:
    0.7 USDT: 0xca76…4B19 → 0x0766…D38b
```

`from` is the bundler's EOA and `to` is the EntryPoint. Neither is the user.
The actual account — `0xca76…4B19` — appears only as an incidental party in a
transfer row, and the fee shown is the bundler's gas cost, not what the account
was charged. An agent asked "did my transaction go through?" gets an answer
about someone else's transaction.

A Safe multisig execution:

```
$ chainq tx 0x8539701a7c29df5d44d3bba265ace0ea79b403839dc07db37e603ce390153349
  0xEf329c418c43E4aFba82a4981d3447207bC2d8ae → 0x4e81EAE032B1fD83E13e6205dF43ECAe513d4eA4
  calls execTransaction(address,uint256,bytes,uint8,uint256,uint256,uint256,address,address,bytes)
```

`from` is whichever owner happened to submit; the Safe is unlabeled; and
nothing distinguishes a successful inner execution from a Safe call that
succeeded at the EVM level while its inner transaction reverted. That
distinction is the entire point of looking up a multisig transaction.

## Current state

- `chainq/decode.py` — created by plan 010. `EVENTS: dict[tuple[bytes, int], EventSpec]`
  keyed by `(topic0, len(topics))`, and `decode_log(log) -> dict | None`, pure
  and network-free. **This plan adds rows to that registry and a framing layer
  on top; it does not fork the decoder.**
- `chainq/commands/chain.py` — the EVM `tx` function, with `data` carrying
  `function`, `token_transfers`, and (after 010) `action`, `events`, `net_flow`.
- `chainq/fmt.py` — `fmt_amount`, `fmt_usd`, `short_addr`, `dim`, `bold`.
- `chainq/rpc.py:101-110` — `decode_address`, `decode_uint`.
- Output contract (AGENTS.md): `--json`, `-q`, `-v`,
  `--format text|json|table|toon`; errors → stderr, exit 1.
- Conventions: **no code comments**; errors via `ChainqError`.

## The verified event layouts

All four were confirmed live on Ethereum mainnet on 2026-07-28. The
`UserOperationEvent` and Safe `ExecutionSuccess` layouts below were read out of
real receipts word by word, not inferred from an ABI.

**`UserOperationEvent(bytes32,address,address,uint256,bool,uint256,uint256)`**
— topic0 `0x49628fd1…`, 4 topics, 4 data words. From tx
`0xa25346f322aee5733a72030c6e68346f4b0bcc062b207aa1eb214bf16799b512`:

| position | field | observed value |
|----------|-------|----------------|
| topic1 | `userOpHash` | `0x1cc89e84…80ea` |
| topic2 | `sender` | `0xca7639d776eb56d4ed694ab8fc0fbf59bfff4b19` |
| topic3 | `paymaster` | `0x777777777777aec03fd955926dbf81597e66834c` |
| data w0 | `nonce` | `1` |
| data w1 | `success` | `1` |
| data w2 | `actualGasCost` | `0x3480bcc087ec` wei |
| data w3 | `actualGasUsed` | `210379` |

So: three indexed, four in data. `paymaster` is the zero address when the
account paid its own gas.

**Two EntryPoint versions are live simultaneously** and emit the *same* topic0:
`0x0000000071727De22E5E9d8BAf0edAc6f37da032` (v0.7, observed) and
`0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789` (v0.6, observed emitting
`UserOperationRevertReason`). **Do not gate detection on an EntryPoint
address list.** Gate on the presence of `UserOperationEvent` logs and read the
EntryPoint address off the emitter. That is version-proof, network-proof, and
needs no registry to maintain.

**`UserOperationRevertReason(bytes32,address,uint256,bytes)`** — topic0
`0x1c4fada7…`, 3 topics (`userOpHash`, `sender` indexed), `nonce` and
`revertReason` in data. 19 hits in the sampled window.

**`ExecutionSuccess(bytes32,uint256)`** — topic0 `0x442e715f…`. From tx
`0x01cc77ce3ec2e4121b91adb8f3e382721723127503713834372ddbdb437cb60b`, emitter
`0xc0955482505C19941B2313AC5ea5F0e6dd3FB510`: **2 topics** — `txHash` is
indexed — and one data word (`payment`, observed `0`).

This is the reason plan 010 keys the registry by `(topic0, topic_count)`.
Safe's older contracts declare `ExecutionSuccess(bytes32 txHash, uint256 payment)`
with **no** indexing, which emits 1 topic and 2 data words, while newer ones
index `txHash`. Same signature, same topic0, two layouts. Register both. If you
find yourself writing an `if len(topics) == …` branch inside the decoder,
you are working around the registry instead of using it.

**`SafeMultiSigTransaction(address,uint256,bytes,uint8,uint256,uint256,uint256,address,address,bytes,bytes)`**
— topic0 `0x66753cd2…`, **1 topic** (everything non-indexed), 33 data words,
emitter is the Safe itself. 9 hits in the sampled window. Also verified:
`ExecutionFromModuleSuccess(address)`, topic0 `0x6895c136…`, 2 topics, 43 hits.

`ExecutionFailure(bytes32,uint256)` (topic0 `0x23428b18…`) produced **zero
hits** — failed Safe executions are rare, not nonexistent. You must observe one
live before shipping it, or drop it and report. Finding one is what the
`--format json` output of a Safe transaction service or an explorer's event tab
is for.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Lint | `uv run ruff check .` | exit 0 |
| Unit tests | `uv run pytest -q` | all pass |
| Live run | `uv run chainq tx <hash> -n <net>` | see steps |

## Scope

**In scope**:
- `chainq/decode.py` (add the four event rows above)
- `chainq/commands/chain.py` (the EVM `tx` function only)
- `tests/test_tx_aa.py` (create)
- `skills/chainq/SKILL.md`, `README.md`

**Out of scope** (do NOT touch):
- Decoding the inner `callData` of a UserOperation, or the inner `data` of a
  Safe transaction, into a nested call tree — recursive decode is a separate
  feature; here the inner effects are already visible as events and transfers
- Looking up pending/queued Safe transactions via the Safe transaction service
  — that is an HTTP provider and a different command
- EIP-7702 delegation — `chainq address` already detects it; not a tx concern
- Solana, and everything plan 010 owns

## Git workflow

- Branch: `feat/tx-account-abstraction`, based on the merged plan-010 work. Do
  NOT commit or push; leave uncommitted and report.

## Steps

### Step 1: Register the events

Add the four signatures to `EVENTS` with kinds `userop`, `userop_revert`,
`safe_exec`, `safe_module_exec`. Two `ExecutionSuccess` entries — one per
topic-count layout. Compute topic0 with `Web3.keccak(text=…)`; no literals.

**Verify**: a unit test asserts both `ExecutionSuccess` layouts resolve, and
that a 2-topic lookup does not return the 1-topic spec.

### Step 2: User operations

`_user_operations(receipt) -> list[dict]` — pure, no RPC. For each decoded
`userop` event, emit:

```python
{"sender": ..., "paymaster": ... or None, "user_op_hash": ..., "nonce": ...,
 "success": bool, "gas_cost": <native, Decimal→str>, "gas_used": ...,
 "revert_reason": ... or None}
```

- `paymaster` is `None` when it decodes to the zero address — say "self-paid",
  do not print a zero address.
- Match `UserOperationRevertReason` rows to their operation by `userOpHash` and
  attach the reason. Decode the `bytes` reason as a UTF-8 `Error(string)` when
  it parses; otherwise keep the raw hex. Never raise on a malformed reason.
- `gas_cost` is `actualGasCost` in native wei, scaled by 1e18. This is what the
  **account** paid, which is not the transaction fee already printed — label it
  so the two cannot be confused.
- Cap at 10 with the `+N more` note pattern used elsewhere.

A bundle contains operations from unrelated senders. Present them as a list of
peers; never promote one to "the" sender.

### Step 3: Safe executions

`_safe_executions(receipt, transaction) -> list[dict]`:

```python
{"safe": <emitter>, "safe_tx_hash": ..., "success": bool, "payment": ... or None,
 "via": "owners" | "module"}
```

- `via` is `"module"` for `ExecutionFromModuleSuccess`, `"owners"` otherwise.
- The emitter is the Safe. Do **not** infer the Safe from `transaction["to"]`:
  nested Safes and batched multisends emit from an address that is not `to`.
- A Safe transaction can succeed at the EVM level while its inner execution
  fails — that is precisely what `ExecutionFailure` reports, and surfacing it is
  the main reason this step exists. The tx-level `status` line must stay
  `success` in that case; the inner failure is reported on its own line, never
  by rewriting the tx status.

### Step 4: Wire into `tx`

- Extend `data` with `"user_operations": [...]` and `"safe_executions": [...]`,
  always present.
- Extend `action` (from plan 010) with `userop` and `safe_exec`, which take
  precedence over every other classification — they describe the frame, and the
  inner swap or transfer is what the frame contains.
- Text, after the `action` line:
  ```
    action userop  via EntryPoint 0x0000…a032
    user operations:
      0xca76…4B19  success  paid 0.0000575 ETH  paymaster 0x7777…834c
      0x88f1…2b0e  reverted  Error: insufficient allowance
    action safe_exec
    safe 0x4e81…4eA4 executed 0x979c…59a9: success (via owners)
  ```
- Colorize per AGENTS.md: green `success`, red `reverted`/`failed`, dim labels.
- Every existing key and line stays byte-identical for transactions with no
  user operations and no Safe executions. Same rule, same verification method,
  as plans 004 and 010.
- `-q` still prints only the tx status. Do not make it context-dependent.

**Verify**: `uv run ruff check .` → exit 0; `uv run pytest -q` → pass.

### Step 5: Live tests

- `0xa25346f322aee5733a72030c6e68346f4b0bcc062b207aa1eb214bf16799b512` →
  `action userop`, one operation with sender `0xca7639d776eb56d4ed694ab8fc0fbf59bfff4b19`,
  paymaster `0x777777777777aec03fd955926dbf81597e66834c`, `success`, gas used
  `210379`. These are the values read from the receipt in this plan; a mismatch
  means the decode is wrong.
- A **v0.6** EntryPoint tx (`0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789`) →
  decodes identically without any version flag.
- A **multi-operation** bundle → several peer rows, no single promoted sender.
- A reverted operation → `UserOperationRevertReason` attached to the right
  `userOpHash`.
- `0x8539701a7c29df5d44d3bba265ace0ea79b403839dc07db37e603ce390153349` →
  `action safe_exec`, safe `0x4e81EAE032B1fD83E13e6205dF43ECAe513d4eA4`,
  safe tx hash `0x979c9bcce5974d6535b5d0884e5ebbf23f5ce2673e2f2f45376e5434777359a9`,
  success.
- A Safe execution on `-n base` or `-n arbitrum` → exit 0. Account abstraction
  is heavier on L2s; do not ship this ethereum-only.
- A plain ETH send and a plain ERC-20 transfer → **byte-identical** to the
  plan-010 baseline.
- `--json | python3 -m json.tool`, `--format table|toon`, `-q` → exit 0.

**Verify**: all runs behave as stated.

## Test plan

`tests/test_tx_aa.py`, pure logic with synthetic receipts — no network. Model on
`tests/test_tx_decode.py`.

- both `ExecutionSuccess` layouts decode to the same logical row
- a `UserOperationEvent` fixture built from the observed words yields the exact
  field values in the table above
- zero-address paymaster → `None`, not `"0x0000…"`
- revert reason matched by `userOpHash`, including when a bundle has several
  operations and only one reverted
- a malformed revert reason keeps raw hex and does not raise
- multi-operation bundles preserve order and do not merge senders
- module-executed Safe rows carry `via == "module"`
- `ExecutionFailure` does **not** flip the tx-level status field

## Done criteria

- [ ] `uv run ruff check .` exits 0; `uv run pytest -q` exits 0 with new tests
- [ ] The v0.7 bundle above decodes to exactly the sender, paymaster, success
      flag, and gas figures recorded in this plan
- [ ] A v0.6 EntryPoint tx decodes with no version-specific code path
- [ ] The Safe tx above shows the Safe, the safe tx hash, and success
- [ ] An `ExecutionFailure` case is observed live and reported, or the row is
      dropped and that is stated
- [ ] Plain sends and transfers remain byte-identical to plan 010's output
- [ ] `--json` gains `user_operations` and `safe_executions`; no existing key
      changed
- [ ] `git status` shows only in-scope files modified; `plans/README.md` updated

## STOP conditions

Stop and report back if:

- The observed `UserOperationEvent` layout differs from the table above on any
  network you test — report the raw topics and data words.
- An EntryPoint version is found whose `UserOperationEvent` topic0 differs —
  that breaks the "gate on the event, not the address" design and needs a
  decision, not a workaround.
- Correct Safe framing appears to require an extra RPC call (e.g. reading
  `getOwners`/`getThreshold`) — out of scope; report the tradeoff.
- `chainq/decode.py` from plan 010 is absent or its registry is not keyed by
  `(topic0, topic_count)` — this plan depends on that shape.

## Maintenance notes

- Detection is by event, never by address list. Any future EntryPoint,
  smart-account, or Safe deployment works with no registry update, which is the
  whole design.
- `action` remains a label. Nothing branches on `userop` or `safe_exec`.
- Owner/threshold context, Safe transaction-service lookups, nested multisend
  expansion, and recursive inner-calldata decoding are all deliberate
  follow-ups, not omissions.
- The `+N more` cap applies to bundles too; large bundles are common on L2s, so
  the cap will be hit in practice — the note must never be silently dropped.
