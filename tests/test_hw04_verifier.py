"""Negative evidence checks must not be hidden by an overall success label."""
import importlib.util
import json
from pathlib import Path

import pytest

path=Path(__file__).resolve().parents[1]/'scripts/verify_hw04_parts123.py'
spec=importlib.util.spec_from_file_location('hw4_partial_verifier',path)
verifier=importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


@pytest.mark.parametrize('nested',[{'passed':False,'status':'fail'}, {'passed':True,'status':'fail'}, {'passed':False,'status':'pass'}])
def test_overall_pass_does_not_mask_failed_nested_check(tmp_path,nested):
    evidence=tmp_path/'bad.json'
    evidence.write_text(json.dumps({'status':'pass','checks':[{'name':'replay',**nested}]}))
    checks,_=verifier.artifact_checks(evidence)
    assert not next(c for c in checks if c['name'].endswith(':individual_checks'))['passed']


def test_missing_evidence_cannot_pass(tmp_path):
    checks,data=verifier.artifact_checks(tmp_path/'missing.json')
    assert data is None and not checks[0]['passed']


@pytest.mark.parametrize('http_status',[200,201,204,401])
def test_numeric_http_status_is_metadata_for_explicit_pass(tmp_path,http_status):
    evidence=tmp_path/'http.json'
    evidence.write_text(json.dumps({'status':'pass','checks':[{'passed':True,'status':http_status}]}))
    checks,_=verifier.artifact_checks(evidence)
    assert all(c['passed'] for c in checks)


def test_mock_browser_or_absent_screenshot_cannot_pass(tmp_path):
    evidence=tmp_path/'mock.json'
    evidence.write_text(json.dumps({'status':'pass','mode':'MOCK','base_url':'http://localhost:5173',
                                    'checks':[{'name':'mock','status':'pass'}],
                                    'screenshots':[{'file':'reports/hw04/screenshots/part1/absent.png'}]}))
    checks,_=verifier.artifact_checks(evidence,real_browser=True)
    assert not next(c for c in checks if c['name'].endswith(':real_https_8702'))['passed']
    assert not next(c for c in checks if c['name'].startswith('browser_screenshot:'))['passed']


def test_verifier_refuses_to_overwrite_source(tmp_path):
    with pytest.raises(SystemExit) as error:
        verifier.main(['--output',str(path)])
    assert error.value.code == 2


def test_pending_null_capture_writes_incomplete_artifact(monkeypatch,tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(verifier,'ROOT',tmp_path)
    monkeypatch.setattr(verifier,'git',lambda *args: verifier.BASELINE if args[0]=='rev-parse' else '')
    monkeypatch.setattr(verifier.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=0))
    output=tmp_path/'reports/hw04/verification.parts123.json'
    output.parent.mkdir(parents=True)
    (output.parent/'manual-captures.json').write_text(json.dumps([
        {'name':'part2/database','captured':False,'file':None,'reason':'Pending UI capture'}]))
    assert verifier.main(['--output',str(output)])==1
    data=json.loads(output.read_text())
    assert data['status']=='incomplete'
    assert next(c for c in data['checks'] if c['name']=='manual_capture:part2/database')['passed'] is False


def test_changed_frontend_source_rejects_stale_browser_pass(monkeypatch,tmp_path):
    monkeypatch.setattr(verifier,'ROOT',tmp_path)
    source=tmp_path/'frontend/src/App.jsx'
    source.parent.mkdir(parents=True)
    source.write_text('old app')
    previous=verifier.browser_fingerprints()
    source.write_text('changed app')
    evidence=tmp_path/'real.json'
    evidence.write_text(json.dumps({'status':'pass','mode':'REAL','base_url':'https://localhost:8702',
                                    'checks':[{'name':'flow','status':'pass'}],
                                    'source_sha256':previous,'screenshots':[]}))
    checks,_=verifier.artifact_checks(evidence,real_browser=True)
    assert not next(c for c in checks if c['name']=='browser_matches_current_sources')['passed']


def test_invalid_screenshots_fail_without_crashing(monkeypatch,tmp_path):
    monkeypatch.setattr(verifier,'ROOT',tmp_path)
    directory=tmp_path/'reports/hw04/screenshots'
    directory.mkdir(parents=True)
    (directory/'empty.png').write_bytes(b'')
    (tmp_path/'outside.png').write_bytes(b'not a PNG')
    (directory/'escaped.png').symlink_to(tmp_path/'outside.png')
    filenames=[None, '', str(directory/'empty.png'), 'reports/hw04/screenshots/empty.png',
               'reports/hw04/screenshots/escaped.png', 'reports/hw04/screenshots/../../../outside.png']
    evidence=tmp_path/'real.json'
    evidence.write_text(json.dumps({'status':'pass','mode':'REAL','base_url':'https://localhost:8702',
                                    'checks':[{'passed':True}], 'screenshots':[{'file':f} for f in filenames]}))
    checks,_=verifier.artifact_checks(evidence,real_browser=True)
    screenshot_checks=[c for c in checks if c['name'].startswith('browser_screenshot:')]
    assert len(screenshot_checks)==len(filenames)
    assert not any(c['passed'] for c in screenshot_checks)
