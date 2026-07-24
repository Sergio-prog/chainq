from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(Path.home() / ".config" / "chainq" / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    coingecko_api_key: str | None = Field(
        None, validation_alias=AliasChoices("CHAINQ_COINGECKO_API_KEY", "COINGECKO_API_KEY")
    )
    opensea_api_key: str | None = Field(
        None, validation_alias=AliasChoices("CHAINQ_OPENSEA_API_KEY", "OPENSEA_API_KEY")
    )
    asset_links: str | None = Field(None, validation_alias=AliasChoices("CHAINQ_ASSET_LINKS", "ASSET_LINKS"))
    http_timeout: float = Field(10.0, validation_alias="CHAINQ_HTTP_TIMEOUT")
    rpc_timeout: float = Field(6.0, validation_alias="CHAINQ_RPC_TIMEOUT")


settings = Settings()
