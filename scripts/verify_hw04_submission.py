#!/usr/bin/env python3
"""Prepare offline evidence, or smoke-test the exact hw4 tag without reseeding.

Only --tagged opens private configuration or starts HTTPS. Final verification.json
is written only after every tagged check passes; failed attempts are separate.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PREPARATION = Path('reports/hw04/raw/report-finalization')
PART4 = Path('reports/hw04/raw/part4/scored-20260928-04')
BENCHMARK = Path('reports/hw04/raw/part3/attempts/20260928T003859.945761Z-cd277c20')
SOURCE_DIRS = ('code', 'src', 'scripts', 'tests', 'frontend/src')
SOURCE_SUFFIXES = {'.py', '.js', '.cjs', '.mjs', '.jsx', '.ts', '.tsx', '.sql', '.json', '.css', '.html', '.toml', '.yaml', '.yml', '.txt'}


class VerificationError(ValueError):
    """A sanitized, actionable verification failure."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()


def is_receipt(path):
    path = Path(path)
    return path == Path('verification.json') or path.is_relative_to(PREPARATION)


def source_fingerprints(root):
    paths = {p for directory in SOURCE_DIRS for p in (root/directory).rglob('*')
             if p.is_file() and p.suffix in SOURCE_SUFFIXES and '__pycache__' not in p.parts}
    paths.update(root.glob('requirements*.txt'))
    paths.update(p for p in (root/'frontend').glob('*')
                 if p.is_file() and p.suffix in SOURCE_SUFFIXES)
    require(all(p.resolve().is_relative_to(root.resolve()) for p in paths), 'Source symlink escapes checkout')
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def tagged_state(root):
    try:
        tagged = git(root, 'rev-parse', '--verify', 'refs/tags/hw4^{commit}')
    except subprocess.CalledProcessError:
        raise VerificationError('The hw4 tag is missing; final tagged verification is pending') from None
    require(git(root, 'rev-parse', 'HEAD') == tagged, 'HEAD must equal the hw4 tagged commit')
    changes = git(root, 'diff', '--name-only', '-z', tagged).split('\0')
    untracked = git(root, 'ls-files', '--others', '--exclude-standard', '-z').split('\0')
    pending = sorted(p for p in changes + untracked if p and not is_receipt(p))
    require(not pending, 'Uncommitted submission files differ from hw4: ' + ', '.join(pending[:8]))
    tracked = set(git(root, 'ls-tree', '-r', '--name-only', '-z', tagged).split('\0'))
    require(set(source_fingerprints(root)) <= tracked, 'Application/verifier source contains files absent from hw4, including ignored source')
    return tagged


def output_path(root, requested, *, tagged):
    root = root.resolve()
    path = (root/requested).resolve()
    if tagged:
        require(path == root/'verification.json', 'Tagged success output must be root verification.json')
    else:
        allowed = root/PREPARATION
        require(path.is_relative_to(allowed) and path.suffix == '.json' and path.name != 'verification.json',
                'Preparation/failed output must be a partial JSON under reports/hw04/raw/report-finalization')
    return path


def module(root, relative):
    path = root/relative
    spec = importlib.util.spec_from_file_location('hw4_submission_' + path.stem, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def validate_benchmark_configuration(values, manifest, config):
    """Bind the saved rows to the saved configuration, not today's runtime."""
    digest = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':'),
                                      ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    require(values['request_count'] == manifest['measured_requests'] == 180
            and manifest['status'] == 'success', 'Selected measured attempt is incomplete')
    require(values['dirty'] is False and manifest['dirty'] is False,
            'Selected measurements must retain their clean measured revision')
    require(all(values[key] == manifest[key] for key in ('run_id', 'code_revision', 'config_sha256'))
            and config == manifest['config'] and digest == values['config_sha256'],
            'Saved measurement rows, manifest, and benchmark configuration differ')


