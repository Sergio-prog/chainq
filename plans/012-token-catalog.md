# Plan 012: Token catalog — auto token lists per network, catalog-wide sweeps, spam-free portfolios

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 0b8ccc3..HEAD -- chainq/tokens.py chainq/cache.py chainq/rpc.py chainq/commands/portfolio.py chainq/commands/address.py chainq/commands/chain.py chainq/commands/uniswap.py chainq/providers/coingecko_data.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: MED (portfolio output changes for every user; wrong pricing or a spam leak is confidently wrong output)
- **Depends on**: none
- **Category**: direction (ROADMAP "Portfolio depth, part 2" — auto token lists per network)
- **Planned at**: commit `0b8ccc3` (v0.19.0), 2026-09-09

## Why this matters

`chainq portfolio`, `chainq address`, `chainq balance --coin <symbol>`, and the Uniswap symbol resolvers all read one hand-curated registry (`chainq/tokens.py`, ~60 EVM tokens on 9 of 26 networks, 8 SPL mints). Anything outside it is invisible: a wallet's largest position can be a mid-cap like BASECAT on Base and the sweep never sees it. Two downstream products (balance-breakdown, trenchbook) each had to bolt on their own discovery layer to work around this.

The naive fixes fail for known reasons. Static community token lists (Uniswap, Raydium, PancakeSwap) are archived and miss every token launched in the last two years. Explorer-based discovery (Blockscout "tokens held by address") finds everything, including ~80 airdrop scam tokens per active wallet, and the public instances answered 403 and 503 during planning. That approach is **explicitly out of scope** here.

Verified live on 2026-09-09, all without an API key:

| Source | What it gives | Verified fact |
|--------|---------------|---------------|
| `https://tokens.coingecko.com/{platform}/all.json` | per-chain token list: `address`, `symbol`, `name`, `decimals` | regenerated daily (`timestamp` today); a list exists for **all 26 EVM networks + Solana** (`robinhood` slug: 928 tokens; `sei-v2` works, `sei-network` 403); Base list has 2,677 tokens incl. BASECAT `0xb2000000000000000000004c27f6523082f41d01`; Ethereum 5,820; Solana 6,965 |
| `https://raw.githubusercontent.com/bgd-labs/aave-address-book/main/tokenlist.json` | Aave aTokens, stata tokens, underlyings, keyed by `chainId` with `tags` | 961 tokens; tags `aTokenV3`, `stataToken`, `staticAT`, `aTokenV2`, `underlying` |
| `https://api-v2.pendle.finance/core/v1/{chainId}/assets/all` | every PT / YT / SY / LP with `baseType`, `decimals`, `price.usd`, `expiry` | Ethereum: 2,511 assets (586 PT, 584 YT, 338 SY, 598 LP); `/core/v1/chains` → `[1, 56, 143, 196, 999, 4663, 8453, 9745, 42161, 10, 146, 5000, 80094]` |
| `https://lite-api.jup.ag/tokens/v2/tag?query=verified` | Solana verified mints with `symbol`, `name`, `decimals`, `liquidity`, `organicScore`, `isVerified` | 3,221 mints, 4.7 MB |
| `https://coins.llama.fi/prices/current/{chain}:{addr},…` | USD price + `confidence` per token, cross-chain in one call | ~100 ids per GET (300 → HTTP 414; POST → 404); priced BASECAT $0.0383 conf 0.99, sUSDe, aEthUSDC; **slugs verified for all 25 EVM networks** (table in Step 2); Solana prices come back as `0.0` for sub-cent mints — do not use Llama for Solana |
| `https://lite-api.jup.ag/price/v3?ids=mint,…` | Solana USD price + `liquidity` | BONK `3.04e-06`, liquidity $1.03M |
| `https://api.dexscreener.com/tokens/v1/{chain}/{addr,…}` | pools with `liquidity.usd`, ≤30 addresses per call | 30 addresses → 9 pairs in 0.3s |
| Multicall3 `balanceOf`-only sweep over the full CoinGecko list | | Base 2,677 tokens **1.8s**, Ethereum 5,820 tokens **3.9s** on the first public RPC, chunks of 1,500, zero failures; vitalik.eth holds 210 listed tokens on Base and 367 on Ethereum |

Spam policy, in filter order — each filter is cheaper than the next:

