#!/usr/bin/env python3
"""Interrupt the real browser runner after confirmed creation, using its own port.

Requires the same private configuration and built frontend as the runtime runner.
Never resets the database. A failed regression attempts guarded recovery of only
the exact row identified by its browser checkpoint and records that separately.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]


def descendants(pid):
    pairs = [tuple(map(int, line.split())) for line in subprocess.check_output(
        ['ps', '-axo', 'pid=,ppid='], text=True).splitlines()]
    owned = {pid}
    while True:
        expanded = owned | {child for child, parent in pairs if parent in owned}
        if expanded == owned:
            return sorted(owned)
        owned = expanded


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--node', default='node')
    parser.add_argument('--port', type=int, default=8712)
    parser.add_argument('--raw-dir', type=Path, required=True)
    parser.add_argument('--screenshots-dir', type=Path, required=True)
    args = parser.parse_args()
    load_dotenv(args.env_file)
    raw = args.raw_dir.resolve()
    raw.mkdir(parents=True, exist_ok=True)
    evidence = {'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'running',
                'revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'source_sha256': {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in (
                    'tests/browser_hw04_part1.cjs', 'tests/browser_hw04_part1_runtime.py',
                    'tests/check_hw04_part1_interruption.py')}, 'port': args.port, 'checks': []}
    engine = create_engine(os.environ['HW4_DATABASE_URL'], hide_parameters=True,
                           connect_args={'connect_timeout': 5, 'read_timeout': 5, 'write_timeout': 5})
    child = record = None

    def check(name, ok, **details):
        evidence['checks'].append({'name': name, 'passed': bool(ok), **details})
        print(f'{"PASS" if ok else "FAIL"} [INTERRUPTION] {name}', flush=True)
        if not ok:
            raise AssertionError(name)

    def fingerprint(connection):
        rows = [dict(row) for row in connection.execute(text('SELECT * FROM rentals ORDER BY id')).mappings()]
        return sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()

    try:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', args.port))
        with engine.connect() as connection:
            before = fingerprint(connection)
        with tempfile.TemporaryDirectory(prefix='hw4-interruption-') as temporary:
            checkpoint = Path(temporary) / 'created.json'
            command = [sys.executable, str(ROOT / 'tests/browser_hw04_part1_runtime.py'),
                       '--env-file', str(args.env_file), '--node', args.node, '--port', str(args.port),
                       '--raw-dir', str(raw / 'runtime'), '--screenshots-dir', str(args.screenshots_dir.resolve())]
            with (raw / 'runner.txt').open('w') as output:
                child = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                         env=dict(os.environ, HW4_CREATED_CHECKPOINT_FILE=str(checkpoint)),
                                         start_new_session=True)
                deadline = time.monotonic() + 100
                while not checkpoint.exists():
                    if child.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError('Runner did not reach the confirmed-create checkpoint')
                    time.sleep(.1)
                record = json.loads(checkpoint.read_text())
                evidence['checkpoint'] = record
                journal_path = Path(record['cleanup_journal'])
                journal = json.loads(journal_path.read_text())
                check('Confirmed ID is persisted in a private per-run journal',
                      journal['record_id'] == record['record_id'] and journal['run_id'] == record['run_id']
                      and journal['phase'] == 'created' and stat.S_IMODE(journal_path.stat().st_mode) == 0o600
                      and stat.S_IMODE(journal_path.parent.stat().st_mode) == 0o700)
                with engine.connect() as connection:
                    row = connection.execute(text('SELECT description, submitter_email FROM rentals WHERE id=:id'),
                                             {'id': record['record_id']}).mappings().one()
                    check('Real POST completed and exact owned rental exists before interruption',
                          record['post_status'] == 201 and dict(row) == {
                              'description': record['description'], 'submitter_email': record['submitter_email']})
                owned = descendants(child.pid)
                evidence['owned_pids_at_interrupt'] = owned
                child.send_signal(signal.SIGTERM)
                returncode = child.wait(timeout=40)
            runtime = json.loads((raw / 'runtime/runtime.json').read_text())
            check('Runtime records interruption and exits with SIGTERM status',
                  returncode == 143 and runtime['status'] == 'interrupted' and runtime['signal'] == signal.SIGTERM,
                  returncode=returncode, runtime_status=runtime['status'])
            check('Wrapper records exact-row cleanup after browser termination',
                  runtime['rental_cleanup']['status'] == 'deleted'
                  and runtime['rental_cleanup']['record_id'] == record['record_id']
                  and not journal_path.exists(), cleanup=runtime['rental_cleanup'])
            with engine.connect() as connection:
                count = connection.scalar(text('SELECT COUNT(*) FROM rentals WHERE id=:id'), {'id': record['record_id']})
                check('Confirmed-created rental is absent after interruption', count == 0, record_id=record['record_id'])
                check('All pre-existing rentals remain unchanged', fingerprint(connection) == before)
            deadline = time.monotonic() + 5
            while any(alive(pid) for pid in owned) and time.monotonic() < deadline:
                time.sleep(.1)
            check('Owned wrapper, API, Node and Chromium processes stopped', not any(alive(pid) for pid in owned),
                  process_count=len(owned))
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(('127.0.0.1', args.port))
            check('Isolated HTTPS port is released', True, port=args.port)
            evidence['status'] = 'pass'
    except Exception as error:
        evidence['status'] = 'fail'
        evidence['error_type'] = type(error).__name__
        # Exception messages from database drivers may expose private configuration.
        print(f'FAIL [INTERRUPTION] {type(error).__name__}', flush=True)
    finally:
        if child is not None and child.poll() is None:
            try:
                child.send_signal(signal.SIGTERM)
                child.wait(timeout=40)
            except Exception as error:
                evidence['status'] = 'fail'
                evidence['teardown_error_type'] = type(error).__name__
        if evidence['status'] != 'pass' and record is not None:
            try:
                with engine.begin() as connection:
                    row = connection.execute(text('SELECT description, submitter_email FROM rentals WHERE id=:id FOR UPDATE'),
                                             {'id': record['record_id']}).mappings().first()
                    if row is None:
                        evidence['regression_recovery'] = 'already_absent'
                    elif dict(row) == {'description': record['description'], 'submitter_email': record['submitter_email']}:
                        connection.execute(text('DELETE FROM rentals WHERE id=:id'), {'id': record['record_id']})
                        evidence['regression_recovery'] = 'deleted_exact_checkpoint_row'
                    else:
                        evidence['regression_recovery'] = 'ownership_mismatch_no_delete'
            except Exception as error:
                evidence['regression_recovery'] = {'status': 'failed', 'error_type': type(error).__name__}
        engine.dispose()
        evidence['finished_at'] = datetime.now(timezone.utc).isoformat()
        (raw / 'check.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return 0 if evidence['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