def offline_checks(root):
    """Recheck frozen artifacts without calling databases, models, or browsers."""
    checks, metadata = [], {}
    sys.path.insert(0, str(root))
    try:
        partial = json.loads((root/'reports/hw04/verification.parts123.json').read_text())
        rows = partial['checks']
        require(partial['status'] == 'pass' and bool(rows) and all(c.get('passed') is True for c in rows),
                'Saved Parts 1-3 receipt contains incomplete or failed checks')
        checks.append({'name': 'saved_parts123_receipt', 'passed': True, 'evidence_scope': 'historical', 'check_count': len(rows)})
    except Exception as error:
        checks.append({'name': 'saved_parts123_receipt', 'passed': False, 'error_type': type(error).__name__})
    try:
        summary = module(root, 'scripts/hw04/part3/summarize.py')
        values = summary.summarize_rows(summary.read_rows(root/BENCHMARK/'requests.jsonl'))
        manifest = json.loads((root/BENCHMARK/'manifest.json').read_text())
        config = json.loads((root/'reports/hw04/raw/part3/benchmark_config.json').read_text())
        validate_benchmark_configuration(values, manifest, config)
        metadata['benchmark_configuration'] = {
            'scope': 'historical measured configuration; not the current live smoke configuration',
            'run_id': values['run_id'], 'measured_commit': values['code_revision'], 'config_sha256': values['config_sha256'],
            'page_sizes': manifest['page_sizes'], 'requests_per_group': manifest['requests_per_group'],
            'worker_count': config['worker_count'], 'reload': config['reload'], 'seed': config['seed'],
            'dataset_rows': {'rentals': config['rental_count'], 'managers': config['manager_count']},
            'title_index_present': config['index_state']['title_index_present']} 
        checks.append({'name': 'saved_180_measurements_integrity', 'passed': True, 'evidence_scope': 'historical',
                       'requests': 180, 'measured_commit': values['code_revision'], 'run': BENCHMARK.as_posix()})
    except Exception as error:
        checks.append({'name': 'saved_180_measurements_integrity', 'passed': False, 'error_type': type(error).__name__})
    try:
        part4 = module(root, 'scripts/verify_hw04_part4.py').verify(
            root/PART4, root/'reports/hw04/part4/REPORT_SECTION.md', root=root)
        require(part4['total'] == 13 and len(part4['checks']) == 13, 'Expected the selected 13-check offline Part 4 contract')
        for check in part4['checks']:
            checks.append({**check, 'name': 'part4:' + check['name'], 'evidence_scope': 'frozen_historical'})
        metadata['part4_assessment'] = part4['assessment_summary']
        metadata['part4_limitations'] = part4['limitations']
        config = json.loads((root/PART4/'frozen/experiment_config.json').read_text())
        metadata['models'] = {'scope': 'frozen historical Part 4; no new model calls',
                              'answer': config['generator'], 'answer_digest': config['generator_digest'],
                              'question_classifier': config['clarification_model']['generator'],
                              'question_classifier_digest': config['clarification_model']['generator_digest'],
                              'embedding': config['model_name'], 'embedding_revision': config['model_revision']}
        metadata['rag_configuration'] = {key: config[key] for key in ('options', 'chunk_size', 'chunk_overlap', 'chunk_unit', 'k', 'relevance_cutoff', 'evidence_budget', 'deduplication', 'ordering')}
    except Exception as error:
        checks.append({'name': 'part4_offline_verifier', 'passed': False, 'error_type': type(error).__name__})
    return checks, metadata


def load_private_env(path):
    """Never call during preparation; never return config values in a receipt."""
    from dotenv import dotenv_values
    from sqlalchemy.engine import make_url
    values = dotenv_values(path, interpolate=False)
    required = ('HW4_DATABASE_URL', 'HW4_SEED_EMAIL', 'HW4_SEED_PASSWORD')
    require(all(isinstance(values.get(k), str) and values[k] for k in required), 'Private environment must supply database URL and seed-account credentials')
    try:
        url = make_url(values['HW4_DATABASE_URL'])
        require(url.drivername == 'mysql+pymysql' and url.database == 's6102_rel'
                and url.host in ('127.0.0.1', 'localhost', '::1'), 'Private configuration must name loopback MySQL s6102_rel')
    except (ValueError, TypeError):
        raise VerificationError('Invalid private MySQL configuration') from None
    return {key: values[key] for key in required}, (url.host, url.port or 3306, url.database)


