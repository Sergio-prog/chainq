# Plan 007: Add Robinhood Chain mainnet across the EVM query surface

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update this plan's row in
> `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 7b4fb6f..HEAD -- chainq/networks.py tests/test_networks.py tests/test_live.py README.md ROADMAP.md skills/chainq/SKILL.md site/index.html site/public/llms.txt site/public/llms-full.txt`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: direction
- **Planned at**: commit `7b4fb6f`, 2026-07-10

## Why this matters

Robinhood Chain is a live EVM-compatible Arbitrum L2, so chainq's existing
balance, portfolio, gas, transaction, address, and raw-RPC commands work once
the network registry knows its chain ID and endpoint. The official public RPC
is keyless, preserving chainq's zero-setup contract. This is a small addition
with broad command coverage and no new dependency or protocol-specific code.

## Current state

- `chainq/networks.py:6-16` defines the complete network contract:

  ```python
  @dataclass(frozen=True)
  class Network:
      key: str
      name: str
      chain_id: int
      native_symbol: str
      native_coingecko_id: str
      rpc_urls: tuple[str, ...]
      explorer: str
      aliases: tuple[str, ...] = ()
      kind: str = "evm"
  ```

- `chainq/networks.py:19-313` contains 25 EVM mainnets and Solana. Robinhood
  Chain is absent. Registry entries are the only code needed by the generic
  EVM commands.
- `chainq/rpc.py:137-171` probes every configured RPC with `eth_chainId` and
  rejects endpoints returning the wrong chain ID. It also tries a
  `CHAINQ_RPC_<NETWORK>` override first.
- `chainq/rpc.py:192-215` uses canonical Multicall3 for portfolio sweeps. The
  live reconnaissance check found 3,808 bytes of code at
  `0xcA11bde05977b3631167028862bE2a173976CA11` on Robinhood Chain, so the batched
  native-balance path is available.
- Official Robinhood Chain configuration, re-verify before editing:
  <https://docs.robinhood.com/chain/connecting/>
  - mainnet chain ID: `4663` (`0x1237`)
  - native gas token: `ETH`
  - public RPC: `https://rpc.mainnet.chain.robinhood.com`
  - explorer: `https://robinhoodchain.blockscout.com`
- The live probe on 2026-07-10 returned `{"result":"0x1237"}` from the public
  RPC. The endpoint is rate-limited by design; chainq should still use it
  because zero-setup public endpoints are the registry convention.
- Network counts and lists are duplicated in `README.md:113`,
  `ROADMAP.md:9`, `skills/chainq/SKILL.md:3,53`, `site/index.html:38`, and
  `site/public/llms.txt:3`. `site/public/llms-full.txt` is generated from the
  skill by `site/scripts/gen-llms-full.mjs` during the site prebuild.
- Conventions: mainnets only in `NETWORKS`; no code comments; tests use plain
  asserts; every user-visible addition updates README, skill, roadmap, and the
  landing-site text.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| RPC probe | `curl -fsS -X POST -H 'content-type: application/json' --data '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' https://rpc.mainnet.chain.robinhood.com` | JSON result `0x1237` |
| Lint | `uv run ruff check .` | exit 0, `All checks passed!` |
| Tests | `uv run pytest -q` | all tests pass |
| Headless test diagnostic | `env -u NO_COLOR TERM=xterm uv run pytest -q` | all tests pass when the host exports `TERM=dumb` |
| Site | `pnpm --dir site build` | exit 0; Vite build completes |

The headless diagnostic is not a waiver for test failures. At planning time,
the suite passed 61 tests with a normal terminal environment; `TERM=dumb`
alone makes three pre-existing color assertions fail.

## Scope

**In scope**:
- `chainq/networks.py`
- `tests/test_networks.py`
- `tests/test_live.py`
- `README.md`
- `ROADMAP.md`
- `skills/chainq/SKILL.md`
- `site/index.html`
- `site/public/llms.txt`
- `site/public/llms-full.txt` (generated)

**Out of scope**:
- Robinhood Chain testnet (`46630`) — the registry contains production
  mainnets, not testnets.
- `chainq/tokens.py` — no token should be added without validating an official
  mainnet contract address; arbitrary ERC-20 addresses already work.
- Stock-token metadata, bridging, account abstraction, or protocol contracts.
- New RPC-provider credentials or an Alchemy/QuickNode dependency.

## Git workflow

- Branch: `feat/robinhood-chain`
- Conventional commit if and only if the owner later asks:
  `feat: add Robinhood Chain mainnet`
- Do not commit, push, or open a PR without the owner's explicit instruction.

## Steps

### Step 1: Re-verify the official network values

Open the official connecting guide and run the RPC probe from the command
table. Confirm the decimal/hex match: `4663 == 0x1237`. Also run:

```bash
curl -fsS -X POST -H 'content-type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"eth_getCode","params":["0xcA11bde05977b3631167028862bE2a173976CA11","latest"]}' \
  https://rpc.mainnet.chain.robinhood.com
```

