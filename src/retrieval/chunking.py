"""The three assignment chunkers, with stable IDs and model-token audits."""
from hashlib import sha256
from statistics import fmean


def model_tokenizer(embed_model):
    """Use the embedding model's actual tokenizer; never estimate token counts."""
    tokenizer = getattr(getattr(embed_model, "_model", None), "tokenizer", None)
    if tokenizer is None or not callable(getattr(tokenizer, "encode", None)):
        raise ValueError("Embedding model must expose its actual _model.tokenizer")
    return tokenizer


def token_length(text, tokenizer, *, special_tokens=True):
    return len(tokenizer.encode(text, add_special_tokens=special_tokens,
                                truncation=False, verbose=False))


def _lengths(text, tokenizer, limit):
    count = token_length(text, tokenizer)
    return {"character_length": len(text), "token_length": count, "truncated": count > limit}


def _mean(values):
    return fmean(values) if values else 0.0


def build_nodes(documents, technique, embed_model, config):
    """Return LlamaIndex nodes and JSON-ready central/context/buffer statistics.

    Token chunks use 192 *content* tokens by default. Audit lengths additionally
    count the model's special tokens. Semantic chunks are left intact even when
    their embeddings will be truncated. Sentence windows remain metadata, never
    replacements for the central sentence sent to the embedding model.
    """
    from llama_index.core.node_parser import (
        SemanticSplitterNodeParser, SentenceWindowNodeParser, TokenTextSplitter,
    )
    from llama_index.core.node_parser.node_utils import build_nodes_from_splits
    from llama_index.core.schema import MetadataMode
    from pydantic import PrivateAttr

    if technique not in {"token", "semantic", "sentence_window"}:
        raise ValueError(f"Unknown chunking technique: {technique}")
    tokenizer = model_tokenizer(embed_model)
    limit = int(config.get("max_seq_length", 256))
    if limit < 1:
        raise ValueError("max_seq_length must be positive")
    sources = [doc.metadata.get("source_id") for doc in documents]
    if any(not isinstance(source, str) or not source.strip() for source in sources):
        raise ValueError("Every document needs a nonempty source_id")
    if len(set(sources)) != len(sources):
        raise ValueError("Duplicate source_id in documents")

    def stable_id(number, doc):
        source_hash = sha256(doc.metadata["source_id"].encode()).hexdigest()[:16]
        return f"{technique}:{source_hash}:{number:06d}"

    class AuditedSemanticSplitter(SemanticSplitterNodeParser):
        """Observe the exact sentence groups used by the installed parser."""
        _buffer_audit: list = PrivateAttr(default_factory=list)
        _source_id: str = PrivateAttr(default="")

        def _build_sentence_groups(self, text_splits):
            groups = super()._build_sentence_groups(text_splits)
            for group in groups:
                text = group["combined_sentence"]
                self._buffer_audit.append({
                    "source_id": self._source_id,
                    "sentence_index": group["index"],
                    "text_sha256": sha256(text.encode()).hexdigest(),
                    **_lengths(text, tokenizer, limit),
                })
            return groups

    if technique == "token":
        parser = TokenTextSplitter(
            chunk_size=int(config.get("token_chunk_size", 192)),
            chunk_overlap=int(config.get("token_overlap", 32)),
            tokenizer=lambda text: tokenizer.encode(text, add_special_tokens=False,
                                                     truncation=False, verbose=False),
            id_func=stable_id,
        )
    elif technique == "semantic":
        parser = AuditedSemanticSplitter.from_defaults(
            embed_model=embed_model,
            buffer_size=int(config.get("semantic_buffer_size", 1)),
            breakpoint_percentile_threshold=int(config.get("semantic_breakpoint_percentile", 95)),
            include_prev_next_rel=False,
            id_func=stable_id,
        )
    else:
        parser = SentenceWindowNodeParser.from_defaults(
            window_size=int(config.get("sentence_window_size", 3)),
            window_metadata_key="window", original_text_metadata_key="original_text",
            include_prev_next_rel=False, id_func=stable_id,
        )

    nodes = []
    for original in sorted(documents, key=lambda doc: doc.metadata["source_id"]):
        # Copies keep caller metadata and exclusion lists unchanged.
        doc = original.model_copy(deep=True)
        doc.id_ = "source:" + sha256(doc.metadata["source_id"].encode()).hexdigest()
        doc.embedding = None
        doc.excluded_embed_metadata_keys = list(doc.metadata)
        doc.excluded_llm_metadata_keys = list(doc.metadata)
        if not doc.text.strip():
            continue
        if technique == "token":
            # split_text avoids the metadata-aware parser's extra reservation;
            # provenance is excluded and the budget is solely content tokens.
            parsed = build_nodes_from_splits(parser.split_text(doc.text), doc, id_func=stable_id)
        else:
            if technique == "semantic":
                parser._source_id = doc.metadata["source_id"]
            parsed = parser.get_nodes_from_documents([doc], show_progress=False)
        for node in parsed:
            if not node.text.strip():
                continue
            node.metadata = {**doc.metadata, **node.metadata, "technique": technique}
            node.excluded_embed_metadata_keys = list(node.metadata)
            node.excluded_llm_metadata_keys = list(node.metadata)
            if node.get_content(metadata_mode=MetadataMode.EMBED) != node.text:
                raise ValueError("Metadata contaminated the indexed embedding text")
            nodes.append(node)

    lengths = []
    for node in nodes:
        text = node.get_content(metadata_mode=MetadataMode.EMBED)
        context = node.metadata.get("window", text)
        lengths.append({
            "node_id": node.node_id, "source_id": node.metadata["source_id"],
            **_lengths(text, tokenizer, limit),
            "context_character_length": len(context),
            "context_token_length": token_length(context, tokenizer),
        })
    buffers = parser._buffer_audit if technique == "semantic" else []
    truncated = sum(row["truncated"] for row in lengths)
    truncated_buffers = sum(row["truncated"] for row in buffers)
    stats = {
        "technique": technique, "chunk_count": len(nodes),
        "average_character_length": _mean([row["character_length"] for row in lengths]),
        "average_token_length": _mean([row["token_length"] for row in lengths]),
        "average_context_character_length": _mean([row["context_character_length"] for row in lengths]),
        "average_context_token_length": _mean([row["context_token_length"] for row in lengths]),
        "max_seq_length": limit, "token_lengths_include_special_tokens": True,
        "indexed_truncation_count": truncated,
        "indexed_truncation_fraction": truncated / len(nodes) if nodes else 0.0,
        "node_lengths": lengths,
        "semantic_buffer_count": len(buffers),
        "semantic_buffer_truncation_count": truncated_buffers,
        "semantic_buffer_truncation_fraction": truncated_buffers / len(buffers) if buffers else 0.0,
        "semantic_buffers": buffers,
    }
    return nodes, stats
