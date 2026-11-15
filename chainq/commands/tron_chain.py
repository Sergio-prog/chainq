import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal

from chainq import catalog, pricing, tron
from chainq.errors import ChainqError
from chainq.fmt import bold, dim, fmt_amount, fmt_usd, short_addr
from chainq.output import Out
from chainq.providers import fourbyte
from chainq.tokens import TRON_TOKENS, resolve_token

KNOWN_SELECTORS = {
    "a9059cbb": "transfer(address,uint256)",
    "23b872dd": "transferFrom(address,address,uint256)",
    "095ea7b3": "approve(address,uint256)",
    "6f21b898": "permitTransfer(address,address,address,uint256,uint256,uint256,uint256,uint256,bytes)",
}
JSON_RPC_PREFIXES = ("eth_", "net_", "web3_")
TEXT_TRANSFER_LIMIT = 10
SCAN_THREADS = 4
UNKNOWN_TOKEN_LIMIT = 25
GASFREE_SOURCE = "gasfree"


def _trx_price() -> float | None:
    return pricing.native_price("tron")


def _usd(amount: Decimal | None, price: float | None) -> float | None:
    return float(amount) * price if amount is not None and price is not None else None


def _token_meta(token: str) -> tuple[str, int | None]:
    entry = catalog.lookup("tron", token)
    symbol = entry.symbol if entry else None
    decimals = entry.decimals if entry and entry.decimals is not None else None
    if decimals is None:
        try:
            decimals = tron.trc20_decimals(token)
        except ChainqError:
            decimals = None
    return symbol or tron.trc20_symbol(token) or short_addr(token), decimals


def _amount(raw: int, decimals: int | None) -> Decimal:
    return Decimal(raw) / Decimal(10**decimals) if decimals is not None else Decimal(raw)


def balance(address: str, coin: str | None, net) -> tuple[str, Decimal, str, str | None, float | None, str | None]:
    addr = tron.resolve_tron_address(address)
    if coin is None:
        amount = tron.sun_to_trx(int(tron.get_account(addr).get("balance") or 0))
        return addr, amount, "TRX", None, _trx_price(), "coingecko"
    token = resolve_token(coin, net)
    raw = tron.trc20_balance(token, addr)
    symbol, decimals = _token_meta(token)
    if decimals is None:
        raise ChainqError(f"{token} does not look like a TRC-20 token")
    amount = _amount(raw, decimals)
    asset = {"network": "tron", "symbol": symbol, "token_address": token, "amount": str(amount)}
    entry = catalog.lookup("tron", token)
    if entry is not None and entry.coingecko_id:
        asset["coingecko_id"] = entry.coingecko_id
    pricing.price_assets([asset])
    return addr, amount, symbol, token, asset["price_usd"], asset["price_source"]


def _registry_balances(address: str) -> dict[str, int]:
    tokens = list(TRON_TOKENS.values())
    with ThreadPoolExecutor(max_workers=SCAN_THREADS) as pool:
        raws = list(pool.map(lambda token: tron.trc20_balance(token, address), tokens))
    return {token: raw for token, raw in zip(tokens, raws, strict=True) if raw}


def _gasfree_asset(address: str) -> dict | None:
    try:
        holder = tron.gasfree_address(address)
        raw = tron.trc20_balance(tron.USDT, holder)
    except ChainqError:
        return None
    if not raw:
        return None
    return {
        "network": "tron",
        "symbol": "USDT (GasFree)",
        "token_address": tron.USDT,
        "holder": holder,
        "amount": str(_amount(raw, 6)),
        "kind": GASFREE_SOURCE,
        "source": GASFREE_SOURCE,
        "coingecko_id": "tether",
    }


def scan_assets(address: str, account: dict | None = None) -> list[dict]:
    account = tron.get_account(address) if account is None else account
    assets = []
    liquid = int(account.get("balance") or 0)
    if liquid:
        assets.append(
            {
                "network": "tron",
                "symbol": "TRX",
                "token_address": None,
                "amount": str(tron.sun_to_trx(liquid)),
                "coingecko_id": "tron",
            }
        )
    staked = tron.staked_sun(account)
    if staked:
        assets.append(
            {
                "network": "tron",
                "symbol": "TRX (staked)",
                "token_address": None,
                "amount": str(tron.sun_to_trx(staked)),
                "kind": "staked",
                "coingecko_id": "tron",
            }
        )
    holdings = tron.trc20_holdings(address)
    if holdings is None:
        holdings = _registry_balances(address)
    known = [token for token in holdings if catalog.lookup("tron", token)]
    unknown = [token for token in holdings if token not in known][:UNKNOWN_TOKEN_LIMIT]
    tokens = known + unknown
    with ThreadPoolExecutor(max_workers=SCAN_THREADS) as pool:
        metas = list(pool.map(_token_meta, tokens))
    for token, (symbol, decimals) in zip(tokens, metas, strict=True):
        if decimals is None:
            continue
        entry = catalog.lookup("tron", token)
        assets.append(
            {
                "network": "tron",
                "symbol": symbol,
                "token_address": token,
                "amount": str(_amount(holdings[token], decimals)),
                "kind": entry.kind if entry else "unknown",
                "source": entry.source if entry else None,
                "coingecko_id": entry.coingecko_id if entry else None,
            }
        )
    if account.get("type") != "Contract":
        gasfree = _gasfree_asset(address)
        if gasfree is not None:
            assets.append(gasfree)
    return assets


