import base64
import hashlib
import os
from decimal import Decimal

import httpx

from chainq import http
from chainq.errors import ChainqError
from chainq.networks import NETWORKS, Network

LAMPORTS_PER_SOL = 10**9
BASE_FEE_LAMPORTS = 5000
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
NAME_PROGRAM_ID = "namesLPneVptA9Z5rqUDD9tMTWEJwofgaYwp8cawRkX"
SOL_TLD_AUTHORITY = "58PwtjSDuFHuUkYjH9BYnnQKHfwo9reZhC2zMJv9JPkx"
SNS_PROXY_URL = "https://sns-sdk-proxy.bonfida.workers.dev"

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BASE58_INDEX = {c: i for i, c in enumerate(BASE58_ALPHABET)}


def base58_decode(value: str) -> bytes:
    num = 0
    for char in value:
        digit = _BASE58_INDEX.get(char)
        if digit is None:
            raise ValueError(f"invalid base58 character '{char}'")
        num = num * 58 + digit
    raw = num.to_bytes((num.bit_length() + 7) // 8, "big")
    pad = len(value) - len(value.lstrip("1"))
    return b"\x00" * pad + raw


def base58_encode(raw: bytes) -> str:
    num = int.from_bytes(raw, "big")
    encoded = ""
    while num:
        num, rem = divmod(num, 58)
        encoded = BASE58_ALPHABET[rem] + encoded
    pad = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * pad + encoded


_ED25519_P = 2**255 - 19
_ED25519_D = (-121665 * pow(121666, _ED25519_P - 2, _ED25519_P)) % _ED25519_P


def _is_on_curve(point: bytes) -> bool:
    y = int.from_bytes(point, "little") & ((1 << 255) - 1)
    if y >= _ED25519_P:
        return False
    y2 = y * y % _ED25519_P
    x2 = (y2 - 1) * pow(_ED25519_D * y2 + 1, _ED25519_P - 2, _ED25519_P) % _ED25519_P
    return x2 == 0 or pow(x2, (_ED25519_P - 1) // 2, _ED25519_P) == 1


def find_program_address(seeds: list[bytes], program_id: str) -> str:
    for bump in range(255, -1, -1):
        data = b"".join(seeds) + bytes([bump]) + base58_decode(program_id) + b"ProgramDerivedAddress"
        digest = hashlib.sha256(data).digest()
        if not _is_on_curve(digest):
            return base58_encode(digest)
    raise ChainqError(f"no valid program-derived address for {program_id}")


def sns_domain_key(domain: str) -> str:
    hashed = hashlib.sha256(b"SPL Name Service" + domain.encode()).digest()
    return find_program_address([hashed, b"\x00" * 32, base58_decode(SOL_TLD_AUTHORITY)], NAME_PROGRAM_ID)


def resolve_sol_domain(name: str) -> str:
    domain = name.strip().lower().removesuffix(".sol")
    try:
        resp = http.get(f"{SNS_PROXY_URL}/resolve/{domain}")
        if resp.status_code < 400:
            payload = resp.json()
            if payload.get("s") == "ok" and is_solana_address(payload.get("result") or ""):
                return payload["result"]
            if payload.get("result") == "Domain not found":
                raise ChainqError(f"could not resolve SNS domain '{name}' (not registered)")
    except ChainqError:
        raise
    except Exception:
        pass
    data = account_data(sns_domain_key(domain))
    if data is None or len(data) < 64:
        raise ChainqError(f"could not resolve SNS domain '{name}'")
    return base58_encode(data[32:64])


def is_solana_address(value: str) -> bool:
    if not 32 <= len(value) <= 44:
        return False
    try:
        return len(base58_decode(value)) == 32
    except ValueError:
        return False


def resolve_solana_address(value: str) -> str:
    value = value.strip()
    if value.lower().endswith(".sol"):
        return resolve_sol_domain(value)
    if not is_solana_address(value):
        raise ChainqError(f"invalid Solana address '{value}' (expected a base58 pubkey or .sol domain)")
    return value


def looks_like_solana(value: str) -> bool:
    value = value.strip()
    if value.lower().endswith(".sol"):
        return True
    return not value.lower().endswith(".eth") and is_solana_address(value)


def network() -> Network:
    return NETWORKS["solana"]


def rpc_call(method: str, params: list | None = None) -> object:
    net = network()
    urls = list(net.rpc_urls)
    override = os.environ.get("CHAINQ_RPC_SOLANA")
    if override:
        urls.insert(0, override)
    failures = []
    for url in urls:
        try:
            resp = http.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []})
        except httpx.HTTPError as exc:
            failures.append(f"{url} ({type(exc).__name__})")
            continue
        if resp.status_code >= 400:
            failures.append(f"{url} (HTTP {resp.status_code})")
            continue
        payload = resp.json()
        if "error" in payload:
            failures.append(f"{url} ({payload['error'].get('message', payload['error'])})")
            continue
        return payload.get("result")
    raise ChainqError(f"all Solana RPC endpoints failed for {method}: {'; '.join(failures)}")


