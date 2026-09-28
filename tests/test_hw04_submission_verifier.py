"""Offline submission guards: no listener, database, or model is needed."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/verify_hw04_submission.py'
spec = importlib.util.spec_from_file_location('hw4_submission', SCRIPT)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repository(tmp_path):
    git(tmp_path, 'init')
    git(tmp_path, 'config', 'user.name', 'Verifier test')
    git(tmp_path, 'config', 'user.email', 'verifier@example.invalid')
    source = tmp_path / 'code/app.py'
    source.parent.mkdir()
    source.write_text('value = 1\n')
    git(tmp_path, 'add', 'code/app.py')
    git(tmp_path, 'commit', '-m', 'test fixture')
    return tmp_path


def test_missing_tag_fails_closed(repository):
    with pytest.raises(verifier.VerificationError, match='hw4 tag'):
        verifier.tagged_state(repository)


def test_tag_must_be_head(repository):
    git(repository, 'tag', 'hw4')
    (repository/'code/app.py').write_text('value = 2\n')
    git(repository, 'commit', '-am', 'second')
    with pytest.raises(verifier.VerificationError, match='HEAD'):
        verifier.tagged_state(repository)


@pytest.mark.parametrize('change', ['modified', 'staged', 'untracked', 'ignored_source'])
def test_tag_rejects_changed_or_uncommitted_submission(repository, change):
    if change == 'ignored_source':
        (repository/'.gitignore').write_text('code/extra.py\n')
        git(repository, 'add', '.gitignore')
        git(repository, 'commit', '-m', 'ignore fixture')
    git(repository, 'tag', 'hw4')
    if change in ('modified', 'staged'):
        (repository/'code/app.py').write_text('value = 2\n')
        if change == 'staged':
            git(repository, 'add', 'code/app.py')
    else:
        (repository/'code/extra.py').write_text('value = 2\n')
    with pytest.raises(verifier.VerificationError):
        verifier.tagged_state(repository)


def test_receipt_outputs_are_only_untracked_exceptions(repository):
    git(repository, 'tag', 'hw4')
    (repository/'verification.json').write_text('{}')
    directory = repository/'reports/hw04/raw/report-finalization'
    directory.mkdir(parents=True)
    (directory/'previous.json').write_text('{}')
    assert verifier.tagged_state(repository) == git(repository, 'rev-parse', 'HEAD')
    (repository/'reports/hw04/uncommitted-report.md').write_text('draft')
    with pytest.raises(verifier.VerificationError):
        verifier.tagged_state(repository)


@pytest.mark.parametrize('output', ['verification.json', 'code/app.py', 'reports/hw04/report.json'])
def test_preparation_cannot_write_final_receipt_or_source(repository, output):
    with pytest.raises(verifier.VerificationError):
        verifier.output_path(repository, Path(output), tagged=False)


def test_output_path_rejects_symlink_escape(repository, tmp_path_factory):
    target = tmp_path_factory.mktemp('outside')
    output = repository/'reports/hw04/raw/report-finalization'
    output.parent.mkdir(parents=True)
    output.symlink_to(target, target_is_directory=True)
    with pytest.raises(verifier.VerificationError):
        verifier.output_path(repository, output/'prep.json', tagged=False)


def test_source_fingerprints_detect_edits_without_counting_receipts(repository):
    before = verifier.source_fingerprints(repository)
    (repository/'verification.json').write_text('{}')
    assert verifier.source_fingerprints(repository) == before
    (repository/'code/app.py').write_text('value = 9\n')
    assert verifier.source_fingerprints(repository) != before


def response(rows, count):
    from types import SimpleNamespace
    return SimpleNamespace(status_code=200, json=lambda: rows,
                           headers={'x-data-sql-statements':str(count), 'x-sql-statements':str(count+2)})


def test_performance_checks_payload_equality_and_actual_query_counts():
    rows = [{'id':i+1, 'manager':{'id':1,'name':'manager'}} for i in range(10)]
    assert verifier.performance_pair(response(rows,11),response(rows,1),10)['rows'] == 10
    with pytest.raises(verifier.VerificationError):
        verifier.performance_pair(response(rows,1),response(rows,1),10)
    with pytest.raises(verifier.VerificationError):
        verifier.performance_pair(response(rows,11),response(rows[:-1],1),10)
    changed = [dict(row) for row in rows]
    changed[0]['manager'] = None
    with pytest.raises(verifier.VerificationError):
        verifier.performance_pair(response(rows,11),response(changed,1),10)


def test_preparation_does_not_read_private_config_or_start_server(monkeypatch, repository):
    monkeypatch.setattr(verifier,'ROOT',repository)
    def forbidden(*args, **kwargs):
        pytest.fail('Preparation crossed into the live/private boundary')
    monkeypatch.setattr(verifier,'load_private_env',forbidden)
    monkeypatch.setattr(verifier,'live_checks',forbidden)
    monkeypatch.setattr(verifier,'offline_checks',lambda root: ([{'name':'saved evidence','passed':True}], {}))
    assert verifier.main(['--prepare']) == 0
    receipt = json.loads((repository/'reports/hw04/raw/report-finalization/preparation.json').read_text())
    assert receipt['status'] == 'prepared'
    assert receipt['tagged_verification'] is False
    assert receipt['live_smoke'] == 'not_run'
    assert not (repository/'verification.json').exists()


def test_missing_tag_prevents_private_config_and_final_receipt(monkeypatch, repository):
    monkeypatch.setattr(verifier,'ROOT',repository)
    monkeypatch.setattr(verifier,'offline_checks',lambda root: ([{'name':'saved evidence','passed':True}], {}))
    def forbidden(*args, **kwargs):
        pytest.fail('Missing tag should stop before reading private configuration')
    monkeypatch.setattr(verifier,'load_private_env',forbidden)
    assert verifier.main(['--tagged','--ordinary-env','/not/read','--performance-env','/not/read-either']) == 1
    assert not (repository/'verification.json').exists()
    failures = list((repository/'reports/hw04/raw/report-finalization').glob('tagged-attempt-*.json'))
    assert len(failures) == 1
    assert json.loads(failures[0].read_text())['status'] == 'fail'


def test_failure_inside_owned_server_closes_only_its_resources(monkeypatch, repository):
    import httpx
    from types import SimpleNamespace
    events = []
    tls = repository/'tmp/https'
    tls.mkdir(parents=True)
    (tls/'cert.pem').write_text('fake certificate; client is stubbed')
    (tls/'key.pem').write_text('fake key')
    process = SimpleNamespace(poll=lambda: None)
    client = SimpleNamespace(get=lambda *args, **kwargs: SimpleNamespace(status_code=200),
                             close=lambda: events.append('client closed'))
    monkeypatch.setattr(httpx,'Client',lambda **kwargs: client)
    monkeypatch.setattr(verifier,'assert_port_free',lambda: None)
    monkeypatch.setattr(verifier.subprocess,'Popen',lambda *args, **kwargs: process)
    monkeypatch.setattr(verifier,'stop_owned',lambda owned: events.append('owned stopped') if owned is process else pytest.fail('wrong process'))
    with pytest.raises(RuntimeError, match='smoke failed'):
        with verifier.owned_server(repository, {}, Path('/unused/private.env')):
            raise RuntimeError('smoke failed')
    assert events == ['client closed', 'owned stopped']


def test_failed_launch_closes_client_without_stopping_other_process(monkeypatch, repository):
    import httpx
    from types import SimpleNamespace
    events = []
    tls = repository/'tmp/https'
    tls.mkdir(parents=True)
    (tls/'cert.pem').write_text('fake certificate')
    (tls/'key.pem').write_text('fake key')
    monkeypatch.setattr(httpx,'Client',lambda **kwargs: SimpleNamespace(close=lambda: events.append('closed')))
    monkeypatch.setattr(verifier,'assert_port_free',lambda: None)
    def fail_launch(*args, **kwargs):
        raise OSError('launch failed')
    monkeypatch.setattr(verifier.subprocess,'Popen',fail_launch)
    monkeypatch.setattr(verifier,'stop_owned',lambda *args: pytest.fail('No process was created'))
    with pytest.raises(OSError):
        with verifier.owned_server(repository, {}, Path('/unused/private.env')):
            pytest.fail('Failed launch cannot yield a server')
    assert events == ['closed']


@pytest.mark.parametrize('changed', ['config', 'run_id', 'code_revision', 'dirty'])
def test_benchmark_metadata_must_match_the_measured_rows(changed):
    import hashlib
    config = {'worker_count': 1, 'seed': 6102}
    digest = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    values = {'request_count': 180, 'run_id':'selected', 'code_revision':'a'*40, 'config_sha256':digest, 'dirty':False}
    manifest = dict(values, status='success', measured_requests=180, config=dict(config))
    verifier.validate_benchmark_configuration(values, manifest, config)
    if changed == 'config':
        config = dict(config, worker_count=2)
    elif changed == 'dirty':
        manifest['dirty'] = True
    else:
        manifest[changed] = 'different'
    with pytest.raises(verifier.VerificationError):
        verifier.validate_benchmark_configuration(values, manifest, config)
