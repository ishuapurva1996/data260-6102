"""Application composition; worker modules do not import one another."""
from dataclasses import dataclass
from pathlib import Path
import subprocess

from src.hw06_documents.service import DocumentService
from src.hw06_memory_mongo.service import MongoMemoryService
from src.hw06_memory_mongo.storage import MongoMemoryStorage
from src.hw06_experiments.policy import token_budget_window
from .config import HW6Config
from .database import MongoConnection
from .models import build_generation_client, OllamaEmbedder, QwenTokenCounter
from .serialization import utc_now
from .telemetry import NullTelemetry


def source_revision():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'],
        cwd=Path(__file__).resolve().parents[2], text=True).strip()


@dataclass
class HW6Runtime:
    config: HW6Config
    connection: object
    document_service: object
    chat_service: object
    embedder: object

    def close(self):
        close = getattr(self.embedder, 'close', None)
        try:
            if close:
                close()
        finally:
            self.connection.close()


def build_runtime(config, *, connection=None, model=None, embedder=None,
                  count_tokens=None, telemetry=None, window_policy=None):
    config = HW6Config(**{**config.model_dump(), 'source_commit': source_revision()})
    connection = connection if connection is not None else MongoConnection(config)
    model = model if model is not None else build_generation_client(config)
    embedder = embedder if embedder is not None else OllamaEmbedder(config)
    if count_tokens is None:
        if config.tokenizer_path is None:
            raise ValueError('HW6_TOKENIZER_PATH is required for the integrated service')
        count_tokens = QwenTokenCounter(config.tokenizer_path, expected_sha256=config.tokenizer_sha256)
    policy = window_policy
    if policy is None and config.policy == 'token_budget':
        policy = token_budget_window
    database = connection.database
    documents = DocumentService(database)
    memory = MongoMemoryService(model=model, embedder=embedder,
        storage=MongoMemoryStorage(database), config=config, count_tokens=count_tokens,
        clock=utc_now, telemetry=telemetry if telemetry is not None else NullTelemetry(),
        window_policy=policy)
    return HW6Runtime(config, connection, documents, memory, embedder)
