"""CPU-only local embeddings. Download is explicit; experiments run offline."""
import os
from pathlib import Path
import numpy as np


def validate_vectors(vectors):
    matrix = np.asarray(vectors, dtype=float)
    if matrix.ndim != 2 or not matrix.shape[0] or not np.isfinite(matrix).all():
        raise ValueError('Expected a nonempty finite vector matrix')
    if not np.allclose(np.linalg.norm(matrix, axis=1), 1.0, atol=1e-5):
        raise ValueError('Expected normalized, nonzero vectors')
    return matrix.shape


def download_model(config, cache):
    from huggingface_hub import snapshot_download
    return snapshot_download(config['model_name'], revision=config['model_revision'],
                             cache_dir=str(cache), allow_patterns=[
                                 '*.json', '*.txt', '*.safetensors', '1_Pooling/*', '*.md'])


def load_embedding(config, cache):
    # Prevent telemetry and accidental network fallbacks in all graded runs.
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    os.environ['OMP_NUM_THREADS'] = str(config['threads'])
    os.environ['MKL_NUM_THREADS'] = str(config['threads'])
    from huggingface_hub import snapshot_download
    try:
        local = snapshot_download(config['model_name'], revision=config['model_revision'],
                                  cache_dir=str(cache), local_files_only=True,
                                  allow_patterns=['*.json', '*.txt', '*.safetensors', '1_Pooling/*', '*.md'])
    except Exception as exc:
        raise RuntimeError('Local model assets missing. Run code/retrieval_compare.py download-model first.') from exc
    import torch
    from llama_index.core import Settings
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    torch.set_num_threads(config['threads'])
    torch.manual_seed(config.get('seed', 6102))
    np.random.seed(config.get('seed', 6102))
    Settings.llm = None
    try:
        model = HuggingFaceEmbedding(model_name=local, cache_folder=str(cache), device='cpu', normalize=True,
                                     max_length=config['max_seq_length'],
                                     embed_batch_size=config.get('batch_size', 32),
                                     local_files_only=True, trust_remote_code=False)
    except Exception as exc:
        raise RuntimeError('Local model failed to load; rerun download-model and inspect pinned dependencies.') from exc
    if model._model.max_seq_length != config['max_seq_length']:
        raise ValueError('Runtime truncation limit differs from frozen configuration')
    return model