1. **Catalog membership**: only catalog tokens are swept. Scam airdrops are never on CoinGecko / Jupiter verified.
2. **Value floor**: `--min-usd` default rises from `0.01` to `1`. Listed-but-worthless dust is the bulk of a busy wallet's 200+ hits.
3. **Must be priceable**: a catalog hit with no DefiLlama / Jupiter price is checked against DexScreener with a **$1k liquidity floor** (batched, only for the unpriced leftovers). Still unpriced → hidden by default, counted, revealed by `--all`. Natives and curated-registry tokens are always shown (today's behaviour).

## Current state

- `chainq/tokens.py` — `TOKENS: dict[network_key, dict[symbol, checksummed address]]` (9 networks), `SOLANA_TOKENS`, `MINT_TO_SYMBOL`, `resolve_token(coin, network)` (curated symbol → address, else passthrough for `0x…`/base58, else `ChainqError` listing known symbols). Tests in `tests/test_tokens.py` enforce checksums and that every registry network exists.
- `chainq/cache.py` — one JSON blob `~/.cache/chainq/http-cache.json`; `key_for`, `get`, `put(key, value, ttl)`. Every `put` rewrites the whole file, so multi-MB token lists must **not** go through it.
- `chainq/rpc.py:192` `sweep_balances(client, address, tokens: dict[str, str]) -> (wei, rows)` — one `aggregate3` with **3 calls per token** (`balanceOf`, `decimals`, `symbol`); rows carry `registry_symbol`, `token_address`, `symbol`, `raw_amount`, `decimals`. `multicall(client, calls)` at `:120` is a single unchunked `aggregate3`.
- `chainq/commands/portfolio.py` — `_scan_evm` (`:47`) sweeps `TOKENS[net]`, sets `coingecko_id` from `coingecko.SYMBOL_TO_ID[registry_symbol]`; `_scan_evm_legacy` (`:17`) is the per-token fallback; `_scan_solana` (`:76`) names mints via `MINT_TO_SYMBOL`, unknown mints show as `short_addr(mint)` unpriced; `_priced` (`:161`) prices via one `coingecko.simple_price(ids)`; `portfolio()` (`:198`) has `--min-usd 0.01`, `--hide-unpriced`, `--defi`; verbose line says `registry tokens`.
- `chainq/commands/address.py` — `_holdings` (`:81`) is the same sweep + CoinGecko pricing, top 5 rendered; `_solana_address` (`:170`) lists only `MINT_TO_SYMBOL` mints under `known_tokens`.
- `chainq/commands/chain.py` — `balance` (`:107`) resolves `--coin` via `resolve_token`, prices via `SYMBOL_TO_ID.get(coin.lower())`; `_solana_balance` (`:90`) prices only registry mints.
- `chainq/commands/uniswap.py` — `pools` (`:67`) and `_resolve_pool_token` (`:80`) resolve symbols via `TOKENS.get(net.key, {})`.
- `chainq/providers/coingecko_data.py` — `PLATFORM_IDS` maps network key → CoinGecko platform slug for 25 of 26 EVM networks (**`robinhood` is missing**) + `solana`; `SYMBOL_TO_ID` maps ~60 symbols to CoinGecko ids.
- `chainq/providers/uniswap_data.py:46` `CHAIN_SLUGS` — DexScreener slugs for 9 networks; `chainq/providers/uniswap.py` has `_get` (cached) and `token_pairs` (single-token endpoint).
- `chainq/providers/defillama.py` — `_fetch(url, params)` uncached; no coins-API function exists.
- `chainq/http.py` — `get`/`post` with retries; `settings.http_timeout` = 10s.
- Conventions: no code comments; `--json`/`-q`/`-v`/`--format` contract; errors via `ChainqError`; registries hold checksummed addresses; version only in `pyproject.toml` (currently `0.19.0`); every new command → `skills/chainq/SKILL.md` + README example; ROADMAP kept in sync.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Lint | `uv run ruff check .` | `All checks passed!` |
| Unit tests | `uv run pytest -q` | all pass (baseline at `0b8ccc3`: run once before editing and record the count) |
| Live sweep | `uv run chainq portfolio vitalik.eth -n base` | BASECAT-class long-tail tokens appear; no dust, no unpriced rows |
| Live symbol | `uv run chainq balance vitalik.eth -c basecat -n base` | resolves via catalog, priced |
| Live catalog | `uv run chainq tokens search basecat -n base` | one row with the address above |
| Live Solana | `uv run chainq portfolio toly.sol` | long-tail mints named + priced, spam hidden |

## Scope

**In scope**:
- `chainq/catalog.py` (create) — sources, caching, lookup, symbol resolution
- `chainq/cache.py` — file-per-key blob cache for large lists
- `chainq/rpc.py` — chunked `multicall`, `balanceOf`-only catalog sweep
- `chainq/providers/defillama.py` — coins price API; `chainq/providers/jupiter.py` (create) — price v3; `chainq/providers/uniswap.py` — batch token endpoint
- `chainq/providers/coingecko_data.py` — add `robinhood` platform id
- `chainq/commands/portfolio.py`, `chainq/commands/address.py`, `chainq/commands/chain.py`, `chainq/commands/uniswap.py`, `chainq/tokens.py`
- `chainq/commands/tokens.py` (create) + registration in `chainq/cli.py`
- `tests/test_catalog.py`, `tests/test_cache.py`, `tests/test_rpc.py`, `tests/test_cli_registration.py`, `tests/test_live.py`
- `skills/chainq/SKILL.md`, `README.md`, `ROADMAP.md`, `pyproject.toml` (→ `0.20.0`)

**Out of scope** (do NOT touch):
- Explorer / Blockscout / Etherscan holder discovery — rejected (unreliable public instances, spam source). Record in `plans/README.md` "Findings considered and rejected".
- Aave/Morpho *position* accounting (debt, health factor) — aTokens are swept as plain balances only.
- Token ranking, scoring, or index features — the catalog is their foundation, not their implementation.
- Removing the curated `TOKENS` / `SOLANA_TOKENS` — they stay as the offline fallback and as the resolution overlay that guarantees `usdc` means the canonical USDC.

## Git workflow

Branch `feat/token-catalog` from `origin/main` (`0b8ccc3`) in its own worktree. Conventional commits only when the owner asks. Never push or open a PR without the owner's explicit ask.

## Steps

### Step 1 — Blob cache

In `chainq/cache.py` add a second store for large, slow-changing payloads:

```python
BLOB_DIR = CACHE_DIR / "blobs"

def get_blob(name: str, max_age: float | None = None) -> object | None
def put_blob(name: str, value: object) -> None
```

- One file per name: `BLOB_DIR / f"{name}.json"` holding `{"fetched_at": <epoch>, "value": ...}`; write via tmp + `replace`, swallow `OSError` like `put`.
- `max_age=None` returns the blob at any age (stale-if-error path). Missing or corrupt file → `None`.
- Tests: roundtrip, `max_age` expiry, stale read with `max_age=None`, corrupt file → `None`. Monkeypatch `BLOB_DIR` the way existing tests patch `CACHE_FILE`.

### Step 2 — `chainq/catalog.py`

Data model:

```python
@dataclass(frozen=True)
class CatalogToken:
    network: str
    address: str          # checksummed on EVM, base58 on Solana
    symbol: str
    name: str
    decimals: int | None
    source: str           # "registry" | "coingecko" | "aave" | "pendle" | "jupiter"
    kind: str = "token"   # "token" | "atoken" | "stata" | "pt" | "yt" | "sy" | "lp"
    coingecko_id: str | None = None
```

Sources (module constants, verified above):

- `COINGECKO_LIST_URL = "https://tokens.coingecko.com/{platform}/all.json"`, platform from `coingecko_data.PLATFORM_IDS` (add `"robinhood": "robinhood"` there — confirm live that `/coins/robinhood/contract/<addr>` on the API uses the same slug; if it does not, keep a separate `LIST_SLUGS` override in `catalog.py` rather than breaking `by_contract`).
- `AAVE_LIST_URL`, `PENDLE_ASSETS_URL = ".../core/v1/{chain_id}/assets/all"` with `PENDLE_CHAIN_IDS = frozenset({1, 56, 143, 999, 4663, 8453, 9745, 42161, 10, 146, 5000, 80094})` (196 X Layer is not a chainq network).
- `JUPITER_VERIFIED_URL` for Solana.
- Pendle `baseType` → `kind`: `PT`, `YT`, `SY`, `PENDLE_LP` → `lp`; skip `GENERIC`, `NATIVE`, `IB` (already in CoinGecko or not user-held). Keep Pendle `price.usd` in a side map `PENDLE_PRICES[(network, address)]` for the pricing fallback in Step 4.
- Aave `tags` → `kind`: `aTokenV3`/`aTokenV2` → `atoken`; `stataToken`/`staticAT` → `stata`; `underlying` → skip (CoinGecko has them).

Loading:

- `_fetch_json(url) -> object | None` via `chainq.http.get` with `timeout=settings.http_timeout`, `User-Agent: chainq/<version>`; any exception or non-200 → `None`. **Never raises.**
- `_load_source(name, url, ttl=86400)`: `cache.get_blob(name, ttl)` → fresh hit; else fetch; on fetch failure return `cache.get_blob(name)` (stale) or `None`. Names: `catalog-coingecko-{network}`, `catalog-aave`, `catalog-pendle-{chain_id}`, `catalog-jupiter`.
- `tokens_for(network_key) -> list[CatalogToken]`, memoised per process:
  1. curated registry entries first (`source="registry"`, `decimals=None` because the registry does not store decimals; the sweep resolves them lazily, see Step 3).
  2. CoinGecko list, then Aave, then Pendle; **dedupe by address** — first source wins, so a registry USDC keeps its curated symbol.
  3. Solana: curated `SOLANA_TOKENS` then Jupiter verified (`id`, `symbol`, `name`, `decimals`).
  4. Skip entries with missing/invalid address, non-integer decimals, or decimals > 36; EVM addresses are stored checksummed.
- `lookup(network_key, address) -> CatalogToken | None` — case-insensitive on EVM.
- `resolve_symbol(network_key, symbol) -> list[CatalogToken]` — curated match returns exactly that one; otherwise all catalog entries whose `symbol.lower()` matches. Callers decide what to do with 0 / 1 / many.
- `search(query, network_key=None, limit=20) -> list[CatalogToken]` — substring match on symbol or name; exact symbol matches first, then registry-sourced, then the rest in catalog order.
- `refresh(network_keys)` — deletes the blob files and reloads.
- `status() -> list[dict]` — per network: token count, sources present, `fetched_at`, `stale: bool`.

Wire into `chainq/tokens.py::resolve_token`: after the curated miss and before the error, call `catalog.resolve_symbol`; 1 match → its address; >1 → `ChainqError("'{coin}' is ambiguous on {net}: SYMBOL 0xabc… (Name), … — pass the contract address")` listing up to 5; 0 → the existing error, now suggesting `chainq tokens search`. Same for Solana via mints.

### Step 3 — Chunked sweep

In `chainq/rpc.py`:

- `multicall(client, calls, chunk=1000)`: split into chunks; each chunk is one `aggregate3`; on any exception with `chunk > 100`, retry that chunk with `chunk // 2` (recursive); below that, re-raise. Results are concatenated in order. Existing callers pass < 1000 calls and are unaffected.
- `sweep_catalog(client, address, tokens: list[CatalogToken]) -> (wei, rows)`: one `getEthBalance` + one `balanceOf` per token (chunk 1,500 — measured safe; the halving fallback covers RPCs with lower caps). For hits whose `decimals is None` or whose source is `registry`, do a second small multicall for `decimals` + `symbol` (this is what makes the curated-only fallback still work with no list downloaded). Row shape stays compatible with today's `sweep_balances` rows plus `catalog: CatalogToken`.
- Keep `sweep_balances` unchanged (used by `_scan_evm_legacy` and tests).

### Step 4 — Pricing

- `chainq/providers/defillama.py`: `LLAMA_CHAIN_SLUGS` (verified 2026-09-09): `ethereum→ethereum, arbitrum→arbitrum, base→base, optimism→optimism, polygon→polygon, bsc→bsc, avalanche→avax, gnosis→xdai, unichain→unichain, linea→linea, scroll→scroll, zksync→era, mantle→mantle, blast→blast, sonic→sonic, berachain→berachain, worldchain→wc, ink→ink, soneium→soneium, celo→celo, sei→sei, hyperevm→hyperliquid, monad→monad, plasma→plasma, katana→katana`. `robinhood` is unverified — probe `coins.llama.fi/prices/current/robinhood:<listed addr>` live; if nothing comes back, leave it out (falls through to DexScreener/unpriced). `token_prices(pairs: list[tuple[network, address]]) -> dict[(network, address), {"price": float, "confidence": float}]` — batches of 80 ids per GET, `ttl=60` through `cache`, drops entries with `confidence < 0.5`, never raises (returns what it has).
- `chainq/providers/jupiter.py`: `prices(mints) -> dict[mint, {"price", "liquidity"}]` from `price/v3`, batches of 50, `ttl=60`, never raises.
- `chainq/providers/uniswap.py`: `token_pairs_batch(chain_slug, addresses)` over `tokens/v1/{chain}/{a,b,…}` in groups of 30; extend `uniswap_data.CHAIN_SLUGS` with the DexScreener slugs for the remaining networks **only where verified live** (`curl https://api.dexscreener.com/tokens/v1/<slug>/<listed addr>` returns a pair) — otherwise leave the network out; DexScreener is a fallback, not a requirement.
- New `chainq/pricing.py`: `price_assets(assets: list[dict]) -> None` mutating in place, used by both `portfolio` and `address`:
  1. natives + assets with a `coingecko_id` → `coingecko.simple_price` (unchanged behaviour for today's registry tokens);
  2. remaining EVM → DefiLlama; remaining Solana → Jupiter;
  3. still unpriced Pendle kinds → `PENDLE_PRICES` (source `pendle`, flagged `stale_price: True` when the blob is older than 1h);
  4. still unpriced, EVM only, in networks with a DexScreener slug → `token_pairs_batch`; take the deepest pool; require `liquidity.usd >= 1000`;
  5. leftovers stay `price_usd: None`.
  Each asset gets `price_source` (`coingecko` | `defillama` | `jupiter` | `pendle` | `dexscreener` | `None`). All provider calls are wrapped so a provider outage degrades to unpriced, never to a crash.

### Step 5 — Commands

`portfolio`:
- `_scan_evm` → `catalog.tokens_for(net.key)` + `sweep_catalog`; the asset dict gains `kind`, `source`, `name`. `_scan_evm_legacy` stays as the exception path.
- `_scan_solana` → name/decimals via `catalog.lookup("solana", mint)`; unknown mints keep `short_addr` naming but are now **hidden by default** (see below).
- `_priced` → `pricing.price_assets`.
- Flags: `--min-usd` default `1.0`; new `--all` ("show unpriced and sub-floor assets too"); `--hide-unpriced` kept, help text `"(default) drop assets with no known USD price; --all overrides"`. Visibility rule: an asset is shown when `value_usd >= min_usd`, or when `--all`; natives are always shown; unpriced assets are shown only with `--all`. `hidden_assets` counts everything filtered; the footer line reads `(N asset(s) hidden: below $1 or unpriced; --all shows them)`.
- Verbose line: `scanned N network(s), catalog tokens: X (coingecko Y, aave Z, pendle W)`.
- `--json` adds `price_source`, `kind`, `source` per asset; no existing key changes.

`address`:
- `_holdings` → same sweep + `price_assets`; keep top-5 render; unpriced hits are excluded from the render and JSON `holdings` but counted in a new `holdings_hidden` key.
- `_solana_address` → `known_tokens` becomes every catalog-named mint (was registry-only).

`balance`:
- `--coin` symbol path already goes through `resolve_token`; after resolving, if `SYMBOL_TO_ID` misses, price via `price_assets` on a one-element list so `-c basecat -n base` shows a USD value; verbose `price used:` shows the source.

`uniswap`:
- `pools` and `_resolve_pool_token` → `catalog.resolve_symbol`; ambiguity → the same `ChainqError` shape as `resolve_token` (factor a helper `catalog.resolve_one(network, symbol)` that applies the 0/1/many rule and raises, used by `tokens.py` and `uniswap.py`).

New `chainq tokens` group (`chainq/commands/tokens.py`, mounted as `app.add_typer(tokens.app, name="tokens")`):
- `tokens search <query> [-n network] [-l 20]` — rows `network, symbol, name, address, decimals, kind, source`; default text one line per row with dim address and source; `-q` prints addresses; `--json` the rows.
- `tokens refresh [-n network]` — force re-download; prints per-network counts and `fetched_at`.
- `tokens status` — the `catalog.status()` table (counts, age, stale flag).
All three honour the full output contract.

### Step 6 — Docs, version, plans

- `pyproject.toml` → `0.20.0`.
- `skills/chainq/SKILL.md`: replace "known tokens" / "registry tokens" wording with the catalog; document `--all`, the $1 default floor, the ambiguity error, `tokens search|refresh|status`, and the recipe "unknown symbol → `chainq tokens search`". Update the Solana lines (unknown mints hidden by default, `--all` reveals).
- `README.md`: one `tokens search` example, adjust the `portfolio` line.
- `ROADMAP.md`: move "auto token lists per network" out of Next into Status; add "explorer-based holder discovery" to Later as deliberately not done.
- `plans/README.md`: status row + rejected finding for Blockscout discovery.
- Regenerate `site/public/llms-full.txt` (`pnpm --dir site build` runs `scripts/gen-llms-full.mjs` as `prebuild`) since SKILL.md changed.

## Test plan

Unit (no network — `tests/test_catalog.py`):
- parsing fixtures for each source shape (CoinGecko, Aave, Pendle, Jupiter) → `CatalogToken` with correct `kind`, checksummed address, dedupe order (registry beats CoinGecko beats Aave beats Pendle);
- `resolve_symbol` 0 / 1 / many and `resolve_one` error text listing candidates;
- `search` ordering (exact symbol first, registry first);
- stale-if-error: fetch stub raises, stale blob present → returned; no blob → curated-only list;
- `multicall` chunking and halving (stub `aggregate3` that raises above N calls);
- `pricing.price_assets` cascade with stubbed providers, including `confidence < 0.5` drop and the DexScreener liquidity floor;
- portfolio visibility rule (`--all`, floor, natives always shown).
- `tests/test_cli_registration.py`: `tokens search|refresh|status` registered.

Live (`pytest -m live` additions and manual):
- `uv run chainq portfolio vitalik.eth -n base` → includes at least 20 assets, no asset with `price_usd: None` unless `--all`, total > $1k.
- `uv run chainq portfolio vitalik.eth -n base --all --json | jq '.hidden_assets'` → 0 while the non-`--all` run reports a large count.
- `uv run chainq balance vitalik.eth -c basecat -n base` → USD value present, source `defillama`.
- `uv run chainq balance 0x… -c usdc -n base` → still the curated canonical address (checksum unchanged from `TOKENS`).
- A deliberately ambiguous symbol on Ethereum (find one with `tokens search`) → exit 1, candidates listed.
- `uv run chainq portfolio toly.sol` → named long-tail mints, prices from `jupiter`.
- `uv run chainq address vitalik.eth -n base` → top 5 by value, `holdings_hidden` > 0 in `--json`.
- `uv run chainq portfolio vitalik.eth` (all networks) completes in < 30s on the first attempt with a warm catalog; report the cold-cache time too.
- Offline check: `CHAINQ_HTTP_TIMEOUT=0.001 uv run chainq portfolio vitalik.eth -n base` with an **empty** blob dir still prints the curated-registry sweep (no crash, exit 0).

## Done criteria

- BASECAT-class tokens show in `portfolio`/`address` on every network that has a CoinGecko list, with a USD value, without any per-network configuration.
- No spam in default output: every shown non-native asset either has a price from CoinGecko/DefiLlama/Jupiter/Pendle or a DexScreener pool with ≥ $1k liquidity, and is worth ≥ `--min-usd`.
- Curated resolutions are byte-identical to today (`usdc`, `usdt`, `weth`, … on every registered network).
- `resolve_token` never guesses on ambiguity.
- Catalog outage (any or all sources) degrades to today's behaviour; no command gains a new hard dependency.
- `ruff` clean, `pytest -q` passes, live checks above pass, SKILL/README/ROADMAP/plans updated, version `0.20.0`.

## STOP conditions

- A public RPC in the fallback list rejects `balanceOf` sweeps even at chunk 100 for a network (report which; do not silently drop the network).
- CoinGecko token lists start requiring a key or return 403 for the standard slugs.
- DefiLlama prices disagree with CoinGecko by > 5% for a curated stablecoin or WETH on any network during live checks (points to a wrong chain slug).
- The Aave or Pendle feed shape differs from the fixtures captured in `tests/test_catalog.py` at execution time.
- Any existing test that passed at `0b8ccc3` fails for a reason other than a deliberately changed default (`--min-usd`, unpriced hidden).

## Maintenance notes

- Catalog TTL is 24h; `chainq tokens refresh` is the escape hatch after a fresh listing. `CHAINQ_NO_UPDATE_CHECK` does not affect the catalog.
- `PLATFORM_IDS` now doubles as the token-list slug map; a new network needs its CoinGecko platform slug verified against `tokens.coingecko.com/<slug>/all.json` and its DefiLlama slug against `coins.llama.fi`.
- Pendle chain ids are a frozen set; re-check `/core/v1/chains` when adding networks.
- The curated `TOKENS` registry remains the canonical-address overlay. Add a token there only when its symbol is contested (multiple catalog entries) and one is clearly canonical.
