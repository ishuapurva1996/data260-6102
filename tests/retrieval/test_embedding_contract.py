import numpy as np
import pytest

from src.retrieval.embedding import validate_vectors, load_embedding


def test_normalized_vectors_required():
    assert validate_vectors([[1.0, 0.0]]) == (1, 2)
    for bad in ([[0.0, 0.0]], [[float('nan'), 0]], [[2., 0.]]):
        with pytest.raises(ValueError):
            validate_vectors(bad)


def test_no_paid_fallback_for_missing_model(tmp_path):
    with pytest.raises(RuntimeError, match='download-model'):
        load_embedding({'model_name': 'absent/model', 'model_revision': 'missing',
                        'max_seq_length': 256, 'threads': 1}, tmp_path)
