import hashlib
import os
from decimal import Decimal

import httpx
from eth_abi import decode as abi_decode

from chainq import cache, http
from chainq.config import settings
from chainq.errors import ChainqError
from chainq.networks import NETWORKS, Network
from chainq.solana import BASE58_ALPHABET, base58_decode, base58_encode

SUN_PER_TRX = 10**6
ADDRESS_PREFIX = 0x41
TRONGRID_URL = "https://api.trongrid.io"
TRONSCAN_URL = "https://tronscan.org/#"
USDT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
GASFREE_CONTROLLER = "TFFAMQLZybALaLb4uxHA9RBE7pxhUAjF3U"
TRANSFER_TOPIC = "ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
GASFREE_TRANSFER_TOPIC = "fe6f7f8574ad66f5a9001635fa07c426dbed515866253867ebd1ca6ac43f0d12"
USDT_REFERENCE_SENDER = "TKHuVq1oKVruCGLvqVexFs6dawKv6fQgFs"
USDT_REFERENCE_RECEIVER = "TJCo98saj6WND61g1uuKwJ9GMWMT9WkJFo"
TRX_TRANSFER_BANDWIDTH = 268
TRC20_TRANSFER_BANDWIDTH = 345
DECIMALS_TTL = 7 * 86400
PARAMS_TTL = 300


def _checksum(payload: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]


def _decode(address: str) -> bytes:
    raw = base58_decode(address)
    if len(raw) != 25 or raw[0] != ADDRESS_PREFIX or _checksum(raw[:21]) != raw[21:]:
        raise ValueError(f"invalid Tron address '{address}'")
    return raw[:21]


def _is_hex(value: str) -> bool:
    return all(c in "0123456789abcdefABCDEF" for c in value)


def is_tron_address(value: str) -> bool:
    value = value.strip()
    if not (value.startswith("T") and len(value) == 34):
        return False
    try:
        _decode(value)
    except ValueError:
        return False
    return True


def is_tron_hex(value: str) -> bool:
    value = value.strip()
    return len(value) == 42 and value[:2] == "41" and _is_hex(value)


def looks_like_tron(value: str) -> bool:
    value = value.strip()
    shaped = value.startswith("T") and len(value) == 34 and all(c in BASE58_ALPHABET for c in value)
    return shaped or is_tron_hex(value)


def from_hex(value: str) -> str:
    raw = bytes.fromhex(value.strip().removeprefix("0x"))
    if len(raw) == 32:
        raw = raw[-20:]
    if len(raw) == 20:
        raw = bytes([ADDRESS_PREFIX]) + raw
    if len(raw) != 21 or raw[0] != ADDRESS_PREFIX:
        raise ChainqError(f"'{value}' is not a Tron address in hex form (41 + 20 bytes)")
    return base58_encode(raw + _checksum(raw))


def to_hex(address: str) -> str:
    return _decode(address).hex()


def resolve_tron_address(value: str) -> str:
    value = value.strip()
    if is_tron_address(value):
        return value
    if looks_like_tron(value) and not is_tron_hex(value):
        raise ChainqError(f"invalid Tron address '{value}' (bad base58check checksum)")
    if is_tron_hex(value):
        return from_hex(value)
    if value.startswith("0x") and len(value) == 42 and _is_hex(value[2:]):
        return from_hex(value)
    raise ChainqError(f"invalid Tron address '{value}' (expected base58 T…, hex 41…, or a 0x address)")


def encode_address(address: str) -> str:
    return to_hex(address)[2:].rjust(64, "0")


def encode_uint(value: int) -> str:
    return f"{value:064x}"


def explorer_tx(txid: str) -> str:
    return f"{TRONSCAN_URL}/transaction/{txid}"


def explorer_address(address: str) -> str:
    return f"{TRONSCAN_URL}/address/{address}"


def network() -> Network:
    return NETWORKS["tron"]


def sun_to_trx(sun: int) -> Decimal:
    return Decimal(sun) / Decimal(SUN_PER_TRX)


