#!/usr/bin/env python3
"""Verify both HW3 parts locally and optionally the assembled report package.

This does not start a browser or repeat the measured retrieval campaign. Run those
checks separately before this evidence verifier. Publishing remains a manual step.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def relative(path, root):
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def execute_check(name, command, root, receipt_dir, output):
    """Require both subprocess success and a newly generated passing payload."""
    started = utc_now()
    log = receipt_dir / f'{name}.txt'
    result = {'name': name, 'command': command, 'started_at': started,
              'output': relative(output, root), 'log': relative(log, root)}
    try:
        process = subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, check=False)
        log.write_text(process.stdout)
        result['exit_code'] = process.returncode
        payload = json.loads(output.read_text())
        result['reported_status'] = payload.get('status')
        result['status'] = 'pass' if process.returncode == 0 and payload.get('status') == 'pass' else 'fail'
        result['output_sha256'] = sha256(output)
    except (OSError, ValueError, AttributeError) as exc:
        result['status'] = 'fail'
        result.setdefault('exit_code', None)
        result['error'] = str(exc)
        if not log.exists():
            log.write_text(str(exc) + '\n')
    result['finished_at'] = utc_now()
    result['log_sha256'] = sha256(log)
    return result


def check_report_manifest(root, check_ancestor):
    """Check PDF/source identity; this is not a PDF rendering or visual QA test."""
    try:
        directory = root / 'reports/hw03'
        pdf = directory / 'report.pdf'
        content = pdf.read_bytes()
        if not content.startswith(b'%PDF-') or b'%%EOF' not in content[-1024:]:
            raise ValueError('PDF header/end marker missing')
        manifest = json.loads((directory / 'report-build.json').read_text())
        if manifest['pdf_sha256'] != sha256(pdf):
            raise ValueError('PDF differs from build manifest')
        if manifest['markdown_sha256'] != sha256(directory / 'report.md'):
            raise ValueError('Generated Markdown differs from build manifest')
        if type(manifest['page_count']) is not int or manifest['page_count'] <= 0:
            raise ValueError('Build manifest page count must be positive')
        sources = manifest['source_sha256']
        if not isinstance(sources, dict) or not sources:
            raise ValueError('Build source hash map is empty')
        for name, expected in sources.items():
            path = root / name
            if Path(name).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError(f'Build source path leaves repository: {name}')
            if sha256(path) != expected:
                raise ValueError(f'Report source changed since build: {name}')
        if not check_ancestor(manifest['tested_code_commit']):
            raise ValueError('Report tested-code commit is not an ancestor of HEAD')
        return True, {'pdf_sha256': manifest['pdf_sha256'], 'markdown_sha256': manifest['markdown_sha256'],
                      'page_count_reported_by_builder': manifest['page_count'],
                      'source_count': len(sources), 'tested_code_commit': manifest['tested_code_commit'],
                      'visual_qa': 'not performed by this verifier'}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return False, str(exc)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--web-python', type=Path, default=ROOT / '.venv-web/bin/python')
    parser.add_argument('--retrieval-python', type=Path, default=ROOT / '.venv-retrieval/bin/python')
    parser.add_argument('--run-dir', type=Path, default=ROOT / 'reports/hw03/raw/part2/baseline-20260920')
    parser.add_argument('--receipt-dir', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/hw03/verification.json')
    parser.add_argument('--smoke', action='store_true', help='Add Part 2 cached-model smoke check; no downloads')
    parser.add_argument('--require-report', action='store_true', help='Require assembled report, build hashes, and shared evidence')
    args = parser.parse_args(argv)
    started = utc_now()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    receipt_dir = (args.receipt_dir or ROOT / 'reports/hw03/raw/integration' / stamp).absolute()
    receipt_dir.mkdir(parents=True, exist_ok=False)
    # Retain the venv executable path: resolving its symlink would bypass the venv.
    web_python = str(args.web_python.absolute())
    retrieval_python = str(args.retrieval_python.absolute())
    commands = [
        ('part1', [web_python, 'scripts/verify_hw03_part1.py']),
        ('part2', [retrieval_python, 'scripts/verify_hw03_part2.py', '--run-dir', str(args.run_dir.absolute()),
                   '--require-report'] + (['--smoke'] if args.smoke else [])),
    ]
    parts = []
    for name, command in commands:
        output = receipt_dir / f'{name}.json'
        parts.append(execute_check(name, command + ['--output', str(output)], ROOT, receipt_dir, output))
    checks = []

    def check(name, passed, details):
        checks.append({'name': name, 'passed': bool(passed), 'details': details})

    def ancestor(commit):
        return subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', commit, 'HEAD'],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0

    provenance = {}
    try:
        provenance['checkout_commit'] = git(ROOT, 'rev-parse', 'HEAD')
        provenance['branch'] = git(ROOT, 'branch', '--show-current')
        provenance['working_tree_status'] = git(ROOT, 'status', '--porcelain')
        tracked_code = set(git(ROOT, 'ls-files', '--', 'code/web_application', 'src/retrieval',
            'code/retrieval_compare.py', 'code/retrieval_summarize.py', 'requirements.txt',
            'requirements-retrieval.txt', 'scripts/verify_hw03*.py', 'scripts/run_hw03_web.py',
            'tests/test_hw03*.py', 'tests/test_api.py', 'tests/browser_hw03_auth.cjs',
            'tests/browser_part2.cjs', 'tests/retrieval', 'package.json').splitlines())
        tracked_code.add('scripts/verify_hw03.py')
        hashes = {}
        for name in sorted(tracked_code):
            current = sha256(ROOT / name)
            saved = subprocess.check_output(['git', '-C', str(ROOT), 'show', f'HEAD:{name}'])
            if hashlib.sha256(saved).hexdigest() != current:
                raise ValueError(f'Uncommitted source changes: {name}')
            hashes[name] = current
        provenance['source_sha256'] = hashes
        check('current_code_is_committed', True, f'{len(hashes)} source/test/dependency files match HEAD')
        run = json.loads((args.run_dir / 'run.json').read_text())
        runtime = {name: digest for name, digest in run['code_hashes'].items()
                   if name.startswith('src/retrieval/') or name in
                   ('code/retrieval_compare.py', 'code/retrieval_summarize.py', 'requirements-retrieval.txt')}
        if not runtime:
            raise ValueError('Baseline runtime hash inventory is empty')
        mismatches = [name for name, digest in runtime.items() if sha256(ROOT / name) != digest]
        check('retrieval_runtime_matches_measured_baseline', not mismatches, mismatches or f'{len(runtime)} files match')
        provenance['retrieval_measured_code_commit'] = run['code_commit']
        provenance['retrieval_input_freeze_commit'] = run['freeze_commit']
        check('retrieval_history_preserved', ancestor(run['freeze_commit']) and ancestor(run['code_commit']),
              'Input freeze and measured-code commits must both be ancestors of HEAD')
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        check('source_provenance', False, str(exc))
    if args.require_report:
        required = ['RUN_LOG.txt', 'AI_USE.md', 'REPRODUCIBLE_RUN_INSTRUCTIONS.md',
                    'SUBMISSION_CHECKLIST.md', 'METRICS.md', 'SOURCES.md', 'CORPUS_MANIFEST.json', 'questions.yaml']
        for name in required:
            path = ROOT / 'reports/hw03' / name
            check(f'shared_evidence:{name}', path.is_file() and path.stat().st_size > 0, name)
        valid, detail = check_report_manifest(ROOT, ancestor)
        check('report_build_identity', valid, detail)
    status = 'pass' if all(part['status'] == 'pass' for part in parts) and all(c['passed'] for c in checks) else 'fail'
    result = {'schema_version': 1, 'assignment': 'HW3', 'status': status,
              'started_at': started, 'finished_at': utc_now(), 'provenance': provenance,
              'parts': parts, 'checks': checks, 'report_package_checked': args.require_report,
              'scope': 'Local integrated evidence verification; fresh browser/full retrieval tests and PDF visual QA are recorded separately.',
              'submission': {'review': 'pending_student_review', 'tags': 'intentionally_pending',
                             'github_publication': 'intentionally_pending', 'collaborator_access': 'not_checked',
                             'course_upload': 'not_performed'}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'HW3 integrated verification: {status}')
    print(f'Result: {args.output}')
    print(f'Receipts: {receipt_dir}')
    for part in parts:
        print(f'{part["name"]}: {part["status"]} (exit {part["exit_code"]})')
    for item in checks:
        if not item['passed']:
            print(f'FAIL {item["name"]}: {item["details"]}')
    print('Tags, publishing, collaborator access and course upload are not verified.')
    return 0 if status == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
