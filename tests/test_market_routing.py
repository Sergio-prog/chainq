from chainq.commands.market import _contract_lookup_key, _dexscreener_best_pair, _token_address_matches
from chainq.providers import uniswap
from chainq.providers.coingecko import is_address, is_solana_mint


def test_solana_mint_detection():
    assert is_solana_mint("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    assert not is_solana_mint("0xdAC17F958D2ee523a2206206994597C13D831ec7")
    assert not is_solana_mint("bitcoin")
    assert not is_address("bitcoin")


def test_contract_lookup_routing():
    mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    evm_address = "0xdAC17F958D2ee523a2206206994597C13D831ec7"

    assert _contract_lookup_key(mint, None) == "solana"
    assert _contract_lookup_key(evm_address, None) is None
    assert _contract_lookup_key(evm_address, "ethereum") == "ethereum"


def test_token_address_comparison_preserves_mint_case():
    mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    evm_address = "0xdAC17F958D2ee523a2206206994597C13D831ec7"

    assert _token_address_matches(mint, mint)
    assert not _token_address_matches(mint, mint.lower())
    assert _token_address_matches(evm_address, evm_address.lower())


def test_solana_pair_selection_preserves_mint_case(monkeypatch):
    mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    correct_pair = {
        "chainId": "solana",
        "baseToken": {"address": mint},
        "liquidity": {"usd": 100},
    }
    wrong_case_pair = {
        "chainId": "solana",
        "baseToken": {"address": mint.lower()},
        "liquidity": {"usd": 1_000},
    }
    monkeypatch.setattr(uniswap, "token_pairs", lambda _: [wrong_case_pair, correct_pair])

    assert _dexscreener_best_pair(mint, "solana") == correct_pair
