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
    kind: str = "evm"


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
            key="robinhood",
            name="Robinhood Chain",
            chain_id=4663,
            native_symbol="ETH",
            native_coingecko_id="ethereum",
            rpc_urls=("https://rpc.mainnet.chain.robinhood.com",),
            explorer="https://robinhoodchain.blockscout.com",
            aliases=("rh", "robinhood-chain"),
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
        Network(
            key="linea",
            name="Linea",
            chain_id=59144,
            native_symbol="ETH",
            native_coingecko_id="ethereum",
            rpc_urls=("https://linea-rpc.publicnode.com", "https://rpc.linea.build"),
            explorer="https://lineascan.build",
        ),
        Network(
            key="scroll",
            name="Scroll",
            chain_id=534352,
            native_symbol="ETH",
            native_coingecko_id="ethereum",
            rpc_urls=("https://scroll-rpc.publicnode.com", "https://rpc.scroll.io"),
            explorer="https://scrollscan.com",
        ),
        Network(
            key="zksync",
            name="ZKsync Era",
            chain_id=324,
            native_symbol="ETH",
            native_coingecko_id="ethereum",
            rpc_urls=("https://mainnet.era.zksync.io",),
            explorer="https://era.zksync.network",
            aliases=("zksync-era", "era"),
        ),
        Network(
            key="mantle",
            name="Mantle",
            chain_id=5000,
            native_symbol="MNT",
            native_coingecko_id="mantle",
            rpc_urls=("https://mantle-rpc.publicnode.com", "https://rpc.mantle.xyz"),
            explorer="https://mantlescan.xyz",
            aliases=("mnt",),
        ),
        Network(
            key="blast",
            name="Blast",
            chain_id=81457,
            native_symbol="ETH",
            native_coingecko_id="ethereum",
            rpc_urls=("https://blast-rpc.publicnode.com", "https://rpc.blast.io"),
            explorer="https://blastscan.io",
        ),
        Network(
            key="sonic",
            name="Sonic",
            chain_id=146,
            native_symbol="S",
            native_coingecko_id="sonic-3",
            rpc_urls=("https://sonic-rpc.publicnode.com", "https://rpc.soniclabs.com"),
            explorer="https://sonicscan.org",
            aliases=("s",),
        ),
        Network(
            key="berachain",
            name="Berachain",
            chain_id=80094,
            native_symbol="BERA",
            native_coingecko_id="berachain-bera",
            rpc_urls=("https://berachain-rpc.publicnode.com", "https://rpc.berachain.com"),
            explorer="https://berascan.com",
            aliases=("bera",),
        ),
        Network(
            key="worldchain",
            name="World Chain",
            chain_id=480,
            native_symbol="ETH",
            native_coingecko_id="ethereum",
            rpc_urls=("https://worldchain-mainnet.g.alchemy.com/public",),
            explorer="https://worldscan.org",
            aliases=("world",),
        ),
        Network(
            key="ink",
            name="Ink",
            chain_id=57073,
            native_symbol="ETH",
            native_coingecko_id="ethereum",
            rpc_urls=("https://rpc-gel.inkonchain.com",),
            explorer="https://explorer.inkonchain.com",
        ),
        Network(
            key="soneium",
            name="Soneium",
            chain_id=1868,
            native_symbol="ETH",
            native_coingecko_id="ethereum",
            rpc_urls=("https://soneium-rpc.publicnode.com", "https://rpc.soneium.org"),
            explorer="https://soneium.blockscout.com",
        ),
        Network(
            key="celo",
            name="Celo",
            chain_id=42220,
            native_symbol="CELO",
            native_coingecko_id="celo",
            rpc_urls=("https://celo-rpc.publicnode.com", "https://forno.celo.org"),
            explorer="https://celoscan.io",
        ),
        Network(
            key="sei",
            name="Sei EVM",
            chain_id=1329,
            native_symbol="SEI",
            native_coingecko_id="sei-network",
            rpc_urls=("https://sei-evm-rpc.publicnode.com", "https://evm-rpc.sei-apis.com"),
            explorer="https://seitrace.com",
        ),
        Network(
            key="hyperevm",
            name="HyperEVM",
            chain_id=999,
            native_symbol="HYPE",
            native_coingecko_id="hyperliquid",
            rpc_urls=("https://rpc.hyperliquid.xyz/evm",),
            explorer="https://hyperevmscan.io",
            aliases=("hyper", "hype"),
        ),
        Network(
            key="monad",
            name="Monad",
            chain_id=143,
            native_symbol="MON",
            native_coingecko_id="monad",
            rpc_urls=("https://rpc.monad.xyz",),
            explorer="https://monadexplorer.com",
            aliases=("mon",),
        ),
        Network(
            key="plasma",
            name="Plasma",
            chain_id=9745,
            native_symbol="XPL",
            native_coingecko_id="plasma",
            rpc_urls=("https://rpc.plasma.to",),
            explorer="https://plasmascan.to",
            aliases=("xpl",),
        ),
        Network(
            key="katana",
            name="Katana",
            chain_id=747474,
            native_symbol="ETH",
            native_coingecko_id="ethereum",
            rpc_urls=("https://rpc.katana.network",),
            explorer="https://explorer.katanarpc.com",
        ),
        Network(
            key="solana",
            name="Solana",
            chain_id=101,
            native_symbol="SOL",
            native_coingecko_id="solana",
            rpc_urls=(
                "https://api.mainnet-beta.solana.com",
                "https://solana-rpc.publicnode.com",
            ),
            explorer="https://solscan.io",
            aliases=("sol",),
            kind="solana",
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