def _urls() -> list[str]:
    urls = list(network().rpc_urls)
    if not settings.trongrid_api_key:
        urls.sort(key=lambda url: url == TRONGRID_URL)
    override = os.environ.get("CHAINQ_RPC_TRON")
    if override:
        urls.insert(0, override.rstrip("/"))
    return urls


def _headers(url: str) -> dict:
    key = settings.trongrid_api_key
    return {"TRON-PRO-API-KEY": key} if key and url.startswith(TRONGRID_URL) else {}


def _post(url: str, body: object) -> tuple[object | None, str | None]:
    try:
        resp = http.post(url, json=body, headers=_headers(url))
    except httpx.HTTPError as exc:
        return None, type(exc).__name__
    if resp.status_code >= 400:
        return None, f"HTTP {resp.status_code}"
    try:
        payload = resp.json()
    except ValueError:
        return None, "non-JSON response"
    if isinstance(payload, dict) and "Error" in payload:
        return None, str(payload["Error"])[:120]
    return payload, None


def api(path: str, body: dict | None = None) -> dict:
    failures = []
    for url in _urls():
        payload, error = _post(f"{url}/{path.lstrip('/')}", body or {})
        if error is None:
            return payload
        failures.append(f"{url} ({error})")
    raise ChainqError(f"all Tron endpoints failed for {path}: {'; '.join(failures)}")


def rpc_call(method: str, params: list | None = None) -> object:
    failures = []
    for url in _urls():
        payload, error = _post(f"{url}/jsonrpc", {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []})
        if error is None and isinstance(payload, dict) and "error" in payload:
            error = str(payload["error"].get("message", payload["error"]))
        if error is None:
            return payload.get("result")
        failures.append(f"{url} ({error})")
    raise ChainqError(f"all Tron JSON-RPC endpoints failed for {method}: {'; '.join(failures)}")


def trongrid_get(path: str, params: dict | None = None) -> dict | None:
    try:
        resp = http.get(f"{TRONGRID_URL}{path}", params=params or {}, headers=_headers(TRONGRID_URL))
    except httpx.HTTPError:
        return None
    if resp.status_code >= 400:
        return None
    try:
        payload = resp.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) and payload.get("success") else None


def get_account(address: str) -> dict:
    return api("wallet/getaccount", {"address": address, "visible": True})


def account_resource(address: str) -> dict:
    return api("wallet/getaccountresource", {"address": address, "visible": True})


def get_contract(address: str) -> dict:
    return api("wallet/getcontract", {"value": address, "visible": True})


def staked_sun(account: dict) -> int:
    frozen = sum(int(entry.get("amount") or 0) for entry in account.get("frozenV2") or [])
    delegated = int(account.get("delegated_frozenV2_balance_for_bandwidth") or 0)
    delegated += int((account.get("account_resource") or {}).get("delegated_frozenV2_balance_for_energy") or 0)
    unfreezing = sum(int(entry.get("unfreeze_amount") or 0) for entry in account.get("unfrozenV2") or [])
    return frozen + delegated + unfreezing


def _revert_message(result: dict) -> str:
    message = (result.get("result") or {}).get("message") or ""
    try:
        return bytes.fromhex(message).decode("utf-8", errors="replace") or "reverted"
    except ValueError:
        return message or "reverted"


def constant_call(contract: str, selector: str, args: list[str] | None = None, owner: str | None = None) -> tuple[bytes, int]:
    body = {
        "owner_address": owner or contract,
        "contract_address": contract,
        "function_selector": selector,
        "parameter": "".join(args or []),
        "visible": True,
    }
    result = api("wallet/triggerconstantcontract", body)
    if not (result.get("result") or {}).get("result"):
        raise ChainqError(f"call {selector} on {contract} failed: {_revert_message(result)}")
    output = (result.get("constant_result") or [""])[0]
    return bytes.fromhex(output), int(result.get("energy_used") or 0)