def gas(out: Out, net) -> None:
    params = tron.chain_parameters()
    energy_price = params.get("getEnergyFee", 0)
    bandwidth_price = params.get("getTransactionFee", 0)
    price = _trx_price()
    trx_transfer = tron.sun_to_trx(tron.TRX_TRANSFER_BANDWIDTH * bandwidth_price)
    usdt_energy = tron.usdt_transfer_energy()
    usdt_transfer = (
        tron.sun_to_trx(usdt_energy * energy_price + tron.TRC20_TRANSFER_BANDWIDTH * bandwidth_price)
        if usdt_energy
        else None
    )
    try:
        fee_raw, activate_raw = tron.gasfree_fees()
        gasfree_fee, gasfree_activate = _amount(fee_raw, 6), _amount(activate_raw, 6)
    except ChainqError:
        gasfree_fee = gasfree_activate = None
    data = {
        "network": net.key,
        "energy_price_sun": energy_price,
        "bandwidth_price_sun": bandwidth_price,
        "new_account_fee_trx": str(tron.sun_to_trx(params.get("getCreateAccountFee", 0))),
        "free_bandwidth_per_day": params.get("getFreeNetLimit"),
        "trx_transfer_bandwidth": tron.TRX_TRANSFER_BANDWIDTH,
        "trx_transfer_trx": str(trx_transfer),
        "usdt_transfer_energy": usdt_energy,
        "usdt_transfer_trx": str(usdt_transfer) if usdt_transfer is not None else None,
        "usdt_transfer_usd": _usd(usdt_transfer, price),
        "gasfree_usdt_fee": str(gasfree_fee) if gasfree_fee is not None else None,
        "gasfree_activation_fee": str(gasfree_activate) if gasfree_activate is not None else None,
        "native_price_usd": price,
        "transfer_cost_usd": _usd(trx_transfer, price),
    }
    lines = [f"Tron fees: energy {energy_price} sun, bandwidth {bandwidth_price:,} sun/byte"]
    trx_line = f"  TRX transfer ≈ {fmt_amount(trx_transfer)} TRX"
    if data["transfer_cost_usd"] is not None:
        trx_line += f" (~{fmt_usd(data['transfer_cost_usd'])})"
    lines.append(trx_line + dim(f" — free with {params.get('getFreeNetLimit', 0)} daily bandwidth"))
    if usdt_transfer is not None:
        usdt_line = f"  USDT transfer ≈ {usdt_energy:,} energy = {fmt_amount(usdt_transfer)} TRX"
        if data["usdt_transfer_usd"] is not None:
            usdt_line += f" (~{fmt_usd(data['usdt_transfer_usd'])})"
        lines.append(usdt_line + dim(" — ~2x to a never-funded address"))
    if gasfree_fee is not None:
        lines.append(
            f"  GasFree USDT transfer: {fmt_amount(gasfree_fee)} USDT fee"
            + dim(f" (+{fmt_amount(gasfree_activate)} USDT once to activate), no TRX needed")
        )
    out.emit(
        data,
        lines,
        quiet_value=energy_price,
        verbose_lines=[
            f"usdt energy simulated live: {tron.USDT_REFERENCE_SENDER} → {tron.USDT_REFERENCE_RECEIVER}",
            f"gasfree controller: {tron.GASFREE_CONTROLLER}",
        ],
    )


def _function(data: str) -> str | None:
    if len(data) < 8:
        return None
    selector = data[:8].lower()
    return KNOWN_SELECTORS.get(selector) or fourbyte.signature(f"0x{selector}") or f"0x{selector}"


def _words(data: str) -> list[int]:
    return [int(data[i : i + 64], 16) for i in range(0, len(data) - 63, 64)]


