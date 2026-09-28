#!/usr/bin/env python3
"""Own the Part 1 HTTPS browser evidence slot, including restart and idle expiry.

Uses an existing migrated MySQL database. Never seeds/resets data, prints secrets,
changes application source, or stops a server it did not start. NODE_PATH may point
at a preinstalled Playwright package; otherwise use the root npm dependencies.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time

import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'reports/hw04/raw/part1'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--node', default='node')
    parser.add_argument('--port', type=int, default=8702)
    parser.add_argument('--raw-dir', type=Path, default=RAW)
    parser.add_argument('--screenshots-dir', type=Path, default=ROOT / 'reports/hw04/screenshots/part1')
    args = parser.parse_args()
    raw = args.raw_dir.resolve()
    load_dotenv(args.env_file)
    raw.mkdir(parents=True, exist_ok=True)
    evidence = {'started_at': datetime.now(timezone.utc).isoformat(),
                'revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'status': 'running', 'base_url': f'https://127.0.0.1:{args.port}',
                'production_idle_seconds': 300, 'absolute_seconds': 3600,
                'expiry_demonstration_idle_seconds': 2, 'processes': [], 'checks': []}
    process = browser = None
    base = evidence['base_url']
    private_env = dict(os.environ, HW4_BASE_URL=base, HW4_RAW_DIR=str(raw),
                       HW4_SCREENSHOTS_DIR=str(args.screenshots_dir.resolve()))
    credentials = {'email': os.environ['HW4_SEED_EMAIL'], 'password': os.environ['HW4_SEED_PASSWORD']}

    def check(name, ok, **details):
        evidence['checks'].append({'name': name, 'passed': bool(ok), **details})
        if not ok:
            raise AssertionError(name)
        print(f'PASS [RUNTIME] {name}', flush=True)

    def port_free():
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', args.port))

    def start(expiry=False):
        nonlocal process
        port_free()
        if expiry:
            app = 'from web_application.main import create_app\ndef make_app():\n    return create_app(idle_timeout=2)\n'
            (scratch / 'expiry_app.py').write_text(app)
            target = 'expiry_app:make_app'
            app_dir = scratch
        else:
            target = 'web_application.main:app'
            app_dir = ROOT / 'code'
        env = dict(private_env, PYTHONPATH=str(ROOT / 'code'))
        command = [sys.executable, '-m', 'uvicorn', target, '--app-dir', str(app_dir),
                   '--host', '127.0.0.1', '--port', str(args.port), '--workers', '1',
                   '--timeout-graceful-shutdown', '2', '--ssl-certfile', str(ROOT / 'tmp/https/cert.pem'),
                   '--ssl-keyfile', str(ROOT / 'tmp/https/key.pem')]
        if expiry:
            command.append('--factory')
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
        evidence['processes'].append({'pid': process.pid, 'idle_timeout_seconds': 2 if expiry else 300,
                                     'started_at': datetime.now(timezone.utc).isoformat()})
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError('Owned server exited before readiness')
            try:
                with httpx.Client(verify=False, trust_env=False, timeout=2) as client:
                    if client.get(base + '/api/health').status_code == 200:
                        return
            except httpx.TransportError:
                pass
            time.sleep(.1)
        raise RuntimeError('Owned server readiness timed out')

    def stop():
        nonlocal process
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            evidence['processes'][-1]['stopped_at'] = datetime.now(timezone.utc).isoformat()
        process = None

    try:
        port_free()
        subprocess.run([sys.executable, str(ROOT / 'scripts/run_hw04_web.py'), '--prepare-cert'], check=True, cwd=ROOT)
        with create_engine(os.environ['HW4_DATABASE_URL'], hide_parameters=True).connect() as connection:
            evidence['mysql_version'] = connection.scalar(text('SELECT VERSION()'))
            check('MySQL evidence database is s6102_rel', connection.scalar(text('SELECT DATABASE()')) == 's6102_rel')
        with tempfile.TemporaryDirectory(prefix='hw4-part1-') as temporary:
            scratch = Path(temporary)
            ready, done = scratch / 'ready.json', scratch / 'done'
            start()
            env = dict(private_env, HW4_RESTART_READY_FILE=str(ready), HW4_RESTART_DONE_FILE=str(done))
            with (raw / 'real-browser.txt').open('w') as output:
                browser = subprocess.Popen([args.node, 'tests/browser_hw04_part1.cjs', '--real'], cwd=ROOT,
                                           env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                deadline = time.monotonic() + 120
                while not ready.exists():
                    if browser.poll() is not None:
                        raise RuntimeError('Browser exited before restart checkpoint; see real-browser.txt')
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Browser restart checkpoint timed out')
                    time.sleep(.1)
                old_pid = process.pid
                stop()
                start()
                check('Backend restarted during browser workflow', process.pid != old_pid,
                      before_pid=old_pid, after_pid=process.pid)
                done.write_text(datetime.now(timezone.utc).isoformat())
                check('Real browser suite passed', browser.wait(timeout=120) == 0)
            result = json.loads((raw / 'real-browser.json').read_text())
            deleted_id = next(item['details']['deleted_id'] for item in result['checks']
                              if item['name'].startswith('Delete direct URL'))
            stop()
            start()
            with httpx.Client(base_url=base, verify=False, trust_env=False, timeout=10) as client:
                check('Login after second restart', client.post('/api/auth/login', json=credentials).status_code == 200)
                response = client.get(f'/api/rentals/{deleted_id}')
                check('Deleted rental stays absent after second restart', response.status_code == 404,
                      record_id=deleted_id, get_status=response.status_code)
                client.post('/api/auth/logout')
            stop()
            start(expiry=True)
            with (raw / 'expiry-browser.txt').open('w') as output:
                browser = subprocess.Popen([args.node, 'tests/browser_hw04_part1.cjs', '--expiry'], cwd=ROOT,
                                           env=dict(private_env, HW4_EXPIRY_TEST='2'), stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                check('Real browser idle expiry suite passed', browser.wait(timeout=90) == 0)
            evidence['status'] = 'pass'
    except Exception as error:
        # Avoid serializing exception strings from database/network clients: they may contain configuration.
        evidence['status'] = 'fail'
        evidence['error_type'] = type(error).__name__
        print(f'FAIL [RUNTIME] {type(error).__name__}; inspect the sanitized browser logs.', flush=True)
        raise SystemExit(1) from None
    finally:
        if browser is not None and browser.poll() is None:
            os.killpg(browser.pid, signal.SIGTERM)
            try:
                browser.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(browser.pid, signal.SIGKILL)
                browser.wait(timeout=5)
        stop()
        evidence['finished_at'] = datetime.now(timezone.utc).isoformat()
        (raw / 'runtime.json').write_text(json.dumps(evidence, indent=2) + '\n')


if __name__ == '__main__':
    main()