def get_balance(pubkey: str) -> int:
    return rpc_call("getBalance", [pubkey])["value"]


def lamports_to_sol(lamports: int) -> Decimal:
    return Decimal(lamports) / Decimal(LAMPORTS_PER_SOL)


def token_accounts(owner: str) -> list[dict]:
    accounts = []
    for program_id in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID):
        result = rpc_call(
            "getTokenAccountsByOwner", [owner, {"programId": program_id}, {"encoding": "jsonParsed"}]
        )
        for entry in result.get("value") or []:
            info = entry["account"]["data"]["parsed"]["info"]
            amount = info.get("tokenAmount") or {}
            accounts.append(
                {
                    "mint": info.get("mint"),
                    "amount": amount.get("uiAmountString") or "0",
                    "raw_amount": int(amount.get("amount") or 0),
                    "decimals": amount.get("decimals"),
                }
            )
    return accounts


def token_balance(owner: str, mint: str) -> dict | None:
    result = rpc_call("getTokenAccountsByOwner", [owner, {"mint": mint}, {"encoding": "jsonParsed"}])
    total_raw = 0
    decimals = None
    for entry in result.get("value") or []:
        amount = entry["account"]["data"]["parsed"]["info"].get("tokenAmount") or {}
        total_raw += int(amount.get("amount") or 0)
        decimals = amount.get("decimals")
    if decimals is None:
        return None
    return {"mint": mint, "raw_amount": total_raw, "decimals": decimals}


def account_info(pubkey: str) -> dict | None:
    return rpc_call("getAccountInfo", [pubkey, {"encoding": "jsonParsed"}]).get("value")


def account_data(pubkey: str) -> bytes | None:
    value = rpc_call("getAccountInfo", [pubkey, {"encoding": "base64"}]).get("value")
    if value is None:
        return None
    return base64.b64decode(value["data"][0])


def program_data_header(programdata: str) -> tuple[str | None, int | None]:
    value = rpc_call(
        "getAccountInfo", [programdata, {"encoding": "base64", "dataSlice": {"offset": 0, "length": 45}}]
    ).get("value")
    if value is None:
        return None, None
    raw = base64.b64decode(value["data"][0])
    if len(raw) < 13:
        return None, None
    slot = int.from_bytes(raw[4:12], "little")
    authority = base58_encode(raw[13:45]) if raw[12] == 1 and len(raw) >= 45 else None
    return authority, slot


