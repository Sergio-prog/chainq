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


def base58_encode(raw: bytes) -> str:
    num = int.from_bytes(raw, "big")
    encoded = ""
    while num:
        num, rem = divmod(num, 58)
        encoded = _BASE58_ALPHABET[rem] + encoded
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
