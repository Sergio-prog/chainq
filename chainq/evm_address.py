import re

from eth_hash.auto import keccak

from chainq.errors import ChainqError

HEX_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")


def is_hex_address(value: object) -> bool:
    return isinstance(value, str) and HEX_ADDRESS.fullmatch(value) is not None


def checksum(address: str) -> str:
    if not is_hex_address(address):
        raise ValueError(f"not a 0x address: {address!r}")
    body = address[2:].lower()
    digest = keccak(body.encode()).hex()
    return "0x" + "".join(c.upper() if int(digest[i], 16) >= 8 else c for i, c in enumerate(body))


def selector(signature: str) -> bytes:
    return keccak(signature.encode())[:4]


def resolve_address(value: str) -> str:
    value = value.strip()
    if value.lower().endswith(".eth"):
        from chainq.networks import NETWORKS
        from chainq.rpc import connect

        resolved = connect(NETWORKS["ethereum"]).w3.ens.address(value)
        if resolved is None:
            raise ChainqError(f"could not resolve ENS name '{value}'")
        return resolved
    if not is_hex_address(value):
        raise ChainqError(f"invalid address '{value}' (expected 0x + 40 hex chars, or an ENS name)")
    return checksum(value)