The result must be non-empty bytecode, not `0x`. Do not substitute a third-party
endpoint based on memory.

**Verify**: both calls return JSON-RPC success; chain ID is `0x1237` and
Multicall3 code is non-empty.

### Step 2: Register the mainnet and lock resolution behavior

Add one `Network` entry in `chainq/networks.py`:

```python
Network(
    key="robinhood",
    name="Robinhood Chain",
    chain_id=4663,
    native_symbol="ETH",
    native_coingecko_id="ethereum",
    rpc_urls=("https://rpc.mainnet.chain.robinhood.com",),
    explorer="https://robinhoodchain.blockscout.com",
    aliases=("rh", "robinhood-chain"),
),
```

Use the key `robinhood`, because it produces the predictable override name
`CHAINQ_RPC_ROBINHOOD`. In `tests/test_networks.py`, add assertions for key,
alias, and chain-ID resolution. Add a uniqueness test that all registered
`chain_id` values are unique; this prevents a numeric query from resolving to
the wrong first entry as the registry grows.

**Verify**: `uv run pytest -q tests/test_networks.py` passes; `.venv/bin/chainq networks --json`
contains exactly one object with `key == "robinhood"` and `chain_id == 4663`.

### Step 3: Exercise generic EVM commands live

Run all of the following against the real endpoint:

```bash
uv run chainq rpc eth_chainId -n robinhood
uv run chainq gas -n robinhood --json
uv run chainq balance 0x000000000000000000000000000000000000dEaD -n robinhood --json
uv run chainq portfolio 0x000000000000000000000000000000000000dEaD -n robinhood --json
```

The raw RPC result must be `0x1237`; the structured commands must emit valid
JSON with `network: "robinhood"`. An empty/zero balance is valid. Add
`"robinhood-gas": ["gas", "-n", "robinhood"]` to `tests/test_live.py` so the
weekly live suite can detect endpoint drift once scheduled CI is enabled.

**Verify**: all four commands exit 0; `uv run pytest -q -m live -k robinhood`
passes.

### Step 4: Update every advertised network count

- `README.md`: change 25 to 26 and add `robinhood` to the explicit EVM list.
- `skills/chainq/SKILL.md`: change both 25 counts to 26 and add `robinhood` to
  the list; include `rh` among example aliases.
- `ROADMAP.md`: change Status to 26 EVM networks.
- `site/index.html`: change the hero copy to 26 EVM networks.
- `site/public/llms.txt`: change the compact summary to 26.
- Run `pnpm --dir site build` to regenerate `site/public/llms-full.txt` and
  verify the landing site.

Do not add a token list or claim Robinhood-specific protocol coverage.

**Verify**: `rg -n "25 EVM" README.md ROADMAP.md skills/chainq/SKILL.md site/`
returns no matches; `rg -n "26 EVM|robinhood"` shows the intended files; the
site build exits 0.

## Test plan

- `tests/test_networks.py`:
  - resolve `robinhood` by key;
  - resolve `rh` by alias;
  - resolve `4663` by chain ID;
  - assert all `Network.chain_id` values are unique.
- `tests/test_live.py`: one `gas -n robinhood` smoke entry, using the existing
  parametrized JSON contract.
- Live manual coverage: RPC chain ID, gas, native balance, single-network
  portfolio.

## Done criteria

- [ ] Official RPC returns `0x1237`; Multicall3 code is non-empty.
- [ ] `resolve_network("robinhood")`, `resolve_network("rh")`, and
  `resolve_network("4663")` all return the same entry.
- [ ] `uv run ruff check .` exits 0.
- [ ] `uv run pytest -q` exits 0 in a normal terminal environment.
- [ ] Robinhood live smoke and all four manual commands exit 0.
- [ ] README, skill, roadmap, site hero, and llms files say 26 EVM networks.
- [ ] `pnpm --dir site build` exits 0.
- [ ] `git status --short` shows only in-scope files plus the pre-existing
  untracked `media/chainq-twitter.mp4`.
- [ ] `plans/README.md` status row is updated.

## STOP conditions

Stop and report back if:

- The official docs no longer list chain ID `4663`, ETH, or the public mainnet
  endpoint.
- `eth_chainId` does not return `0x1237` twice in succession.
- The public endpoint requires authentication or consistently rate-limits the
  four minimal live commands.
- Multicall3 is no longer deployed at the canonical address; report whether
  native balance still works, but do not add a Robinhood-specific portfolio
  code path.
- Supporting the chain requires adding credentials or a non-public endpoint.

## Maintenance notes

- Robinhood's official docs recommend provider endpoints for production, but
  chainq deliberately ships rate-limited public fallbacks and supports a user
  override. Review that `CHAINQ_RPC_ROBINHOOD` is mentioned by the generic
  configuration text without a special case.
- When official Robinhood token contracts are added later, validate each live,
  checksum it, and add it to `TOKENS["robinhood"]`; this plan intentionally
  leaves portfolio coverage native-only.
- Version bumping remains a release-cut decision: this is a user-visible minor
  feature, but a batch of plans should bump `pyproject.toml` only once.
