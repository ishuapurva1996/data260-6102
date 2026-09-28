"""General dense/BM25 retrieval fusion over the caller's approved chunks.

No question identifiers, answer keys, source preferences, or network resources
are used. Sparse scores use positive Robertson/Lucene BM25 IDF and Porter
stemming when the already-installed NLTK package is available. Reciprocal rank
fusion (RRF) combines the dense ranking with positive-scoring sparse matches.
The original dense cosine ``score`` is preserved for downstream filtering.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Mapping, Sequence

try:
    from nltk.stem import PorterStemmer
except ImportError:  # No installation or corpus download is attempted here.
    _stemmer = None
    STEMMER = "none"
else:
    _stemmer = PorterStemmer()
    STEMMER = "nltk.PorterStemmer"

BM25_K1 = 1.5
BM25_B = 0.75
RRF_K = 60
# Deliberately small and domain-independent. Numbers, negation, actors, and
# substantive verbs remain available for matching.
_STOPWORDS = frozenset("a an and are as at be by for from in is it of on or that the this to was were with".split())


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.casefold())
    words = [word for word in words if word not in _STOPWORDS]
    return [_stemmer.stem(word) for word in words] if _stemmer else words


def _identity(hit: Mapping) -> tuple:
    return str(hit["source_id"]), int(hit["start"]), str(hit["chunk_id"])


def hybrid_rank(question: str, dense_hits: Sequence[Mapping]) -> list[dict]:
    """Return ranked copies using BM25 (1.5, .75) plus dense RRF (60).

    The caller must supply all approved chunks, each with its actual dense
    cosine score, so BM25 document frequencies describe the same corpus.
    Dense, lexical, and fusion ranks are one-based with deterministic tie
    breaking. Zero lexical scores have ``lexical_rank=None`` and contribute
    nothing to fusion. An empty/unmatched lexical query therefore preserves
    the dense order rather than inventing a lexical ranking from zero ties.
    """
    rows = [dict(hit) for hit in dense_hits]
    if not rows:
        return []
    if len({row["chunk_id"] for row in rows}) != len(rows):
        raise ValueError("Hybrid retrieval requires unique chunk IDs")
    if any(not math.isfinite(float(row["score"])) for row in rows):
        raise ValueError("Dense retrieval scores must be finite")
    rows.sort(key=lambda row: (-float(row["score"]), _identity(row)))
    documents = [Counter(_tokens(row["text"])) for row in rows]
    lengths = [sum(document.values()) for document in documents]
    average_length = sum(lengths) / len(rows)
    document_frequency = Counter(term for document in documents for term in document)
    # Standard BM25 counts each distinct query term once; repeating a term in
    # natural question wording must not silently become an extra query weight.
    query_terms = set(_tokens(question))
    for dense_rank, (row, document, length) in enumerate(zip(rows, documents, lengths), 1):
        score = 0.0
        if average_length:
            normalization = BM25_K1 * (1 - BM25_B + BM25_B * length / average_length)
            # Sorting also makes floating-point accumulation repeatable across
            # Python hash randomization and input permutations.
            for term in sorted(query_terms & document.keys()):
                frequency = document[term]
                idf = math.log1p((len(rows) - document_frequency[term] + 0.5) /
                                (document_frequency[term] + 0.5))
                score += idf * frequency * (BM25_K1 + 1) / (frequency + normalization)
        row.update(dense_rank=dense_rank, lexical_score=score, lexical_rank=None)
    lexical_rows = sorted((row for row in rows if row["lexical_score"] > 0),
                          key=lambda row: (-row["lexical_score"], _identity(row)))
    for lexical_rank, row in enumerate(lexical_rows, 1):
        row["lexical_rank"] = lexical_rank
    for row in rows:
        row["fusion_score"] = 1 / (RRF_K + row["dense_rank"])
        if row["lexical_rank"] is not None:
            row["fusion_score"] += 1 / (RRF_K + row["lexical_rank"])
    rows.sort(key=lambda row: (-row["fusion_score"], row["dense_rank"], _identity(row)))
    for fusion_rank, row in enumerate(rows, 1):
        row["fusion_rank"] = fusion_rank
    return rows
