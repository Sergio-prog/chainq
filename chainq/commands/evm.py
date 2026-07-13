import typer

from chainq.commands import evm_chain, evm_codec

app = typer.Typer(
    no_args_is_help=True,
    help="EVM queries and utilities: chain state, contract calls, ABI, hashing, bytes, and conversions.",
)

for command in (
    evm_chain.block_number,
    evm_chain.block,
    evm_chain.find_block,
    evm_chain.client,
    evm_chain.chain_id,
    evm_chain.nonce,
    evm_chain.code,
    evm_chain.storage,
    evm_chain.call,
    evm_chain.estimate,
    evm_codec.to_hex,
    evm_codec.to_dec,
    evm_codec.to_wei,
    evm_codec.from_wei,
    evm_codec.sig,
    evm_codec.sig_event,
    evm_codec.shl,
    evm_codec.shr,
    evm_codec.format_bytes32_string,
    evm_codec.parse_bytes32_string,
    evm_codec.parse_bytes32_address,
    evm_codec.to_bytes32,
    evm_codec.from_utf8,
    evm_codec.to_utf8,
    evm_codec.checksum,
    evm_codec.hash_message,
    evm_codec.hash_zero,
    evm_codec.namehash,
    evm_codec.max_int,
    evm_codec.min_int,
    evm_codec.max_uint,
    evm_codec.abi_encode,
    evm_codec.abi_decode,
):
    app.command()(command)

app.command("keccak")(evm_codec.keccak256)