def decode_string(data: bytes) -> str:
    try:
        return abi_decode(["string"], data)[0]
    except Exception:
        return data[:32].rstrip(b"\x00").decode("utf-8", errors="replace")


def _uint(data: bytes) -> int:
    return int.from_bytes(data[:32], "big") if data else 0


def trc20_balance(token: str, owner: str) -> int:
    data, _ = constant_call(token, "balanceOf(address)", [encode_address(owner)])
    return _uint(data)


def trc20_decimals(token: str) -> int:
    key = cache.key_for("tron-decimals", token)
    cached = cache.get(key)
    if isinstance(cached, int):
        return cached
    data, _ = constant_call(token, "decimals()")
    if not data:
        raise ChainqError(f"{token} does not look like a TRC-20 token")
    decimals = _uint(data)
    cache.put(key, decimals, DECIMALS_TTL)
    return decimals


def trc20_symbol(token: str) -> str | None:
    try:
        data, _ = constant_call(token, "symbol()")
    except ChainqError:
        return None
    return decode_string(data) if data else None


def trc20_profile(token: str) -> dict | None:
    try:
        symbol = constant_call(token, "symbol()")[0]
        decimals = constant_call(token, "decimals()")[0]
        supply = constant_call(token, "totalSupply()")[0]
        name = constant_call(token, "name()")[0]
    except ChainqError:
        return None
    if not symbol or not decimals or not supply:
        return None
    dec = _uint(decimals)
    if dec > 36:
        return None
    return {
        "name": decode_string(name) if name else None,
        "symbol": decode_string(symbol),
        "decimals": dec,
        "total_supply": str(Decimal(_uint(supply)) / Decimal(10**dec)),
    }


def trc20_holdings(address: str) -> dict[str, int] | None:
    payload = trongrid_get(f"/v1/accounts/{address}")
    if payload is None:
        return None
    rows = payload.get("data") or []
    holdings: dict[str, int] = {}
    for entry in (rows[0].get("trc20") or []) if rows else []:
        for token, raw in entry.items():
            if is_tron_address(token) and int(raw or 0):
                holdings[token] = int(raw)
    return holdings


def is_txid(value: str) -> bool:
    value = value.strip().removeprefix("0x")
    return len(value) == 64 and _is_hex(value)


def get_transaction(txid: str) -> dict | None:
    result = api("wallet/gettransactionbyid", {"value": txid.strip().removeprefix("0x"), "visible": True})
    return result or None


def get_transaction_info(txid: str) -> dict:
    return api("wallet/gettransactioninfobyid", {"value": txid.strip().removeprefix("0x")})


def chain_parameters() -> dict[str, int]:
    key = cache.key_for("tron-chain-parameters")
    cached = cache.get(key)
    if isinstance(cached, dict):
        return cached
    entries = api("wallet/getchainparameters").get("chainParameter") or []
    params = {entry["key"]: int(entry.get("value") or 0) for entry in entries if "key" in entry}
    cache.put(key, params, PARAMS_TTL)
    return params


def usdt_transfer_energy() -> int | None:
    try:
        _, energy = constant_call(
            USDT,
            "transfer(address,uint256)",
            [encode_address(USDT_REFERENCE_RECEIVER), encode_uint(1)],
            owner=USDT_REFERENCE_SENDER,
        )
    except ChainqError:
        return None
    return energy or None


def gasfree_address(user: str) -> str:
    data, _ = constant_call(GASFREE_CONTROLLER, "getGasFreeAddress(address)", [encode_address(user)])
    return from_hex(data[-20:].hex())


def gasfree_fees(token: str = USDT) -> tuple[int, int]:
    transfer, _ = constant_call(GASFREE_CONTROLLER, "tokenFees(address)", [encode_address(token)])
    activate, _ = constant_call(GASFREE_CONTROLLER, "activateFees(address)", [encode_address(token)])
    return _uint(transfer), _uint(activate)