def _decode_transfers(logs: list[dict]) -> list[dict]:
    transfers = [
        log
        for log in logs
        if len(log.get("topics") or []) == 3 and log["topics"][0].lower() == tron.TRANSFER_TOPIC
    ]
    metas = {token: _token_meta(token) for token in {tron.from_hex(log["address"]) for log in transfers}}
    rows = []
    for log in transfers:
        token = tron.from_hex(log["address"])
        symbol, decimals = metas[token]
        raw = int(log.get("data") or "0", 16)
        rows.append(
            {
                "token": token,
                "symbol": symbol,
                "amount": float(_amount(raw, decimals)),
                "from": tron.from_hex(log["topics"][1]),
                "to": tron.from_hex(log["topics"][2]),
            }
        )
    return rows


def _decode_gasfree(logs: list[dict]) -> dict | None:
    controller = tron.to_hex(tron.GASFREE_CONTROLLER)[2:]
    for log in logs:
        topics = log.get("topics") or []
        if log.get("address", "").lower() != controller or len(topics) != 4:
            continue
        if topics[0].lower() != tron.GASFREE_TRANSFER_TOPIC:
            continue
        words = _words(log.get("data") or "")
        if len(words) < 5:
            continue
        token = tron.from_hex(topics[1])
        symbol, decimals = _token_meta(token)
        return {
            "token": token,
            "symbol": symbol,
            "user": tron.from_hex(topics[2]),
            "receiver": tron.from_hex(topics[3]),
            "provider": tron.from_hex(f"{words[0]:064x}"),
            "amount": str(_amount(words[1], decimals)),
            "fee": str(_amount(words[2], decimals)),
            "activate_fee": str(_amount(words[3], decimals)),
            "nonce": words[4],
        }
    return None


def _parties(kind: str, value: dict) -> tuple[str | None, str | None, int]:
    owner = value.get("owner_address")
    if kind == "TriggerSmartContract":
        return owner, value.get("contract_address"), int(value.get("call_value") or 0)
    if kind in ("TransferContract", "TransferAssetContract"):
        return owner, value.get("to_address"), int(value.get("amount") or 0) if kind == "TransferContract" else 0
    target = value.get("receiver_address") or value.get("to_address") or value.get("contract_address")
    amount = value.get("balance") or value.get("frozen_balance") or value.get("unfreeze_balance") or 0
    return owner, target, int(amount)


def _bandwidth_used(receipt: dict) -> int:
    if receipt.get("net_usage"):
        return int(receipt["net_usage"])
    burned = int(receipt.get("net_fee") or 0)
    price = tron.chain_parameters().get("getTransactionFee") if burned else None
    return burned // price if price else 0


def _tx_kind(contract_type: str, function: str | None, gasfree: dict | None) -> str:
    if gasfree is not None:
        return "gasfree_transfer"
    if contract_type == "TransferContract":
        return "trx_transfer"
    if contract_type == "TransferAssetContract":
        return "trc10_transfer"
    if contract_type == "TriggerSmartContract":
        return "trc20_transfer" if function and function.startswith(("transfer(", "transferFrom(")) else "contract_call"
    return contract_type


