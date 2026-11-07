"""Binary-safe Redis Search cache over a pinned local cosine embedding."""

import os
import re
import struct
from dataclasses import dataclass

import httpx
from redis import Redis
from redis.exceptions import ResponseError

from src.hw06_shared.config import HW6Config
from src.hw06_shared.models import OllamaEmbedder
from src.kafka_service.config import PREFIX

MODEL = "nomic-embed-text:v1.5"
MODEL_DIGEST = "0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f"
DIMENSION = 768
VECTOR = struct.Struct(f"<{DIMENSION}f")
FIELDS = ("question", "answer", "dataset_id", "data_version", "user_id", "source_request_id")
MODEL_INPUT_PREFIX = "clustering: "


@dataclass(frozen=True)
class CacheSettings:
    redis_url: str
    namespace: str
    threshold: float
    allow_stale: bool

    @classmethod
    def from_env(cls):
        namespace = os.getenv("HW9_CACHE_NAMESPACE", "default")
        threshold = float(os.getenv("HW9_CACHE_THRESHOLD", "0.85"))
        allow_stale = os.getenv("HW9_CACHE_DEMO_ALLOW_STALE", "0") == "1"
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", namespace):
            raise ValueError(
                "HW9_CACHE_NAMESPACE must be 1–64 lowercase letters, digits or hyphens."
            )
        if not 0 <= threshold <= 1:
            raise ValueError("HW9_CACHE_THRESHOLD must be between 0 and 1.")
        if allow_stale and not namespace.startswith("stale-demo-"):
            raise ValueError("Stale demo mode requires a stale-demo-* namespace.")
        return cls(
            os.getenv("HW9_REDIS_URL", "redis://127.0.0.1:6389/0"),
            namespace,
            threshold,
            allow_stale,
        )


def build_embedder():
    return OllamaEmbedder(
        HW6Config(
            ollama_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            embedding_model=MODEL,
            embedding_digest=MODEL_DIGEST,
            embedding_dimension=DIMENSION,
            model_timeout=30,
        )
    )


def verify_embedding_model(embedder):
    response = httpx.get(f"{embedder.config.ollama_url.rstrip('/')}/api/tags", timeout=10)
    response.raise_for_status()
    if not any(
        model["name"] == MODEL and model["digest"] == MODEL_DIGEST
        for model in response.json()["models"]
    ):
        raise RuntimeError(f"Ollama must have {MODEL} with digest {MODEL_DIGEST}.")


class SemanticCache:
    def __init__(self, settings):
        self.settings = settings
        self.entry_prefix = f"{PREFIX}:hw9:semantic:{settings.namespace}:entry:"
        self.index = f"{PREFIX}:hw9:semantic:{settings.namespace}:index"
        self.redis = Redis.from_url(
            settings.redis_url,
            decode_responses=False,
            protocol=2,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

    def create_index(self, *, fresh=False):
        try:
            self.redis.execute_command(
                "FT.CREATE",
                self.index,
                "ON",
                "HASH",
                "PREFIX",
                1,
                self.entry_prefix,
                "SCHEMA",
                "dataset_id",
                "TAG",
                "data_version",
                "TAG",
                "user_id",
                "TAG",
                "embedding",
                "VECTOR",
                "FLAT",
                6,
                "TYPE",
                "FLOAT32",
                "DIM",
                DIMENSION,
                "DISTANCE_METRIC",
                "COSINE",
            )
        except ResponseError as exc:
            if fresh or str(exc) != "Index already exists":
                raise

    def closest(self, vector, dataset_id, version, user_id):
        # Apply eligibility in Redis before the KNN ranking. Searching globally
        # and discarding one stale winner could hide an eligible second match.
        filters = f"@dataset_id:{{{dataset_id}}} @user_id:{{{user_id}}}"
        if not self.settings.allow_stale:
            filters += f" @data_version:{{{version}}}"
        result = self.redis.execute_command(
            "FT.SEARCH",
            self.index,
            f"({filters})=>[KNN 1 @embedding $vec AS distance]",
            "RETURN",
            len(FIELDS) + 1,
            *FIELDS,
            "distance",
            "SORTBY",
            "distance",
            "PARAMS",
            2,
            "vec",
            vector,
            "DIALECT",
            2,
        )
        if not result[0]:
            return None
        fields = dict(zip(result[2][::2], result[2][1::2]))
        candidate = {key: fields[key.encode()].decode() for key in FIELDS}
        candidate["data_version"] = int(candidate["data_version"])
        candidate["similarity"] = max(-1.0, min(1.0, 1 - float(fields[b"distance"])))
        return candidate

    def save(self, vector, *, question, answer, dataset_id, data_version, user_id, request_id):
        self.redis.hset(
            self.entry_prefix + request_id,
            mapping={
                "question": question,
                "answer": answer,
                "embedding": vector,
                "dataset_id": dataset_id,
                "data_version": data_version,
                "user_id": user_id,
                "source_request_id": request_id,
            },
        )

    def close(self):
        self.redis.close()
