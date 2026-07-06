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

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BASE58_INDEX = {c: i for i, c in enumerate(_BASE58_ALPHABET)}


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


def is_solana_address(value: str) -> bool:
    if not 32 <= len(value) <= 44:
        return False
    try:
        return len(base58_decode(value)) == 32
    except ValueError:
        return False


def resolve_solana_address(value: str) -> str:
    value = value.strip()
    if not is_solana_address(value):
        raise ChainqError(f"invalid Solana address '{value}' (expected a base58-encoded 32-byte pubkey)")
    return value


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
