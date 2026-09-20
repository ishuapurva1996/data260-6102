"""Retrieve without an LLM and save explicit cosine and timing evidence."""
from itertools import groupby
from time import perf_counter

import numpy as np

from .chunking import model_tokenizer, token_length


def _vector(value, label):
    vector = np.asarray(value, dtype=float)
    if vector.ndim != 1 or not vector.size or not np.isfinite(vector).all():
        raise ValueError(f"{label} must be a nonempty finite one-dimensional vector")
    norm = np.linalg.norm(vector)
    if not np.isfinite(norm) or norm == 0:
        raise ValueError(f"{label} must have a finite, nonzero norm")
    return vector


def cosine_similarity(left, right):
    left = _vector(left, "Left vector")
    right = _vector(right, "Right vector")
    if left.shape != right.shape:
        raise ValueError(f"Cosine vector shapes differ: {left.shape} versus {right.shape}")
    cosine = np.dot(left / np.linalg.norm(left), right / np.linalg.norm(right))
    return float(np.clip(cosine, -1.0, 1.0))


def _stable_ties(results):
    """Preserve store order except deterministic ID order within tied scores."""
    ranked = list(enumerate(results, start=1))
    output = []
    for _, group in groupby(ranked, key=lambda item: item[1].score):
        output.extend(sorted(group, key=lambda item: item[1].node.node_id))
    return output


def retrieve_record(index, embed_model, question, k=3, repeats=10, *, technique=None):
    """Return a JSON-ready result and aligned query/document vector sidecar.

    Exactly one unmeasured search warms the retriever. Only retrieve() calls with
    an already computed query vector are timed. Explicit document re-embedding,
    tokenizer audits, formatting, and printing happen outside those intervals.
    """
    from llama_index.core.schema import MetadataMode, QueryBundle

    if k < 1 or repeats < 1:
        raise ValueError("k and repeats must be positive")
    query = question["question"]
    query_vector = _vector(embed_model.get_query_embedding(query), "Query embedding")
    query_values = query_vector.tolist()
    # Bundles and the retriever are constructed outside the search timer.
    bundles = [QueryBundle(query_str=query, embedding=query_values.copy()) for _ in range(repeats + 1)]
    retriever = index.as_retriever(similarity_top_k=k)
    retriever.retrieve(bundles[0])
    samples = []
    results = []
    for bundle in bundles[1:]:
        start = perf_counter()
        results = retriever.retrieve(bundle)
        samples.append(perf_counter() - start)
    ranked = _stable_ties(results)
    texts = [hit.node.get_content(metadata_mode=MetadataMode.EMBED) for _, hit in ranked]
    for text, (_, hit) in zip(texts, ranked):
        if text != hit.node.text:
            raise ValueError(f"Retrieved node {hit.node.node_id} has metadata in its embedding input")
    vectors = embed_model.get_text_embedding_batch(texts) if texts else []
    if len(vectors) != len(ranked):
        raise ValueError("Document embedding count differs from retrieved-node count")
    tokenizer = model_tokenizer(embed_model)
    limit = int(embed_model._model.max_seq_length)
    hits = []
    documents = []
    for rank, ((store_rank, result), text, vector) in enumerate(zip(ranked, texts, vectors), start=1):
        vector = _vector(vector, "Document embedding")
        cosine = cosine_similarity(query_vector, vector)
        documents.append(vector.tolist())
        node = result.node
        context = node.metadata.get("window", text)
        count = token_length(text, tokenizer)
        score = float(result.score) if result.score is not None else None
        if score is not None and not np.isfinite(score):
            raise ValueError(f"Nonfinite store score for node {node.node_id}")
        hits.append({
            "rank": rank, "store_rank": store_rank,
            "node_id": node.node_id, "source_id": node.metadata["source_id"],
            "store_score": score, "cosine": cosine,
            "character_length": len(text), "token_length": count,
            "truncated": count > limit, "embedded_token_length": min(count, limit),
            "max_seq_length": limit, "preview": text[:160],
            "retrieved_text": node.text, "embedding_text": text, "context_text": context,
            "context_character_length": len(context),
            "context_token_length": token_length(context, tokenizer),
            "document_vector_shape": list(vector.shape),
            "document_embedding_first8": vector[:8].tolist(),
        })
    query_tokens = token_length(query, tokenizer)
    inferred_techniques = {hit.node.metadata.get("technique") for _, hit in ranked}
    if technique is None and len(inferred_techniques) == 1:
        technique = inferred_techniques.pop()
    diagnostics = []
    if not hits:
        diagnostics.append("No results returned; cosine metrics are undefined and source recall is zero.")
    elif len(hits) < k:
        diagnostics.append(f"Only {len(hits)} of {k} requested results returned; averages use actual hits.")
    record = {
        "question_id": question["id"], "question": query,
        "designation": question.get("designation", "baseline"),
        "expected_source_ids": list(question["expected_source_ids"]), "technique": technique,
        "query_embedding_dimension": int(query_vector.size),
        "query_embedding_first8": query_vector[:8].tolist(),
        "query_vector_shape": list(query_vector.shape),
        "document_vector_shape": [len(documents), int(query_vector.size)],
        "query_character_length": len(query), "query_token_length": query_tokens,
        "query_truncated": query_tokens > limit,
        "max_seq_length": limit, "token_lengths_include_special_tokens": True,
        "requested_k": k, "returned_k": len(hits),
        "unmeasured_warmup_searches": 1, "search_seconds": samples,
        "mean_search_seconds": float(np.mean(samples)),
        "timing_scope": "retriever.retrieve with precomputed query embedding; excludes embedding and index creation",
        "hits": hits, "diagnostics": diagnostics,
    }
    return record, {"query": query_values, "documents": documents}
