from chainq.errors import ChainqError
from chainq.networks import Network

TOKENS: dict[str, dict[str, str]] = {
    "ethereum": {
        "usdt": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "usdc": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "dai": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
        "weth": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "wbtc": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
        "steth": "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",
        "link": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
        "uni": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",
        "aave": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",
        "pepe": "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
        "ena": "0x57e114B691Db790C35207b2e685D4A43181e6061",
        "usde": "0x4c9EDD5852cd905f086C759E8383e09bff1E68B3",
    },
    "arbitrum": {
        "usdt": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        "usdc": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "dai": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
        "weth": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "wbtc": "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
        "arb": "0x912CE59144191C1204E64559FE8253a0e49E6548",
    },
    "base": {
        "usdc": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "usdt": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",
        "dai": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",
        "weth": "0x4200000000000000000000000000000000000006",
        "cbbtc": "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf",
    },
    "optimism": {
        "usdt": "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58",
        "usdc": "0x0B2c639c533813F4aa9D7837cACdc7621e0da5D4",
        "dai": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
        "weth": "0x4200000000000000000000000000000000000006",
        "wbtc": "0x68f180fcCe6836688e9084f035309E29Bf0A2095",
        "op": "0x4200000000000000000000000000000000000042",
    },
    "polygon": {
        "usdt": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "usdc": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
        "dai": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
        "weth": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "wbtc": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
        "wpol": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
    },
    "bsc": {
        "usdt": "0x55d398326f99059fF775485246999027B3197955",
        "usdc": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        "eth": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",
        "wbnb": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        "btcb": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c",
        "dai": "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3",
    },
    "avalanche": {
        "usdt": "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7",
        "usdc": "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",
        "wavax": "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7",
    },
    "gnosis": {
        "usdc": "0xDDAfbb505ad214D7b80b1f830fcCc89B60fb7A83",
        "usdt": "0x4ECaBa5870353805a9F068101A40E0f32ed605C6",
        "wxdai": "0xe91D153E0b41518A2Ce8Dd3D7944Fa863463a97d",
        "weth": "0x6A023CCd1ff6F2045C3309768eAd9E68F978f6e1",
    },
    "unichain": {
        "usdc": "0x078D782b760474a361dDA0AF3839290b0EF57AD6",
        "weth": "0x4200000000000000000000000000000000000006",
    },
}


def resolve_token(coin: str, network: Network) -> str:
    if coin.startswith("0x") and len(coin) == 42:
        return coin
    address = TOKENS.get(network.key, {}).get(coin.strip().lower())
    if address is None:
        known = ", ".join(sorted(TOKENS.get(network.key, {}))) or "none"
        raise ChainqError(
            f"unknown token '{coin}' on {network.name} (known symbols: {known}); pass the contract address instead"
        )
    return address
