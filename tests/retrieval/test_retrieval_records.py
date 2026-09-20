"""Verify explicit vectors, search timing boundaries, and sparse retrieval."""
import json
from types import SimpleNamespace

import numpy as np
import pytest
from llama_index.core import Document
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.schema import NodeWithScore, TextNode

from src.retrieval.chunking import build_nodes
from src.retrieval.evaluation import cosine_similarity, retrieve_record
from src.retrieval.indexing import build_index


class WordTokenizer:
    def encode(self, text, add_special_tokens=True, **kwargs):
        return list(range(len(text.split()) + (2 if add_special_tokens else 0)))


def embedding():
    model = MockEmbedding(embed_dim=12)
    object.__setattr__(model, "_model", SimpleNamespace(tokenizer=WordTokenizer(), max_seq_length=256))
    return model


@pytest.mark.parametrize("left,right,expected", [([1, 0], [1, 0], 1), ([1, 0], [0, 1], 0), ([1, 0], [-1, 0], -1)])
def test_known_cosine(left, right, expected):
    assert cosine_similarity(left, right) == pytest.approx(expected)


@pytest.mark.parametrize("left,right", [([0, 0], [1, 0]), ([1, float("nan")], [1, 0]), ([1, float("inf")], [1, 0]), ([1], [1, 0]), ([], []), ([[1, 0]], [[1, 0]])])
def test_invalid_vectors_fail(left, right):
    with pytest.raises(ValueError):
        cosine_similarity(left, right)


def test_real_llama_index_returns_aligned_vectors_and_fewer_than_k():
    model = embedding()
    nodes, _ = build_nodes([Document(text="Rent is monthly.", metadata={"source_id": "lease"})], "token", model, {})
    index = build_index(nodes, model)
    record, vectors = retrieve_record(index, model, {"id": "q1", "question": "When is rent due?", "expected_source_ids": ["lease"]})
    assert record["requested_k"] == 3 and record["returned_k"] == 1
    assert record["query_vector_shape"] == [12]
    assert record["document_vector_shape"] == [1, 12]
    assert record["query_embedding_first8"] == vectors["query"][:8]
    assert len(record["search_seconds"]) == 10
    assert record["hits"][0]["cosine"] == pytest.approx(1)
    assert record["hits"][0]["embedding_text"] == "Rent is monthly."
    assert record["hits"][0]["token_length"] == 5
    assert np.asarray(vectors["documents"]).shape == (1, 12)
    json.dumps(record, allow_nan=False)
    json.dumps(vectors, allow_nan=False)


def test_embeddings_stay_outside_timer_and_ties_use_node_ids(monkeypatch):
    import src.retrieval.evaluation as evaluation
    events = []

    class RecordingEmbedding:
        _model = SimpleNamespace(tokenizer=WordTokenizer(), max_seq_length=256)

        def get_query_embedding(self, text):
            events.append("query_embedding")
            return [1.0, 0.0]

        def get_text_embedding_batch(self, texts):
            events.append(("document_embeddings", texts))
            return [[1.0, 0.0] for _ in texts]

    def node(id_, text):
        result = TextNode(id_=id_, text=text, metadata={"source_id": "lease", "technique": "sentence_window", "window": text + " Context."})
        result.excluded_embed_metadata_keys = list(result.metadata)
        return NodeWithScore(node=result, score=0.9)

    class Retriever:
        def retrieve(self, bundle):
            assert bundle.embedding == [1.0, 0.0]
            events.append("search")
            return [node("b", "Second sentence."), node("a", "First sentence.")]

    class Index:
        def as_retriever(self, similarity_top_k):
            events.append("create_retriever")
            return Retriever()

    ticks = iter(range(20))

    def tick():
        events.append("clock")
        return next(ticks)

    monkeypatch.setattr(evaluation, "perf_counter", tick)
    record, _ = retrieve_record(Index(), RecordingEmbedding(), {"id": "q", "question": "rent", "expected_source_ids": ["lease"]})
    assert events[:3] == ["query_embedding", "create_retriever", "search"]
    assert events[3:-1] == ["clock", "search", "clock"] * 10
    assert events[-1] == ("document_embeddings", ["First sentence.", "Second sentence."])
    assert record["search_seconds"] == [1] * 10
    assert [hit["node_id"] for hit in record["hits"]] == ["a", "b"]
    assert [hit["store_rank"] for hit in record["hits"]] == [2, 1]
    assert record["hits"][0]["context_text"] == "First sentence. Context."


def test_empty_index_serializes_and_marks_no_results():
    model = embedding()
    record, vectors = retrieve_record(build_index([], model), model, {"id": "q", "question": "rent", "expected_source_ids": ["lease"]})
    assert record["hits"] == []
    assert record["returned_k"] == 0
    assert record["document_vector_shape"] == [0, 12]
    assert vectors["documents"] == []
    assert record["diagnostics"]
    json.dumps(record, allow_nan=False)
