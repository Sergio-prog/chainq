import pytest

from chainq.errors import ChainqError
from chainq.networks import resolve_network
from chainq.solana import (
    base58_decode,
    base58_encode,
    is_signature,
    is_solana_address,
    looks_like_solana,
    resolve_solana_address,
    sns_domain_key,
)
from chainq.tokens import SOLANA_TOKENS, resolve_token

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def test_network_resolves():
    net = resolve_network("sol")
    assert net.key == "solana"
    assert net.kind == "solana"


def test_base58_decode_system_program():
    assert base58_decode("11111111111111111111111111111111") == b"\x00" * 32


def test_is_solana_address():
    assert is_solana_address(USDC_MINT)
    assert not is_solana_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    assert not is_solana_address("vitalik.eth")
    assert not is_solana_address("short")


def test_resolve_solana_address_rejects_invalid():
    with pytest.raises(ChainqError):
        resolve_solana_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")


def test_is_signature():
    assert not is_signature(USDC_MINT)
    assert is_signature("5" * 87)


def test_resolve_token_symbol():
    assert resolve_token("USDC", resolve_network("solana")) == USDC_MINT


def test_resolve_token_passthrough_mint():
    assert resolve_token(USDC_MINT, resolve_network("solana")) == USDC_MINT


def test_resolve_token_unknown():
    with pytest.raises(ChainqError):
        resolve_token("notatoken", resolve_network("solana"))


def test_all_mints_are_valid_pubkeys():
    for mint in SOLANA_TOKENS.values():
        assert is_solana_address(mint)


def test_base58_roundtrip():
    assert base58_encode(base58_decode(USDC_MINT)) == USDC_MINT
    assert base58_encode(b"\x00" * 32) == "1" * 32


def test_sns_domain_key():
    assert sns_domain_key("toly") == "FX1APjKbFu6M8GKb3dGXcZLXjxX4fGaYwvHqb5Vaee8q"


def test_looks_like_solana():
    assert looks_like_solana("toly.sol")
    assert looks_like_solana(USDC_MINT)
    assert not looks_like_solana("vitalik.eth")
    assert not looks_like_solana("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")


SIGNER = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
RECEIVER = "8DfHuYFv7VQ6wgcGtVDN2vtFn5ezFwvcFTVd5nGwm8hU"
SOURCE_ATA = "2NmZRs9y7UxJj8hauYiErTX9r2pNASYPSZ9xFUgChVNu"
DEST_ATA = "HF4AV2vKNigai3oNXoNc1tiVuz5ZsmiAr6yVTqNGW4cF"


def _balance(index, owner, amount):
    return {
        "accountIndex": index,
        "mint": USDC_MINT,
        "owner": owner,
        "uiTokenAmount": {"amount": str(amount), "decimals": 6},
    }


TXN = {
    "transaction": {
        "signatures": ["sig"],
        "message": {
            "accountKeys": [{"pubkey": SIGNER, "signer": True}, {"pubkey": SOURCE_ATA}, {"pubkey": DEST_ATA}],
            "instructions": [
                {"programId": "ComputeBudget111111111111111111111111111111", "data": "x"},
                {
                    "program": "spl-token",
                    "programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                    "parsed": {
                        "type": "transfer",
                        "info": {"source": SOURCE_ATA, "destination": DEST_ATA, "amount": "2500000", "authority": SIGNER},
                    },
                },
            ],
        },
    },
    "meta": {
        "fee": 7000,
        "innerInstructions": [
            {
                "index": 1,
                "instructions": [
                    {
                        "program": "system",
                        "parsed": {
                            "type": "transfer",
                            "info": {"source": SIGNER, "destination": RECEIVER, "lamports": 1_000_000_000},
                        },
                    }
                ],
            }
        ],
        "preTokenBalances": [_balance(1, SIGNER, 5_000_000), _balance(2, RECEIVER, 0)],
        "postTokenBalances": [_balance(1, SIGNER, 2_500_000), _balance(2, RECEIVER, 2_500_000)],
    },
}


def test_decode_transfers_resolves_owners_and_inner_instructions():
    from chainq.solana import decode_transfers

    assert decode_transfers(TXN) == [
        {"mint": USDC_MINT, "raw_amount": 2_500_000, "decimals": 6, "from": SIGNER, "to": RECEIVER},
        {"mint": None, "raw_amount": 1_000_000_000, "decimals": 9, "from": SIGNER, "to": RECEIVER},
    ]


def test_owner_changes_priority_fee_and_main_instruction():
    from chainq.solana import main_instruction, owner_token_changes, priority_fee_lamports

    assert owner_token_changes(TXN, SIGNER) == [{"mint": USDC_MINT, "raw_change": -2_500_000, "decimals": 6}]
    assert priority_fee_lamports(TXN) == 2000
    assert main_instruction(TXN) == "SPL Token transfer"
