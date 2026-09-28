#!/usr/bin/env python3
"""Own the Part 1 HTTPS browser evidence slot, including restart and idle expiry.

Uses an existing migrated MySQL database. Never seeds/resets data, prints secrets,
changes application source, or stops a server it did not start. NODE_PATH may point
at a preinstalled Playwright package; otherwise use the root npm dependencies.
"""
import argparse
from datetime import datetime, timezone
import json
from hashlib import sha256
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from uuid import UUID, uuid4

import httpx
from dotenv import load_dotenv
from sqlalchemy import column, create_engine, delete, select, table, text

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'reports/hw04/raw/part1'


def cleanup_rental(journal_path, engine):
    """Delete one proven-owned test row; retain the private journal on uncertainty.

    The caller must first stop its browser and API, allowing in-flight SQL to
    finish. Exact marker recovery covers a POST committed before its ID reached
    the journal. No title/prefix matching or unguarded multi-row DELETE is used.
    """
    result = {'status': 'failed', 'recovery_journal': str(journal_path)}
    try:
        journal = json.loads(journal_path.read_text())
        run_id, record_id = journal['run_id'], journal['record_id']
        if (journal['schema_version'] != 1 or str(UUID(run_id)) != run_id
                or journal['phase'] not in ('not_started', 'create_pending', 'created')
                or (record_id is not None and (type(record_id) is not int or record_id <= 0))
                or (journal['phase'] == 'created' and record_id is None)
                or (journal['phase'] == 'not_started' and record_id is not None)):
            raise ValueError('Invalid cleanup journal')
        result['record_id'] = record_id
        status = 'not_created'
        if journal['phase'] != 'not_started':
            marker, email = f'HW4 Part 1 browser cleanup run {run_id}', f'{run_id}@example.com'
            rentals = table('rentals', column('id'), column('description'), column('submitter_email'))
            ownership = (rentals.c.description == marker) & (rentals.c.submitter_email == email)
            selection = rentals.c.id == record_id if record_id is not None else ownership
            with engine.begin() as connection:
                matches = connection.execute(select(rentals).where(selection).limit(2).with_for_update()).mappings().all()
                if len(matches) > 1:
                    return dict(result, status='ambiguous')
                if matches:
                    row = matches[0]
                    # Compare in Python too: MySQL text collation can ignore case.
                    if row['description'] != marker or row['submitter_email'] != email:
                        return dict(result, status='ownership_mismatch')
                    result['record_id'] = row['id']
                    deleted = connection.execute(delete(rentals).where((rentals.c.id == row['id']) & ownership))
                    if deleted.rowcount != 1:
                        raise RuntimeError('Exact owned row was not deleted')
                    status = 'deleted'
                elif record_id is not None:
                    status = 'already_absent'
        # Only discard recovery information after the transaction commits.
        journal_path.unlink()
        result.pop('recovery_journal')
        return dict(result, status=status)
    except Exception as error:
        # Driver messages can contain a database URL or password.
        return dict(result, status='failed', error_type=type(error).__name__)


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
                'source_sha256': {str(Path(__file__).relative_to(ROOT)): sha256(Path(__file__).read_bytes()).hexdigest()},
                'status': 'running', 'base_url': f'https://127.0.0.1:{args.port}',
                'production_idle_seconds': 300, 'absolute_seconds': 3600,
                'expiry_demonstration_idle_seconds': 2, 'processes': [], 'browser_processes': [], 'checks': []}
    process = browser = None
    run_id = str(uuid4())
    (ROOT / 'tmp').mkdir(exist_ok=True)
    # Outside TemporaryDirectory: failures must retain recovery information.
    journal_dir = Path(tempfile.mkdtemp(prefix='hw4-part1-cleanup-', dir=ROOT / 'tmp'))
    journal = journal_dir / 'rental.json'
    with open(journal, 'x', opener=lambda name, flags: os.open(name, flags, 0o600)) as output:
        json.dump({'schema_version': 1, 'run_id': run_id, 'record_id': None, 'phase': 'not_started'}, output)
        output.flush()
        os.fsync(output.fileno())
    evidence['cleanup_run_id'] = run_id
    base = evidence['base_url']
    private_env = dict(os.environ, HW4_BASE_URL=base, HW4_RAW_DIR=str(raw),
                       HW4_SCREENSHOTS_DIR=str(args.screenshots_dir.resolve()),
                       HW4_CLEANUP_RUN_ID=run_id, HW4_CLEANUP_JOURNAL=str(journal))
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
        if process is not None:
            stop_owned(process)
            evidence['processes'][-1]['stopped_at'] = datetime.now(timezone.utc).isoformat()
            evidence['processes'][-1]['returncode'] = process.returncode
        process = None

    def stop_owned(child):
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)

    def interrupted(signum, _frame):
        evidence['status'] = 'interrupted'
        evidence['signal'] = signum
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
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
                evidence['browser_processes'].append({'pid': browser.pid, 'mode': 'real'})
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
                evidence['browser_processes'][-1]['returncode'] = browser.returncode
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
                evidence['browser_processes'].append({'pid': browser.pid, 'mode': 'expiry'})
                check('Real browser idle expiry suite passed', browser.wait(timeout=90) == 0)
            evidence['status'] = 'pass'
    except Exception as error:
        # Avoid serializing exception strings from database/network clients: they may contain configuration.
        evidence['status'] = 'fail'
        evidence['error_type'] = type(error).__name__
        print(f'FAIL [RUNTIME] {type(error).__name__}; inspect the sanitized browser logs.', flush=True)
        raise SystemExit(1) from None
    finally:
        # A second Ctrl-C must not interrupt bounded cleanup and evidence writing.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        evidence['teardown_errors'] = []
        if browser is not None:
            try:
                stop_owned(browser)
                evidence['browser_processes'][-1].update(returncode=browser.returncode,
                    stopped_at=datetime.now(timezone.utc).isoformat())
            except Exception as error:
                evidence['teardown_errors'].append({'process': 'browser', 'error_type': type(error).__name__})
        try:
            stop()
        except Exception as error:
            evidence['teardown_errors'].append({'process': 'api', 'error_type': type(error).__name__})
        engine = None
        try:
            if evidence['teardown_errors']:
                evidence['rental_cleanup'] = {'status': 'failed', 'reason': 'process_teardown_incomplete',
                                              'recovery_journal': str(journal)}
            else:
                engine = create_engine(os.environ['HW4_DATABASE_URL'], hide_parameters=True,
                                       connect_args={'connect_timeout': 5, 'read_timeout': 5, 'write_timeout': 5})
                evidence['rental_cleanup'] = cleanup_rental(journal, engine)
                if not journal.exists():
                    try:
                        journal.with_name(journal.name + '.next').unlink(missing_ok=True)
                        journal_dir.rmdir()
                    except OSError as error:
                        # Rental cleanup already committed; directory housekeeping
                        # must not claim a nonexistent recovery journal is needed.
                        evidence['journal_directory_cleanup_error_type'] = type(error).__name__
        except Exception as error:
            evidence['rental_cleanup'] = {'status': 'failed', 'error_type': type(error).__name__,
                                          'recovery_journal': str(journal)}
        finally:
            if engine is not None:
                engine.dispose()
        if evidence['rental_cleanup']['status'] not in ('deleted', 'already_absent', 'not_created'):
            # Keep interruption as the primary outcome; never report a clean pass.
            if evidence['status'] == 'pass':
                evidence['status'] = 'fail'
        evidence['finished_at'] = datetime.now(timezone.utc).isoformat()
        (raw / 'runtime.json').write_text(json.dumps(evidence, indent=2) + '\n')
        print(f"CLEANUP [RUNTIME] {evidence['rental_cleanup']['status']}", flush=True)
    return 0 if evidence['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