def tx(out: Out, txid: str, net) -> None:
    if not tron.is_txid(txid):
        raise ChainqError(f"'{txid}' is not a valid Tron transaction id (64 hex chars)")
    txid = txid.strip().removeprefix("0x").lower()
    transaction = tron.get_transaction(txid)
    if transaction is None:
        raise ChainqError(f"transaction {txid} not found on Tron (check the id and --network)")
    info = tron.get_transaction_info(txid)
    contract = (transaction.get("raw_data") or {}).get("contract") or [{}]
    contract_type = contract[0].get("type") or "unknown"
    value = (contract[0].get("parameter") or {}).get("value") or {}
    sender, target, amount_sun = _parties(contract_type, value)
    receipt = info.get("receipt") or {}
    ret = ((transaction.get("ret") or [{}])[0]).get("contractRet")
    result = receipt.get("result") or ret
    status = "pending" if not info else ("success" if result in (None, "SUCCESS") else "failed")
    logs = info.get("log") or []
    function = _function(value.get("data") or "") if contract_type == "TriggerSmartContract" else None
    gasfree = _decode_gasfree(logs)
    transfers = _decode_transfers(logs)
    price = _trx_price()
    amount = tron.sun_to_trx(amount_sun)
    fee = tron.sun_to_trx(int(info.get("fee") or 0)) if info else None
    timestamp = datetime.fromtimestamp(info["blockTimeStamp"] / 1000, tz=UTC) if info.get("blockTimeStamp") else None
    data = {
        "hash": txid,
        "network": net.key,
        "status": status,
        "result": result,
        "type": contract_type,
        "kind": _tx_kind(contract_type, function, gasfree),
        "from": sender,
        "to": target,
        "value": str(amount),
        "value_usd": _usd(amount, price),
        "fee": str(fee) if fee is not None else None,
        "fee_usd": _usd(fee, price),
        "energy_used": receipt.get("energy_usage_total"),
        "energy_fee_trx": str(tron.sun_to_trx(int(receipt.get("energy_fee") or 0))),
        "bandwidth_used": _bandwidth_used(receipt),
        "bandwidth_fee_trx": str(tron.sun_to_trx(int(receipt.get("net_fee") or 0))),
        "block": info.get("blockNumber"),
        "timestamp": timestamp.isoformat() if timestamp else None,
        "function": function,
        "token_transfers": transfers,
        "gasfree": gasfree,
        "explorer": tron.explorer_tx(txid),
    }
    lines = [
        f"Tx {short_addr(txid)} on Tron: {status}" + dim(f" ({contract_type})"),
        f"  {sender or 'unknown'} → {target or '-'}",
        f"  value {fmt_amount(amount)} TRX"
        + (f" (~{fmt_usd(data['value_usd'])})" if data["value_usd"] else "")
        + (f", fee {fmt_amount(fee)} TRX" if fee is not None else "")
        + (f" (~{fmt_usd(data['fee_usd'])})" if data["fee_usd"] else ""),
    ]
    if function:
        lines.append(f"  calls {function}")
    if gasfree:
        lines.append(
            f"  GasFree: {bold(fmt_amount(gasfree['amount']) + ' ' + gasfree['symbol'])} "
            f"{short_addr(gasfree['user'])} → {short_addr(gasfree['receiver'])}, "
            f"fee {fmt_amount(gasfree['fee'])} {gasfree['symbol']}"
            + (f" (+{fmt_amount(gasfree['activate_fee'])} activation)" if Decimal(gasfree["activate_fee"]) else "")
        )
    if transfers:
        lines.append("  transfers:")
        for row in transfers[:TEXT_TRANSFER_LIMIT]:
            arrow = f"{short_addr(row['from'])} → {short_addr(row['to'])}"
            lines.append(f"    {fmt_amount(row['amount'])} {row['symbol']}: {arrow}")
        hidden = len(transfers) - TEXT_TRANSFER_LIMIT
        if hidden > 0:
            lines.append(f"    … +{hidden} more transfers (--json lists all)")
    if data["block"] is not None:
        when = f" at {timestamp.strftime('%Y-%m-%d %H:%M UTC')}" if timestamp else ""
        lines.append(f"  block {data['block']}{when}")
    out.emit(
        data,
        lines,
        quiet_value=status,
        verbose_lines=[
            f"energy: {data['energy_used'] or 0:,} used, {data['energy_fee_trx']} TRX burned; "
            f"bandwidth: {data['bandwidth_used'] or 0:,} used, {data['bandwidth_fee_trx']} TRX burned",
            f"explorer: {data['explorer']}",
        ],
    )


def _proxy_target(address: str, contract: dict) -> str | None:
    names = {entry.get("name") for entry in (contract.get("abi") or {}).get("entrys") or []}
    if "implementation" not in names:
        return None
    try:
        data, _ = tron.constant_call(address, "implementation()")
    except ChainqError:
        return None
    return tron.from_hex(data[-20:].hex()) if data and int.from_bytes(data, "big") else None


def _resources(address: str) -> dict:
    res = tron.account_resource(address)
    return {
        "energy_limit": res.get("EnergyLimit", 0),
        "energy_used": res.get("EnergyUsed", 0),
        "bandwidth_free_limit": res.get("freeNetLimit", 0),
        "bandwidth_free_used": res.get("freeNetUsed", 0),
        "bandwidth_staked_limit": res.get("NetLimit", 0),
        "bandwidth_staked_used": res.get("NetUsed", 0),
    }


def _gasfree_profile(address: str) -> dict | None:
    try:
        holder = tron.gasfree_address(address)
        raw = tron.trc20_balance(tron.USDT, holder)
        activated = tron.get_account(holder).get("type") == "Contract"
    except ChainqError:
        return None
    return {"address": holder, "activated": activated, "usdt": str(_amount(raw, 6))}


