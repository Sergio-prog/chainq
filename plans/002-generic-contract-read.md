# Plan 002: Add `chainq read` — call any view function on any contract

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 4b48de2..HEAD -- chainq/rpc.py chainq/cli.py chainq/commands/ chainq/output.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW (new command, no existing behavior changes)
- **Depends on**: none
- **Category**: direction
- **Planned at**: commit `4b48de2`, 2026-07-07

## Why this matters

chainq's only escape hatch for arbitrary onchain state is `chainq rpc eth_call`, which requires the caller to hand-encode calldata — unusable for agents without foundry installed. Internally the repo already has everything needed (`encode_call`, `decode_uint`/`decode_address`/`decode_string`, RPC fallback): a `chainq read 0xADDR "balanceOf(address)(uint256)" 0xUSER -n base` command exposes every view function on every contract on 25 networks with zero setup. It also makes the roadmap's ERC-4626 vault inspector nearly free (four `read` calls).

## Current state

- `chainq/rpc.py` — web3 wrapper. Key helpers (excerpts as of `4b48de2`):

  ```python
  # rpc.py:97-98
  def encode_call(abi: list, fn: str, args: list | None = None) -> bytes:
      return bytes.fromhex(_codec_w3.eth.contract(abi=abi).encode_abi(fn, args or [])[2:])

  # rpc.py:113-117 — _codec_w3 is a bare Web3() used as an ABI codec
  def decode_string(data: bytes) -> str:
      try:
          return _codec_w3.codec.decode(["string"], data)[0]
      ...
  ```

  `_codec_w3.codec.decode(types: list[str], data: bytes)` decodes any ABI types — use it for return values.
  `connect(network) -> ChainClient` (rpc.py:146) races fallback RPCs; `client.w3.eth.call({...})` does a raw eth_call.
  `resolve_address(value)` (rpc.py:174) resolves ENS `.eth` names and checksums — reuse for address-typed CLI args.

- `chainq/cli.py:19-32` — top-level commands are registered as `app.command()(chain.balance)` etc. A new `read` module registers the same way.
- `chainq/commands/ethena.py` — the exemplar thin command file: Typer function, `Out(json_out, quiet, verbose, format)`, `out.emit(data, lines, quiet_value=..., verbose_lines=[...])`. Match its shape.
- `chainq/output.py:112-158` — the `Out` dataclass. Every command takes `JsonOpt/QuietOpt/VerboseOpt/FormatOpt` (import from `chainq.output`).
- `chainq/networks.py` — `resolve_network(value)` accepts keys/aliases/chain ids; used by every network-aware command (e.g. `chainq/commands/uniswap.py:58`).
- Conventions: **no code comments**; errors are `ChainqError` (message to stderr, exit 1, handled centrally in `cli.py:64-71`); Typer args use `Annotated[..., typer.Argument(help=...)]`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Lint | `uv run ruff check .` | exit 0 |
| Unit tests | `uv run pytest -q` | all pass |
| Live run | `uv run chainq read ...` | see steps |

## Scope

**In scope**:
- `chainq/commands/read.py` (create)
- `chainq/cli.py` (register the command)
- `tests/test_read.py` (create — signature-parser unit tests)
- `skills/chainq/SKILL.md`, `README.md` (document the command; a new command MUST ship with a SKILL.md entry and a README example — repo rule)

**Out of scope** (do NOT touch):
- `chainq/rpc.py` — use its helpers as-is; if something seems missing, put the logic in `read.py`.
- `chainq/commands/chain.py` — the raw `rpc` command stays unchanged as the lower-level escape hatch.
- Write/transaction support of any kind — chainq is read-only by design (ROADMAP.md vision).
- Solana — this command is EVM-only; reject `-n solana` with a clear `ChainqError`.

## Git workflow

- Branch: `feat/contract-read`. Do NOT commit or push — leave work uncommitted and report (repo rule: owner asks for commits explicitly).

## Steps

### Step 1: Signature parser (pure function)

In `chainq/commands/read.py`, write `parse_signature(sig: str) -> tuple[str, list[str], list[str]]` returning `(fn_name, input_types, output_types)` for cast-style signatures:

- `"totalSupply()(uint256)"` → `("totalSupply", [], ["uint256"])`
- `"balanceOf(address)(uint256)"` → `("balanceOf", ["address"], ["uint256"])`
- `"getReserves()(uint112,uint112,uint32)"` → 3 outputs
- `"symbol()(string)"`, `"owner()(address)"`, `"paused()(bool)"`, `"merkleRoot()(bytes32)"`
- No output section (`"decimals()"`) → `output_types == []`, meaning print raw hex.
- Supported arg/return types: `address`, `bool`, `string`, `bytes`, `bytesN`, `uintN`/`intN` (any N). On tuples, arrays (`[]`), or anything else: raise `ChainqError("unsupported type '<t>' (supported: address, uint*, int*, bool, string, bytes*)")`.

Also write `coerce_arg(value: str, abi_type: str)`: ints from decimal or 0x-hex strings, `true`/`false` for bool, `0x…` passthrough for bytes, ENS/`.eth` resolution via `chainq.rpc.resolve_address` for `address`.

