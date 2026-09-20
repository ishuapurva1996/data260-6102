"""Synthetic parser fixtures; no corpus retrieval or downloaded model is used."""
from types import SimpleNamespace

import pytest
from llama_index.core import Document
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.schema import MetadataMode

from src.retrieval.chunking import build_nodes


class WordTokenizer:
    def encode(self, text, add_special_tokens=True, **kwargs):
        return list(range(len(text.split()) + (2 if add_special_tokens else 0)))


@pytest.fixture
def embedding():
    model = MockEmbedding(embed_dim=12)
    object.__setattr__(model, "_model", SimpleNamespace(tokenizer=WordTokenizer(), max_seq_length=256))
    return model


@pytest.fixture
def documents():
    return [
        Document(text="ALPHA: Rent is due monthly. ALPHA: The deposit is refundable. ALPHA: Pets are permitted.",
                 metadata={"source_id": "alpha", "url": "https://example.invalid/secret-provenance"}),
        Document(text="BETA: Offices open at nine. BETA: Applications close in June. BETA: Call for details.",
                 metadata={"source_id": "beta", "filename": "private_bookkeeping.txt"}),
    ]


@pytest.mark.parametrize("technique", ["token", "semantic", "sentence_window"])
def test_parsers_keep_source_boundaries_and_stable_metadata_free_text(embedding, documents, technique):
    nodes, stats = build_nodes(documents, technique, embedding, {})
    repeated, _ = build_nodes(list(reversed(documents)), technique, embedding, {})
    assert nodes
    assert [n.node_id for n in nodes] == [n.node_id for n in repeated]
    assert stats["chunk_count"] == len(nodes)
    assert len({n.node_id for n in nodes}) == len(nodes)
    for node in nodes:
        text = node.get_content(metadata_mode=MetadataMode.EMBED)
        assert text == node.text
        own, other = ("ALPHA", "BETA") if node.metadata["source_id"] == "alpha" else ("BETA", "ALPHA")
        assert own in text
        assert other not in text
        assert other not in node.metadata.get("window", text)
        assert "example.invalid" not in text and "bookkeeping" not in text
        assert node.metadata["technique"] == technique
    if technique == "sentence_window":
        assert any(len(n.metadata["window"]) > len(n.text) for n in nodes)


def test_token_limit_counts_content_without_a_metadata_reservation(embedding):
    doc = Document(text=" ".join(f"word{i}" for i in range(400)), metadata={"source_id": "long"})
    nodes, stats = build_nodes([doc], "token", embedding, {"token_chunk_size": 192, "token_overlap": 32})
    assert len(nodes[0].text.split()) == 192
    assert nodes[0].text.split()[-32:] == nodes[1].text.split()[:32]
    assert max(row["token_length"] for row in stats["node_lengths"]) == 194
    assert stats["indexed_truncation_count"] == 0


def test_semantic_truncation_audits_boundary_buffers_without_resplitting(embedding):
    sentence = " ".join(["housing"] * 150) + ". "
    doc = Document(text=sentence * 4, metadata={"source_id": "long"})
    nodes, stats = build_nodes([doc], "semantic", embedding, {})
    # Constant synthetic vectors cause no dissimilarity breakpoints.
    assert len(nodes) == 1
    assert len(nodes[0].text.split()) == 600
    assert stats["indexed_truncation_count"] == 1
    assert stats["semantic_buffer_count"] == 4
    assert stats["semantic_buffer_truncation_count"] == 4
    assert all(row["token_length"] > 256 for row in stats["semantic_buffers"])
    assert stats["semantic_buffers"][0]["token_length"] == 302


def test_missing_or_duplicate_source_ids_fail(embedding):
    with pytest.raises(ValueError, match="source_id"):
        build_nodes([Document(text="A sentence.")], "token", embedding, {})
    doc = Document(text="A sentence.", metadata={"source_id": "same"})
    with pytest.raises(ValueError, match="Duplicate"):
        build_nodes([doc, doc], "token", embedding, {})


def test_empty_documents_produce_empty_stats(embedding):
    nodes, stats = build_nodes([], "token", embedding, {})
    assert nodes == [] and stats["chunk_count"] == 0
    assert stats["indexed_truncation_fraction"] == 0