def assert_port_free():
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', 8702))
        except OSError:
            raise VerificationError('Port 8702 is unavailable; refusing to reuse or stop another server') from None


def stop_owned(process):
    """Use only the process group created by this invocation, even on failure."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


@contextmanager
def owned_server(root, private, env_path):
    import httpx
    assert_port_free()
    cert, key = root/'tmp/https/cert.pem', root/'tmp/https/key.pem'
    require(cert.is_file() and key.is_file(), 'Prepare the existing launcher TLS certificate/key before the tagged run')
    environment = {k: v for k, v in os.environ.items() if not k.startswith('HW4_')}
    environment.update(private, PYTHONDONTWRITEBYTECODE='1')
    client = httpx.Client(base_url='https://127.0.0.1:8702', verify=str(cert), timeout=10, trust_env=False)
    process = None
    try:
        process = subprocess.Popen([sys.executable, str(root/'scripts/run_hw04_web.py'), '--host', '127.0.0.1',
                                '--port', '8702', '--env-file', str(env_path), '--cert', str(cert), '--key', str(key)],
                               cwd=root, env=environment, start_new_session=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            require(process.poll() is None, 'Owned HTTPS launcher exited before readiness')
            try:
                if client.get('/api/health', timeout=1).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(.1)
        else:
            raise VerificationError('Owned HTTPS backend did not become ready')
        require(process.poll() is None, 'Owned HTTPS launcher exited during readiness')
        yield client
    finally:
        try:
            client.close()
        finally:
            if process is not None:
                stop_owned(process)
                deadline = time.monotonic() + 5
                while True:
                    try:
                        assert_port_free()
                        break
                    except VerificationError:
                        if time.monotonic() >= deadline:
                            raise VerificationError('Port 8702 did not become free after owned-server cleanup') from None
                        time.sleep(.1)


def performance_pair(naive, fixed, size):
    require(naive.status_code == fixed.status_code == 200, 'Performance endpoints must both respond 200')
    left, right = naive.json(), fixed.json()
    require(isinstance(left, list) and isinstance(right, list) and len(left) == len(right) == size and left == right,
            'Naive/fixed data payloads must match with the requested number of rows')
    require(all(isinstance(r, dict) and isinstance(r.get('id'), int) and r['id'] > 0
                and isinstance(r.get('manager'), dict) and r['manager'].get('id') for r in left),
            'Performance payload must contain related manager data')
    require(naive.headers.get('x-data-sql-statements') == str(size+1)
            and fixed.headers.get('x-data-sql-statements') == '1', 'Expected N+1 versus one data SQL statement')
    totals = [int(r.headers.get('x-sql-statements', '0')) for r in (naive, fixed)]
    require(totals[0] > size+1 and totals[1] > 1, 'Total SQL must include authentication/session work')
    return {'rows': size, 'equal_payloads': True, 'data_sql': {'naive': size+1, 'fixed': 1},
            'total_sql': {'naive': totals[0], 'fixed': totals[1]}}


def verify_frontend_build(root):
    """Compare the served build with a fresh temporary build of tagged sources."""
    with tempfile.TemporaryDirectory(prefix='hw4-submission-build-') as temporary:
        expected = Path(temporary)/'dist'
        subprocess.run(['npm', 'run', 'build', '--', '--outDir', str(expected), '--emptyOutDir'],
                       cwd=root/'frontend', check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        def files(directory):
            return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in directory.rglob('*') if p.is_file()}
        wanted, served = files(expected), files(root/'frontend/dist')
        require(bool(wanted) and 'index.html' in wanted and wanted == served,
                'frontend/dist differs from a fresh tagged-source build; build it before verification')
    return {'files': len(wanted)}


def live_checks(root, ordinary_path, performance_path, checks):
    from sqlalchemy import create_engine, text
    ordinary, ordinary_id = load_private_env(ordinary_path)
    performance, performance_id = load_private_env(performance_path)
    # localhost and 127.0.0.1 are the same target for this guard.
    canonical = lambda identity: ('loopback' if identity[0] in ('127.0.0.1', 'localhost') else identity[0], *identity[1:])
    require(canonical(ordinary_id) != canonical(performance_id), 'Ordinary and performance private configurations must identify distinct owned instances')
    checks.append({'name': 'served_build_matches_tagged_sources', 'passed': True, **verify_frontend_build(root)})
    instance_ids = set()
    for label, private, env_path in (('ordinary', ordinary, ordinary_path), ('performance', performance, performance_path)):
        engine = create_engine(private['HW4_DATABASE_URL'], hide_parameters=True, connect_args={'connect_timeout': 10})
        try:
            with engine.connect() as connection:
                require(connection.scalar(text('SELECT DATABASE()')) == 's6102_rel', 'Configured MySQL database differs')
                require('MariaDB' not in connection.scalar(text('SELECT VERSION()')), 'Expected the assignment MySQL runtime')
                identity = connection.scalar(text('SELECT @@server_uuid'))
                require(identity and identity not in instance_ids, 'Ordinary and performance settings resolve to the same MySQL instance')
                instance_ids.add(identity)
                if label == 'performance':
                    require(connection.scalar(text('SELECT COUNT(*) FROM rentals')) == 5000
                            and connection.scalar(text('SELECT COUNT(*) FROM property_managers')) == 200,
                            'Performance instance must already contain the retained 5000/200 dataset; no seeding is performed')
        finally:
            engine.dispose()
        checks.append({'name': label + ':mysql_readonly_preflight', 'passed': True})
        with owned_server(root, private, env_path) as client:
            try:
                denied = client.get('/api/rentals')
                require(denied.status_code == 401, 'Anonymous protected list must return 401')
                checks.append({'name': label + ':anonymous_denied', 'passed': True, 'http_status': 401})
                login = client.post('/api/auth/login', json={'email': private['HW4_SEED_EMAIL'], 'password': private['HW4_SEED_PASSWORD']})
                require(login.status_code == 200 and isinstance(login.json().get('user'), dict), 'Configured account must log in')
                cookie = login.headers.get('set-cookie', '').lower()
                require(all(attribute in cookie for attribute in ('httponly', 'secure', 'samesite=lax', 'path=/')),
                        'Login cookie must have the required security attributes')
                require(client.get('/api/auth/me').status_code == 200, 'Login session must authenticate')
                checks.append({'name': label + ':https_login_session_cookie', 'passed': True})
                if label == 'ordinary':
                    rows = client.get('/api/rentals')
                    require(rows.status_code == 200 and isinstance(rows.json(), list) and bool(rows.json()), 'Ordinary list must return saved data')
                    checks.append({'name': 'ordinary:saved_rentals_returned', 'passed': True, 'rows': len(rows.json())})
                    expected = (root/'frontend/dist/index.html').read_bytes()
                    for route in ('/', '/login', '/create', '/update', '/delete'):
                        response = client.get(route)
                        require(response.status_code == 200 and response.content == expected, 'Required React route must serve the built app')
                    assets = re.findall(r'(?:src|href)="(/assets/[^"?#]+)', expected.decode())
                    require(bool(assets), 'React build must reference assets')
                    for asset in assets:
                        response = client.get(asset)
                        local = (root/'frontend/dist'/asset.lstrip('/')).resolve()
                        require(local.is_relative_to((root/'frontend/dist').resolve()) and response.status_code == 200
                                and response.content == local.read_bytes(), 'React asset must match the verified build')
                    checks.append({'name': 'ordinary:react_routes_and_assets', 'passed': True, 'routes': 5, 'assets': len(assets)})
                else:
                    for size in (10, 50, 200):
                        detail = performance_pair(client.get(f'/api/rentals/naive?page_size={size}'),
                                                  client.get(f'/api/rentals/fixed?page_size={size}'), size)
                        checks.append({'name': f'performance:equal_payload_and_sql_{size}', 'passed': True, **detail})
            finally:
                # Even an assertion after login must attempt normal session revocation.
                logout = client.post('/api/auth/logout')
                require(logout.status_code == 204 and client.get('/api/rentals').status_code == 401,
                        'Session logout cleanup did not complete')
                checks.append({'name': label + ':logout_cleanup', 'passed': True})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true', help='Offline saved-evidence integrity only; never a tagged pass')
    mode.add_argument('--tagged', action='store_true', help='Explicitly run the final live smoke test at hw4')
    parser.add_argument('--ordinary-env', type=Path)
    parser.add_argument('--performance-env', type=Path)
    parser.add_argument('--output', type=Path, help='Preparation output only, under raw/report-finalization')
    args = parser.parse_args(argv)
    if args.tagged and (not args.ordinary_env or not args.performance_env):
        parser.error('--tagged requires both explicitly supplied private environment files')
    if args.tagged and args.output:
        parser.error('--output is only for --prepare; tagged failures never overwrite verification.json')
    root = ROOT.resolve()
    try:
        prepared_output = output_path(root, args.output or PREPARATION/'preparation.json', tagged=False)
    except VerificationError as error:
        parser.error(str(error))
    # Imports of the offline helpers must not create bytecode beside source.
    sys.dont_write_bytecode = True
    started = datetime.now(timezone.utc)
    result = {'homework': 4, 'SID4': 6102, 'PORT_BASE': 8702, 'PREFIX': 's6102', 'DOMAIN_ID': 6,
              'SEED': 6102, 'VERIFY_SEED': 266102, 'commit_hash': git(root, 'rev-parse', 'HEAD'),
              'timestamp_utc': started.isoformat(), 'tag': 'hw4' if args.tagged else None,
              'tagged_verification': False, 'live_smoke': 'not_run', 'checks': [],
              'scope': ('whole-HW4 tagged objective smoke plus selected historical evidence' if args.tagged
                        else 'offline preparation: historical evidence consistency only; no live or tagged verification'),
              'runtime_configuration': {'scope': 'requested tagged smoke' if args.tagged else 'planned only; not executed', 'base_url': 'https://127.0.0.1:8702', 'database': 's6102_rel', 'instances': ['ordinary', 'performance'],
                                        'live_sample_sizes': [10, 50, 200], 'fresh_benchmark_requests': 0, 'fresh_model_calls': 0}}
    before = source_fingerprints(root)
    previous_signal = signal.getsignal(signal.SIGTERM)
    def interrupted(_signum, _frame):
        raise InterruptedError('Verification interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.tagged:
            result['commit_hash'] = tagged_state(root)
            result['checks'].append({'name': 'exact_hw4_tag_and_submission_tree', 'passed': True})
        checks, metadata = offline_checks(root)
        result['checks'].extend(checks)
        result.update(metadata)
        require(bool(checks) and all(c.get('passed') is True for c in checks), 'Offline selected-evidence checks did not all pass')
        if args.tagged:
            result['live_smoke'] = 'attempted'
            live_checks(root, args.ordinary_env, args.performance_env, result['checks'])
            result['live_smoke'] = 'pass'
            require(tagged_state(root) == result['commit_hash'], 'Tagged state changed during verification')
    except (Exception, KeyboardInterrupt) as error:
        detail = str(error) if isinstance(error, VerificationError) else type(error).__name__
        result['checks'].append({'name': 'verification_completed', 'passed': False, 'detail': detail})
    finally:
        signal.signal(signal.SIGTERM, previous_signal)
        result['checks'].append({'name': 'application_sources_unchanged', 'passed': before == source_fingerprints(root)})
        result['source_sha256_before'] = before
        result['source_sha256_after'] = source_fingerprints(root)
    passed = all(c.get('passed') is True for c in result['checks'])
    result['status'] = ('pass' if args.tagged else 'prepared') if passed else 'fail'
    result['tagged_verification'] = bool(args.tagged and passed and result['live_smoke'] == 'pass')
    if result['tagged_verification']:
        destination = output_path(root, Path('verification.json'), tagged=True)
    elif args.tagged:
        destination = output_path(root, PREPARATION/f'tagged-attempt-{started.strftime("%Y%m%dT%H%M%S%fZ")}.json', tagged=False)
    else:
        destination = prepared_output
    result['pending'] = [] if result['tagged_verification'] else ['Final local commit/tag and successful explicit --tagged live execution']
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'tagged_verification': result['tagged_verification'],
                      'passed': sum(c['passed'] for c in result['checks']), 'total': len(result['checks']), 'output': str(destination)}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