**Verify**: `uv run pytest -q tests/test_read.py` → parser tests pass (write them in this step, see Test plan).

### Step 2: The command

Add to `read.py`:

```python
def read(
    address: Annotated[str, typer.Argument(help="contract address or ENS name")],
    signature: Annotated[str, typer.Argument(help="function signature like 'balanceOf(address)(uint256)'")],
    args: Annotated[list[str] | None, typer.Argument(help="function arguments")] = None,
    network: Annotated[str, typer.Option("--network", "-n", help="network key, alias, or chain id")] = "ethereum",
    block: Annotated[str, typer.Option("--block", "-b", help="block number or 'latest'")] = "latest",
    json_out: JsonOpt = False, quiet: QuietOpt = False, verbose: VerboseOpt = False, format: FormatOpt = "text",
):
    """Call a view function on any contract and decode the result."""
```

Implementation: `resolve_network` → reject `net.kind == "solana"` → `connect` → build a one-entry ABI dict from the parsed signature (name/type=function/stateMutability=view/inputs/outputs with empty names) → `encode_call` → `client.w3.eth.call({"to": checksummed, "data": calldata}, block)` (parse `block` as int when it's digits) → decode with `_codec_w3.codec.decode(output_types, result)` — import the codec via a small local `Web3()` instance rather than reaching into rpc.py private globals.

Output contract:
- text: `totalSupply() on 0xdAC1…1ec7 [ethereum]: 91634171341393728` — one line; multiple outputs comma-separated.
- `--json`: `{"address", "network", "function", "args", "result": <single value or list>, "raw": "0x..."}`.
- `-q`: bare result value only.
- `-v`: rpc url used + raw hex.
- Empty return data (`0x`) → `ChainqError` explaining the address may not be a contract on that network.

Register in `chainq/cli.py` after the `market.candles` line: `app.command()(read.read)` (import `read` in the existing `from chainq.commands import ...` line).

**Verify**: `uv run chainq read --help` → shows the command; `uv run ruff check .` → exit 0.

### Step 3: Live tests (real endpoints — repo rule)

- `uv run chainq read 0xdAC17F958D2ee523a2206206994597C13D831ec7 "symbol()(string)"` → `USDT` in output
- `uv run chainq read 0xdAC17F958D2ee523a2206206994597C13D831ec7 "decimals()(uint8)"` → `6`
- `uv run chainq read 0xdAC17F958D2ee523a2206206994597C13D831ec7 "balanceOf(address)(uint256)" vitalik.eth` → a number, exit 0 (ENS arg path)
- `uv run chainq read 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 "name()(string)" -n base` → `USD Coin` (cross-network)
- `uv run chainq read 0xdAC17F958D2ee523a2206206994597C13D831ec7 "totalSupply()(uint256)" --json | python3 -m json.tool` → exit 0
- `uv run chainq read 0xdAC17F958D2ee523a2206206994597C13D831ec7 "nope()(uint256)"` → exits 1 with a clean error on stderr

**Verify**: all six behave as stated.

### Step 4: Docs

- SKILL.md: add a `## Generic contract reads` section with 3 examples (ERC-20 read, ENS arg, `-n base`), noting supported types and that it replaces hand-encoded `rpc eth_call`.
- README.md: one example line in the command overview.

**Verify**: `uv run ruff check .` && `uv run pytest -q` → clean.

## Test plan

- `tests/test_read.py`, modeled on `tests/test_fmt.py` (plain asserts, pure functions, no network):
  - parse: no-arg/no-output, single arg, multi-output, string/bool/bytes32 types
  - reject: tuple `(uint256,uint256)` as an arg type, arrays `uint256[]`, garbage input (each raises `ChainqError`)
  - coerce: `"123"` → int, `"0xff"` → 255, `"true"` → True, bad bool raises
- Verification: `uv run pytest -q` → all pass.

## Done criteria

- [ ] `uv run ruff check .` exits 0; `uv run pytest -q` exits 0 with new parser tests
- [ ] All six live commands in Step 3 behave as stated
- [ ] `uv run chainq read ... -n solana` (any read) exits 1 with a clear message
- [ ] SKILL.md and README.md document the command
- [ ] `git status` shows only in-scope files modified
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back if:

- `web3`'s codec API (`w3.codec.decode(types, data)`) doesn't exist under the pinned web3 version — check `uv.lock` and report the actual API instead of pulling in `eth_abi` directly without confirming it's already a transitive dependency (`uv run python -c "import eth_abi"`; note `chainq/commands/uniswap.py:4` already imports `eth_abi.encode`, so `eth_abi.decode` is the sanctioned fallback).
- Typer cannot express optional variadic `list[str] | None` positional args after two required ones — report the exact error rather than redesigning the CLI shape.
- The excerpts in "Current state" don't match the live code.

## Maintenance notes

- The roadmap's ERC-4626 inspector (`chainq vault`) should be built on this parser + `multicall` rather than a new ABI set — note for whoever picks that up.
- Reviewer: check the decode path against multi-value returns (tuple decoding order) and that `-q` prints exactly one value for single-output calls.
- Deferred deliberately: tuple/array types, `--from` override, batch reads (multicall exposure) — keep v1 small.