def get_transaction(signature: str) -> dict | None:
    return rpc_call(
        "getTransaction", [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    )


def recent_prioritization_fees() -> list[int]:
    return [entry.get("prioritizationFee", 0) for entry in rpc_call("getRecentPrioritizationFees", []) or []]


def is_signature(value: str) -> bool:
    if not 80 <= len(value) <= 90:
        return False
    try:
        return len(base58_decode(value)) == 64
    except ValueError:
        return False


SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"
PROGRAM_LABELS = {
    SYSTEM_PROGRAM_ID: "System",
    TOKEN_PROGRAM_ID: "SPL Token",
    TOKEN_2022_PROGRAM_ID: "Token-2022",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "Associated Token Account",
    "ComputeBudget111111111111111111111111111111": "Compute Budget",
    "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr": "Memo",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter v6",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "pump.fun",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "PumpSwap",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM v4",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium CLMM",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpool",
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "Meteora DLMM",
    "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD": "Kamino Lend",
}
SYSTEM_TRANSFERS = ("transfer", "transferWithSeed")
TOKEN_TRANSFERS = ("transfer", "transferChecked")
TOKEN_PROGRAMS = ("spl-token", "spl-token-2022")


def account_keys(txn: dict) -> list[str]:
    keys = ((txn.get("transaction") or {}).get("message") or {}).get("accountKeys") or []
    return [key.get("pubkey") if isinstance(key, dict) else key for key in keys]


def instructions(txn: dict) -> list[dict]:
    message = (txn.get("transaction") or {}).get("message") or {}
    groups = (txn.get("meta") or {}).get("innerInstructions") or []
    inner = {group.get("index"): group.get("instructions") or [] for group in groups}
    flat = []
    for index, ix in enumerate(message.get("instructions") or []):
        flat.append(ix)
        flat.extend(inner.get(index, []))
    return flat


def _token_account_map(txn: dict) -> dict[str, dict]:
    keys = account_keys(txn)
    meta = txn.get("meta") or {}
    accounts: dict[str, dict] = {}
    for balance in (meta.get("preTokenBalances") or []) + (meta.get("postTokenBalances") or []):
        index = balance.get("accountIndex")
        if index is None or index >= len(keys):
            continue
        accounts[keys[index]] = {
            "mint": balance.get("mint"),
            "owner": balance.get("owner"),
            "decimals": (balance.get("uiTokenAmount") or {}).get("decimals"),
        }
    return accounts


def _first(*values: object) -> object:
    return next((value for value in values if value is not None), None)


def decode_transfers(txn: dict) -> list[dict]:
    accounts = _token_account_map(txn)
    rows = []
    for ix in instructions(txn):
        parsed = ix.get("parsed")
        if not isinstance(parsed, dict):
            continue
        kind, info, program = parsed.get("type"), parsed.get("info") or {}, ix.get("program")
        if program == "system" and kind in SYSTEM_TRANSFERS:
            rows.append(
                {
                    "mint": None,
                    "raw_amount": int(info.get("lamports") or 0),
                    "decimals": 9,
                    "from": info.get("source"),
                    "to": info.get("destination"),
                }
            )
        elif program in TOKEN_PROGRAMS and kind in TOKEN_TRANSFERS:
            source = accounts.get(info.get("source"), {})
            destination = accounts.get(info.get("destination"), {})
            token_amount = info.get("tokenAmount") or {}
            rows.append(
                {
                    "mint": _first(info.get("mint"), source.get("mint"), destination.get("mint")),
                    "raw_amount": int(_first(token_amount.get("amount"), info.get("amount")) or 0),
                    "decimals": _first(token_amount.get("decimals"), source.get("decimals"), destination.get("decimals")),
                    "from": _first(source.get("owner"), info.get("authority"), info.get("source")),
                    "to": _first(destination.get("owner"), info.get("destination")),
                }
            )
    return rows


def owner_token_changes(txn: dict, owner: str) -> list[dict]:
    meta = txn.get("meta") or {}
    totals: dict[str, list] = {}
    for sign, key in ((-1, "preTokenBalances"), (1, "postTokenBalances")):
        for balance in meta.get(key) or []:
            if balance.get("owner") != owner:
                continue
            amount = balance.get("uiTokenAmount") or {}
            entry = totals.setdefault(balance.get("mint"), [0, amount.get("decimals") or 0])
            entry[0] += sign * int(amount.get("amount") or 0)
    return [
        {"mint": mint, "raw_change": raw, "decimals": decimals}
        for mint, (raw, decimals) in totals.items()
        if raw
    ]


def priority_fee_lamports(txn: dict) -> int:
    signatures = len((txn.get("transaction") or {}).get("signatures") or []) or 1
    return max(int((txn.get("meta") or {}).get("fee") or 0) - BASE_FEE_LAMPORTS * signatures, 0)


def main_instruction(txn: dict) -> str | None:
    message = (txn.get("transaction") or {}).get("message") or {}
    for ix in message.get("instructions") or []:
        program_id = ix.get("programId")
        if PROGRAM_LABELS.get(program_id) == "Compute Budget":
            continue
        label = PROGRAM_LABELS.get(program_id) or program_id
        parsed = ix.get("parsed")
        kind = parsed.get("type") if isinstance(parsed, dict) else None
        return f"{label} {kind}" if kind else label
    return None