def address(out: Out, target: str, net) -> None:
    addr = tron.resolve_tron_address(target)
    account = tron.get_account(addr)
    is_contract = account.get("type") == "Contract"
    contract = tron.get_contract(addr) if is_contract else {}
    proxy = _proxy_target(addr, contract) if is_contract else None
    trc20 = tron.trc20_profile(addr) if is_contract else None
    resources = _resources(addr) if account else None
    gasfree = _gasfree_profile(addr) if not is_contract else None
    assets = pricing.price_assets(scan_assets(addr, account)) if account else []
    native = next((a for a in assets if a["symbol"] == "TRX"), None)
    staked = next((a for a in assets if a["symbol"] == "TRX (staked)"), None)
    holdings = [
        {k: a.get(k) for k in ("symbol", "token_address", "amount", "kind", "value_usd", "price_source")}
        for a in assets
        if a["token_address"] and a["value_usd"] is not None
    ]
    holdings.sort(key=lambda h: -h["value_usd"])
    hidden = sum(1 for a in assets if a["token_address"] and a["value_usd"] is None)
    kind = "contract" if is_contract else ("account" if account else "unactivated")
    created = datetime.fromtimestamp(account["create_time"] / 1000, tz=UTC) if account.get("create_time") else None
    data = {
        "address": addr,
        "input": target,
        "hex_address": tron.to_hex(addr),
        "network": net.key,
        "type": kind,
        "contract_name": contract.get("name") or None,
        "creator": contract.get("origin_address"),
        "proxy_implementation": proxy,
        "trc20": trc20,
        "created_at": created.isoformat() if created else None,
        "native_amount": native["amount"] if native else "0",
        "native_value_usd": native["value_usd"] if native else None,
        "staked_trx": staked["amount"] if staked else "0",
        "staked_value_usd": staked["value_usd"] if staked else None,
        "resources": resources,
        "gasfree": gasfree,
        "holdings": holdings,
        "holdings_hidden": hidden,
        "explorer": tron.explorer_address(addr),
    }
    what = {"account": "account (wallet)", "unactivated": "unactivated address (never received TRX)"}.get(kind)
    if is_contract:
        what = f"contract {contract.get('name') or ''}".rstrip()
        if proxy:
            what = f"proxy contract → {proxy}"
    lines = [f"{short_addr(addr)} on Tron: {what}"]
    if trc20:
        lines.append(
            f"  TRC-20: {trc20['name'] or trc20['symbol']} ({trc20['symbol']}), "
            f"{trc20['decimals']} decimals, supply {fmt_amount(trc20['total_supply'])}"
        )
    if contract.get("origin_address"):
        lines.append(f"  creator: {contract['origin_address']}")
    native_line = f"  native: {fmt_amount(data['native_amount'])} TRX"
    if data["native_value_usd"] is not None:
        native_line += f" (~{fmt_usd(data['native_value_usd'])})"
    if staked:
        native_line += f", staked {fmt_amount(staked['amount'])} TRX"
    lines.append(native_line)
    if resources and (resources["energy_limit"] or resources["bandwidth_staked_limit"]):
        lines.append(
            f"  resources: energy {resources['energy_used']:,}/{resources['energy_limit']:,}, "
            f"bandwidth {resources['bandwidth_staked_used']:,}/{resources['bandwidth_staked_limit']:,}"
            f" + free {resources['bandwidth_free_used']}/{resources['bandwidth_free_limit']}"
        )
    if holdings:
        shown = ", ".join(f"{fmt_amount(h['amount'])} {h['symbol']} (~{fmt_usd(h['value_usd'])})" for h in holdings[:5])
        more = f" (+{len(holdings) - 5} more)" if len(holdings) > 5 else ""
        unpriced = f" ({hidden} unpriced hidden)" if hidden else ""
        lines.append(f"  tokens: {shown}{more}{unpriced}")
    if gasfree and (gasfree["activated"] or Decimal(gasfree["usdt"])):
        state = "activated" if gasfree["activated"] else "not activated"
        lines.append(f"  GasFree: {gasfree['address']} ({state}), {fmt_amount(gasfree['usdt'])} USDT")
    out.emit(
        data,
        lines,
        quiet_value=kind,
        verbose_lines=[
            f"hex: {data['hex_address']}",
            *([f"created: {created.strftime('%Y-%m-%d')}"] if created else []),
            *([f"gasfree address: {gasfree['address']}"] if gasfree else []),
            f"explorer: {data['explorer']}",
        ],
    )


def rpc(method: str, params: list) -> None:
    if method.startswith(JSON_RPC_PREFIXES):
        result = tron.rpc_call(method, params)
    else:
        path = method if "/" in method else f"wallet/{method}"
        body = params[0] if params and isinstance(params[0], dict) else {}
        result = tron.api(path, body)
    print(json.dumps(result, indent=2, default=str))
