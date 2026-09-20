"""Frozen experiment settings and local runtime paths."""
from pathlib import Path
import os
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = REPO_ROOT / 'reports/hw03'
TECHNIQUES = ('token', 'semantic', 'sentence_window')


def load_config(path=None):
    config = yaml.safe_load(Path(path or REPORT_ROOT / 'experiment_config.yaml').read_text())
    for key in ('model_name', 'model_revision', 'max_seq_length', 'threads', 'k', 'repeats'):
        if key not in config:
            raise ValueError(f'Missing setting: {key}')
    if config['k'] < 1 or config['repeats'] < 1:
        raise ValueError('k and repeats must be positive')
    return config


def model_cache():
    return Path(os.environ.get('HW3_MODEL_CACHE', REPO_ROOT / '.venv-retrieval/model-cache'))
