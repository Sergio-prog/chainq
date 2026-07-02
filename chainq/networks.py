from dataclasses import dataclass

from chainq.errors import ChainqError


@dataclass(frozen=True)
class Network:
    key: str
    name: str
    chain_id: int
    native_symbol: str
    native_coingecko_id: str
    rpc_urls: tuple[str, ...]
    explorer: str
    aliases: tuple[str, ...] = ()


NETWORKS: dict[str, Network] = {
    net.key: net
    for net in (
        Network(
            key="ethereum",
            name="Ethereum",
            chain_id=1,
            native_symbol="ETH",
            native_coingecko_id="ethereum",
            rpc_urls=(
                "https://ethereum-rpc.publicnode.com",
                "https://eth.llamarpc.com",
                "https://1rpc.io/eth",
                "https://eth.drpc.org",
            ),
            explorer="https://etherscan.io",
            aliases=("eth", "mainnet", "ether"),
        ),
        Network(
            key="arbitrum",
            name="Arbitrum One",
            chain_id=42161,
            native_symbol="ETH",
            native_coingecko_id="ethereum",
            rpc_urls=(
                "https://arbitrum-one-rpc.publicnode.com",
                "https://arb1.arbitrum.io/rpc",
                "https://1rpc.io/arb",
            ),
            explorer="https://arbiscan.io",
            aliases=("arb", "arbitrum-one"),
        ),
        Network(
            key="base",
            name="Base",
            chain_id=8453,
            native_symbol="ETH",
            native_coingecko_id="ethereum",
            rpc_urls=(
                "https://base-rpc.publicnode.com",
                "https://mainnet.base.org",
                "https://1rpc.io/base",
            ),
            explorer="https://basescan.org",
        ),
        Network(
            key="optimism",
            name="OP Mainnet",
            chain_id=10,
            native_symbol="ETH",
            native_coingecko_id="ethereum",
            rpc_urls=(
                "https://optimism-rpc.publicnode.com",
                "https://mainnet.optimism.io",
                "https://1rpc.io/op",
            ),
            explorer="https://optimistic.etherscan.io",
            aliases=("op",),
        ),
        Network(
            key="polygon",
            name="Polygon PoS",
            chain_id=137,
            native_symbol="POL",
            native_coingecko_id="polygon-ecosystem-token",
            rpc_urls=(
                "https://polygon-bor-rpc.publicnode.com",
                "https://polygon-rpc.com",
                "https://1rpc.io/matic",
            ),
            explorer="https://polygonscan.com",
            aliases=("matic", "pol"),
        ),
        Network(
            key="bsc",
            name="BNB Smart Chain",
            chain_id=56,
            native_symbol="BNB",
            native_coingecko_id="binancecoin",
            rpc_urls=(
                "https://bsc-rpc.publicnode.com",
                "https://bsc-dataseed.bnbchain.org",
                "https://1rpc.io/bnb",
            ),
            explorer="https://bscscan.com",
            aliases=("bnb", "binance"),
        ),
        Network(
            key="avalanche",
            name="Avalanche C-Chain",
            chain_id=43114,
            native_symbol="AVAX",
            native_coingecko_id="avalanche-2",
            rpc_urls=(
                "https://avalanche-c-chain-rpc.publicnode.com",
                "https://api.avax.network/ext/bc/C/rpc",
                "https://1rpc.io/avax/c",
            ),
            explorer="https://snowscan.xyz",
            aliases=("avax",),
        ),
        Network(
            key="gnosis",
            name="Gnosis",
            chain_id=100,
            native_symbol="xDAI",
            native_coingecko_id="xdai",
            rpc_urls=(
                "https://gnosis-rpc.publicnode.com",
                "https://rpc.gnosischain.com",
            ),
            explorer="https://gnosisscan.io",
            aliases=("xdai", "gno"),
        ),
        Network(
            key="unichain",
            name="Unichain",
            chain_id=130,
            native_symbol="ETH",
            native_coingecko_id="ethereum",
            rpc_urls=(
                "https://unichain-rpc.publicnode.com",
                "https://mainnet.unichain.org",
            ),
            explorer="https://uniscan.xyz",
            aliases=("uni-chain",),
        ),
    )
}


def resolve_network(query: str) -> Network:
    q = query.strip().lower()
    for net in NETWORKS.values():
        if q == net.key or q in net.aliases or (q.isdigit() and int(q) == net.chain_id):
            return net
    known = ", ".join(NETWORKS)
    raise ChainqError(f"unknown network '{query}' (known: {known}; also accepts aliases and chain ids)")
