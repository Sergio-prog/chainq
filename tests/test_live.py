import json

import pytest
from typer.testing import CliRunner

from chainq.cli import app

pytestmark = pytest.mark.live

runner = CliRunner()

SMOKE = {
    "coingecko-price": ["price", "btc"],
    "coingecko-candles": ["candles", "eth", "--days", "7"],
    "coingecko-history": ["price", "btc", "--at", "2026-03-01"],
    "rpc-gas": ["gas", "-n", "ethereum"],
    "defillama-stables": ["stables"],
    "defillama-chains": ["protocols", "llama", "chains"],
    "hyperliquid": ["protocols", "hl", "markets"],
    "hyperliquid-funding-history": ["protocols", "hl", "funding", "BTC", "--history"],
    "lighter": ["protocols", "lighter", "markets"],
    "aave": ["protocols", "aave", "markets"],
    "morpho": ["protocols", "morpho", "vaults"],
    "pendle": ["protocols", "pendle", "markets"],
    "uniswap": ["protocols", "uniswap", "stats"],
    "sky": ["protocols", "sky", "rate"],
    "ethena": ["protocols", "ethena", "yield"],
    "lido": ["protocols", "lido", "apr"],
    "aerodrome": ["protocols", "aerodrome", "stats"],
    "curve-stats": ["protocols", "curve", "stats"],
    "curve-pools": ["protocols", "curve", "pools", "-l", "3"],
    "solana-gas": ["gas", "-n", "solana"],
    "solana-balance": ["balance", "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", "-n", "solana"],
    "address-eoa": ["address", "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"],
}


@pytest.mark.parametrize("args", SMOKE.values(), ids=list(SMOKE))
def test_command_returns_json(args):
    result = runner.invoke(app, [*args, "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "error" not in payload
