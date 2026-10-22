"""Owned HTTPS subprocess for acceptance and smoke checks; caller owns lease."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[2]


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def port_busy():
    with socket.socket() as sock:
        sock.settimeout(.2)
        return sock.connect_ex(('127.0.0.1', 8702)) == 0


@contextmanager
def running_app(config, *, lease, directory, env_files, cert, key, credentials=None):
    if not lease.token or port_busy():
        raise RuntimeError('Hold the shared lease and use an unowned port 8702')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    config_file = directory / 'config.json'
    save(config_file, config.public_dict())
    command = [sys.executable, '-B', str(ROOT/'scripts/run_hw06_web.py'),
               '--runtime-dir', str(lease.runtime_dir), '--cert', str(cert), '--key', str(key),
               '--events', str(directory/'events.jsonl'), '--config-json', str(config_file),
               '--inherited-lease']
    for path in env_files:
        command += ['--env-file', str(path)]
    env = {**os.environ, 'HW6_PARENT_LEASE_TOKEN': lease.token,
           'PYTHONPATH': str(ROOT)+os.pathsep+str(ROOT/'code'), 'PYTHONDONTWRITEBYTECODE': '1'}
    with (directory/'server.log').open('x') as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic()+30
            while not port_busy():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Owned application startup failed; inspect private server.log')
                time.sleep(.1)
            tls = ssl.create_default_context(cafile=str(cert))
            with httpx.Client(base_url='https://127.0.0.1:8702', verify=tls,
                              timeout=config.model_timeout*12, trust_env=False) as client:
                from scripts.hw07.client_auth import authenticate
                username, password = credentials or (os.environ['HW6_EXPERIMENT_USERNAME'],
                                                     os.environ['HW6_EXPERIMENT_PASSWORD'])
                user = authenticate(client, username, password)
                yield client, str(user['id'])
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


def add_runtime_arguments(parser):
    parser.add_argument('--env-file', type=Path, action='append', required=True)
    parser.add_argument('--runtime-dir', type=Path, required=True)
    parser.add_argument('--cert', type=Path, required=True)
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True,
                        help='Fresh external directory for private server logs and working fixtures')


def load_config(args):
    from dotenv import load_dotenv
    from src.hw06_shared.config import HW6Config
    from src.hw06_shared.runtime import source_revision
    for path in args.env_file:
        load_dotenv(path, override=True)
    base = HW6Config.from_env()
    return HW6Config(**{**base.model_dump(), 'source_commit': source_revision()})
