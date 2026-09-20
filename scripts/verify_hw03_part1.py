#!/usr/bin/env python3
"""Run auth/API checks and validate the recorded HTTPS evidence; fail closed."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {'SID4': '6102', 'PORT_BASE': 8702, 'PREFIX': 's6102', 'SEED': 6102,
          'VERIFY_SEED': 266102, 'DOMAIN_ID': 6, 'domain': 'Rental Housing Listings',
          'idle_timeout_seconds': 300, 'cookie_max_age_seconds': 3600}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def check(name, passed, details=''):
    return {'name': name, 'passed': bool(passed), 'details': details}


def evidence_checks(root: Path, evidence: dict) -> list[dict]:
    """Validate facts, source correspondence and files, not only an overall flag."""
    checks = [check('browser_run_passed', evidence.get('status') == 'pass')]
    items = evidence.get('checks', [])
    checks.append(check('browser_individual_checks_passed', bool(items) and all(
        item.get('status') == 'pass' for item in items), f'{len(items)} recorded browser checks'))
    names = ' '.join(item.get('name', '').lower() for item in items)
    for topic in ['logout', 'idle', 'cookie', 'desktop', 'mobile']:
        checks.append(check(f'browser_covers_{topic}', topic in names))
    replay_checks = [item for item in items if isinstance(item.get('details'), dict)
                     and item['details'].get('fresh_browser_context')
                     and item['details'].get('copied_cookie_actually_sent')]
    replay_names = ' '.join(item.get('name', '').lower() for item in replay_checks)
    checks.append(check('browser_covers_replay', len(replay_checks) >= 3
                        and 'logout' in replay_names and 'idle' in replay_names
                        and all(item['details'].get('dashboard_response', {}).get('status') == 303
                                and any(header.get('name', '').lower() == 'location'
                                        and header.get('value') == '/login'
                                        for header in item['details']['dashboard_response'].get('headers', []))
                                for item in replay_checks)))
    source_hashes = evidence.get('source_sha256', {})
    required_sources = ['code/web_application/main.py', 'code/web_application/routers/auth.py',
                        'code/web_application/session_store.py', 'tests/browser_hw03_auth.cjs',
                        'scripts/verify_hw03_part1.py', 'tests/test_hw03_auth.py']
    checks.append(check('source_manifest_complete', all(p in source_hashes for p in required_sources)))
    for relative, expected in source_hashes.items():
        path = root / relative
        valid = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected
        checks.append(check(f'source_matches:{relative}', valid))
    screenshots = evidence.get('screenshots', [])
    screenshot_names = ' '.join(item.get('file', '') for item in screenshots)
    for name in ['home', 'login', 'dashboard', 'invalid-login', 'post-logout',
                 'idle-replay-denied', 'cookie-header', 'templates-directory']:
        checks.append(check(f'screenshot_recorded:{name}', name in screenshot_names))
    for item in screenshots:
        path = root / item.get('file', '')
        valid = path.is_file() and path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        checks.append(check(f'screenshot_exists:{item.get("file")}', valid))
        sizes = item.get('dimensions')
        if sizes:
            checks.append(check(f'no_overflow:{item["file"]}',
                                sizes['document_width'] <= sizes['viewport_width']
                                and sizes['body_width'] <= sizes['viewport_width']))
    header_path = root / 'reports/hw03/raw/part1/desktop-login-response-headers.txt'
    header = header_path.read_text().lower() if header_path.is_file() else ''
    checks.append(check('https_cookie_flags', all(flag in header for flag in
                                               ['httponly', 'secure', 'samesite=lax'])))
    checks.append(check('live_cookie_redacted', 'redacted' in header))
    commit = evidence.get('tested_head', '')
    result = subprocess.run(['git', 'cat-file', '-t', commit], cwd=root, text=True,
                            capture_output=True) if commit else None
    checks.append(check('tested_code_commit_exists', result is not None
                        and result.returncode == 0 and result.stdout.strip() == 'commit', commit))
    # Match each captured source to that commit, even after later evidence-only commits.
    for relative, expected in source_hashes.items():
        result = subprocess.run(['git', 'show', f'{commit}:{relative}'], cwd=root, capture_output=True)
        checks.append(check(f'captured_commit_matches:{relative}', result.returncode == 0
                            and hashlib.sha256(result.stdout).hexdigest() == expected))
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/hw03/part1/verification.json')
    args = parser.parse_args(argv)
    started = utc_now()
    raw = ROOT / 'reports/hw03/raw/part1'
    raw.mkdir(parents=True, exist_ok=True)
    xml_path = ROOT / 'tmp/hw03-part1-pytest.xml'
    xml_path.parent.mkdir(exist_ok=True)
    command = [sys.executable, '-m', 'pytest', 'tests/test_api.py', 'tests/test_hw03_auth.py',
               '-q', f'--junitxml={xml_path}']
    result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (raw / 'self-check-pytest.txt').write_text(result.stdout)
    checks = [check('pytest_exit_status', result.returncode == 0, f'exit={result.returncode}')]
    if xml_path.is_file():
        cases = ET.parse(xml_path).getroot().findall('.//testcase')
        checks.append(check('pytest_collected_tests', bool(cases), f'{len(cases)} tests'))
        for case in cases:
            checks.append(check(f'pytest:{case.get("name")}', not any(
                case.find(tag) is not None for tag in ('failure', 'error', 'skipped'))))
    evidence_path = raw / 'browser-evidence.json'
    try:
        evidence = json.loads(evidence_path.read_text())
        checks.extend(evidence_checks(ROOT, evidence))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        evidence = {}
        checks.append(check('browser_evidence_readable', False, str(exc)))
    for name in ['REPORT_SECTION.md', 'AI_USE.md', 'REPRODUCIBLE_RUN_INSTRUCTIONS.md',
                 'INTEGRATION_NOTES.md', 'RUN_LOG.txt']:
        path = ROOT / 'reports/hw03/part1' / name
        checks.append(check(f'report_material:{name}', path.is_file() and path.stat().st_size > 0))
    report_path = ROOT / 'reports/hw03/part1/REPORT_SECTION.md'
    source = (ROOT / 'code/web_application/routers/auth.py').read_text().strip()
    report = report_path.read_text() if report_path.exists() else ''
    checks.append(check('report_includes_current_auth_source_at_bottom', report.rstrip().endswith(source+'\n```')))
    status = 'pass' if checks and all(item['passed'] for item in checks) else 'fail'
    payload = {'schema_version': 1, 'part': 1, 'status': status, 'started_at': started,
               'finished_at': utc_now(), 'configuration': CONFIG,
               'tested_code_commit': evidence.get('tested_head'),
               'verification_checkout_commit': subprocess.check_output(
                   ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'pytest_command': command, 'checks': checks,
               'browser_evidence': str(evidence_path.relative_to(ROOT)),
               'scope': 'HW3 Part 1 only; Part 2 and combined submission are not verified here.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2)+'\n')
    print(f'HW3 Part 1: {status}; {sum(item["passed"] for item in checks)}/{len(checks)} checks passed')
    for item in checks:
        if not item['passed']:
            print(f'FAIL {item["name"]}: {item["details"]}')
    return 0 if status == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
