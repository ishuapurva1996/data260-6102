#!/usr/bin/env python3
"""Run the shared app with a local development TLS certificate (one worker)."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8702)
    parser.add_argument('--idle-timeout', type=float, default=300)
    parser.add_argument('--cert', type=Path, default=ROOT / 'tmp/https/cert.pem')
    parser.add_argument('--key', type=Path, default=ROOT / 'tmp/https/key.pem')
    parser.add_argument('--prepare-cert', action='store_true', help='Create certificate if absent, then exit')
    args = parser.parse_args()
    if not args.cert.exists() and not args.key.exists():
        args.cert.parent.mkdir(parents=True, exist_ok=True)
        args.key.parent.mkdir(parents=True, exist_ok=True)
        config = ROOT / 'tmp/https/openssl.cnf'
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('[req]\ndistinguished_name=dn\nx509_extensions=v3\nprompt=no\n'
                          '[dn]\nCN=localhost\n[v3]\nsubjectAltName=DNS:localhost,IP:127.0.0.1,IP:::1\n')
        old_umask = os.umask(0o077)
        try:
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                            '-keyout', str(args.key), '-out', str(args.cert), '-days', '30',
                            '-config', str(config)], check=True, capture_output=True)
        finally:
            os.umask(old_umask)
        args.key.chmod(0o600)
        print('Created local development certificate; no OS trust settings changed.')
    if not args.cert.is_file() or not args.key.is_file():
        parser.error('Both certificate and private key must exist; preserve or remove the incomplete pair manually.')
    if args.prepare_cert:
        print(f'Certificate ready: {args.cert}')
        return 0
    env = {**os.environ, 'IDLE_TIMEOUT_SECONDS': str(args.idle_timeout)}
    return subprocess.call([sys.executable, '-m', 'uvicorn', 'main:app', '--app-dir',
                            str(ROOT / 'code/web_application'), '--host', args.host,
                            '--port', str(args.port), '--workers', '1',
                            '--ssl-certfile', str(args.cert), '--ssl-keyfile', str(args.key)], env=env)


if __name__ == '__main__':
    raise SystemExit(main())
