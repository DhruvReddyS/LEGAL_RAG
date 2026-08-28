from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    cors_origins: str = (
        "http://localhost:3000,http://advocate.localhost:3000,"
        "http://admin.localhost:3000,http://127.0.0.1:3000,"
        "http://127.0.0.2:3000,http://tauri.localhost,tauri://localhost"
    )
    cors_allow_private_network: bool = False
    trusted_hosts: str = "localhost,127.0.0.1,test,testserver"
    cookie_secure: bool | None = None
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    database_url: str = Field(
        default="postgresql+asyncpg://legal_rag:legal_rag_dev_only@localhost:5432/legal_rag"
    )
    qdrant_url: str = "http://localhost:6333"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    embedding_device: str = "auto"
    qdrant_dense_vector_name: str = "dense"
    qdrant_sparse_vector_name: str = "sparse"
    query_embedding_cache_size: int = Field(default=256, ge=0, le=4096)
    fast_candidate_limit: int = Field(default=8, ge=4, le=40)
    fast_result_limit: int = Field(default=4, ge=1, le=10)
    fast_latency_target_ms: int = Field(default=5000, ge=500, le=30000)
    deep_latency_target_ms: int = Field(default=60000, ge=5000, le=300000)
    warm_query_models_on_startup: bool = True
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3-14b-16k:latest"
    jwt_secret_key: SecretStr = SecretStr("development-access-secret-change-me")
    jwt_refresh_secret_key: SecretStr = SecretStr("development-refresh-secret-change-me")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    jwt_issuer: str = "multi-agent-legal-rag"
    jwt_audience: str = "multi-agent-legal-rag-api"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: SecretStr = SecretStr("development-minio-user")
    s3_secret_access_key: SecretStr = SecretStr("development-minio-secret")
    s3_bucket_name: str = "legal-rag-documents"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False
    s3_corpus_bucket: str = "legal-rag-corpus"
    s3_police_bucket: str = "legal-rag-police"
    s3_advocate_bucket: str = "legal-rag-advocate"
    s3_generated_bucket: str = "legal-rag-generated"
    legal_kb_root: str = "/data/legal_kb"

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if not origins:
            raise ValueError("cors_origins must contain at least one explicit origin")
        normalized: list[str] = []
        for origin in origins:
            if "*" in origin:
                raise ValueError("wildcard CORS is forbidden when credential cookies are enabled")
            try:
                parsed = urlsplit(origin)
                # Reading .port also validates malformed and out-of-range ports.
                parsed.port
            except ValueError as exc:
                raise ValueError(f"invalid CORS origin: {origin}") from exc
            if (
                parsed.scheme not in {"http", "https", "tauri"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(f"invalid CORS origin: {origin}")
            if parsed.scheme == "tauri" and parsed.netloc != "localhost":
                raise ValueError("only tauri://localhost is an allowed Tauri origin")
            normalized.append(origin.rstrip("/"))
        return ",".join(dict.fromkeys(normalized))

    @field_validator("trusted_hosts")
    @classmethod
    def validate_trusted_hosts(cls, value: str) -> str:
        hosts = [host.strip().lower() for host in value.split(",") if host.strip()]
        if not hosts:
            raise ValueError("trusted_hosts must contain at least one explicit host")
        for host in hosts:
            if (
                "*" in host
                or "://" in host
                or "/" in host
                or any(character.isspace() for character in host)
            ):
                raise ValueError(f"invalid trusted host: {host}")
        return ",".join(dict.fromkeys(hosts))

    @model_validator(mode="after")
    def validate_cookie_transport(self) -> "Settings":
        if self.cookie_samesite == "none" and not self.auth_cookie_secure:
            raise ValueError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
        if self.app_env.casefold() not in {"development", "test"} and not self.auth_cookie_secure:
            raise ValueError("secure authentication cookies are required outside development")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return self.cors_origins.split(",")

    @property
    def trusted_host_list(self) -> list[str]:
        return self.trusted_hosts.split(",")

    @property
    def auth_cookie_secure(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.app_env.casefold() != "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
