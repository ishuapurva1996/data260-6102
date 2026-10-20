"""One immutable configuration for document and memory services."""
from collections.abc import Mapping
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HW6Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    sid4: Literal[6102] = 6102
    port: Literal[8702] = 8702
    prefix: Literal["s6102"] = "s6102"
    seed: Literal[6102] = 6102
    verify_seed: Literal[266102] = 266102
    domain_id: Literal[6] = 6
    database_name: Literal["s6102_doc"] = "s6102_doc"
    mongo_uri: str = Field(default="mongodb://127.0.0.1:27017", repr=False)
    mongo_timeout_ms: int = Field(default=2000, gt=0)
    model: str = "qwen2.5:7b"
    model_digest: str | None = None
    source_commit: str | None = None
    ollama_url: str = "http://127.0.0.1:11434"
    temperature: float = Field(default=0, ge=0, allow_inf_nan=False)
    context_window: int = Field(default=4096, gt=0)
    output_limit: int = Field(default=512, gt=0)
    model_timeout: float = Field(default=180, gt=0, allow_inf_nan=False)
    short_term_n: int = Field(default=12, ge=0)
    summarize_every_user_msgs: int = Field(default=5, gt=0)
    top_k: int = Field(default=3, ge=0)
    policy: Literal["baseline", "token_budget"] = "baseline"
    token_budget: int = Field(default=160, ge=0)
    embedding_model: str = "nomic-embed-text:v1.5"
    embedding_digest: str | None = None
    embedding_dimension: int = Field(default=768, gt=0)
    tokenizer_path: Path | None = None
    tokenizer_sha256: str | None = None
    cors_origins: tuple[str, ...] = ("https://localhost:8702", "https://127.0.0.1:8702")

    @model_validator(mode="after")
    def validate_limits(self):
        if self.output_limit >= self.context_window:
            raise ValueError("output_limit must be less than context_window")
        return self

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None):
        env = os.environ if env is None else env
        names = {name: f"HW6_{name.upper()}" for name in cls.model_fields}
        names.update(short_term_n="SHORT_TERM_N",
                     summarize_every_user_msgs="SUMMARIZE_EVERY_USER_MSGS")
        values = {name: env[key] for name, key in names.items() if key in env}
        for name in {"sid4", "port", "seed", "verify_seed", "domain_id"} & values.keys():
            values[name] = int(values[name])
        if "cors_origins" in values:
            values["cors_origins"] = tuple(v.strip() for v in values["cors_origins"].split(",") if v.strip())
        return cls(**values)

    def public_dict(self):
        """Telemetry may contain configuration, never connection credentials."""
        return self.model_dump(mode="json", exclude={"mongo_uri"})
