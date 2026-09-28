#!/usr/bin/env python3
"""Read application source, verify Parts1–3 artifacts, write partial evidence.

No application source edits, schema changes, seed resets or submission tags.
Missing manual screenshots are failed checks, never inferred from curl results.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '5742b2aadbafee5ba208311723ea470c09811dc5'
FOUNDATION = 'f29e7cc85baf52bea30bd4bb3209d1bd79b22051'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def screenshot_valid(filename):
    """Require a nonempty PNG inside the evidence screenshot directory."""
    if not isinstance(filename, str) or not filename or Path(filename).is_absolute():
        return False
    candidate = (ROOT / filename).resolve()
    if not candidate.is_relative_to((ROOT/'reports/hw04/screenshots').resolve()) or candidate.suffix != '.png':
        return False
    try:
        data = candidate.read_bytes()
        if data[:8] != b'\x89PNG\r\n\x1a\n':
            return False
        offset, width, height, compressed = 8, 0, 0, bytearray()
        while offset + 12 <= len(data):
            length = struct.unpack('>I', data[offset:offset+4])[0]
            kind = data[offset+4:offset+8]
            end = offset + 8 + length
            if end + 4 > len(data):
                return False
            payload = data[offset+8:end]
            if zlib.crc32(kind + payload) & 0xffffffff != struct.unpack('>I',data[end:end+4])[0]:
                return False
            if offset == 8:
                if kind != b'IHDR' or length != 13:
                    return False
                width, height = struct.unpack('>II',payload[:8])
            if kind == b'IDAT':
                compressed.extend(payload)
            if kind == b'IEND':
                return length == 0 and end + 4 == len(data) and width > 0 and height > 0 and bool(zlib.decompress(compressed))
            offset = end + 4
    except (OSError, ValueError, struct.error, zlib.error):
        return False
    return False


def artifact_checks(path, *, real_browser=False):
    """An overall pass cannot conceal a failed/missing individual result."""
    name = str(path)
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return [{'name':name+':readable','passed':False}], None
    if not isinstance(data, dict):
        return [{'name':name+':object_shape','passed':False}], None
    nested = data.get('checks')
    checks = [{'name':name+':overall_pass', 'passed':data.get('status')=='pass'},
              {'name':name+':individual_checks', 'passed':isinstance(nested,list) and bool(nested) and all(
                  isinstance(c,dict) and (c.get('passed') is True or c.get('status')=='pass')
                  and ('passed' not in c or c['passed'] is True)
                  and ('status' not in c or c['status']=='pass'
                       or (type(c['status']) is int and 100 <= c['status'] <= 599))
                  for c in (nested or []))}]
    if real_browser:
        checks += [{'name':name+':real_https_8702', 'passed':data.get('mode')=='REAL'
                    and bool(re.match(r'^https://[^/]+:8702/?$',data.get('base_url','')))}]
        shots = data.get('screenshots')
        for shot in shots if isinstance(shots,list) else []:
            filename = shot.get('file') if isinstance(shot,dict) else None
            checks.append({'name':'browser_screenshot:'+str(filename), 'passed':screenshot_valid(filename)})
        checks.append({'name':'browser_has_screenshots','passed':isinstance(shots,list) and bool(shots)})
        expected = browser_fingerprints()
        checks.append({'name':'browser_matches_current_sources',
                       'passed':bool(expected) and data.get('source_sha256')==expected})
    return checks, data


def fingerprint(paths):
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths if p.is_file() and '__pycache__' not in p.parts}


def browser_fingerprints():
    return fingerprint([*sorted((ROOT/'frontend/src').rglob('*')),
                        *[ROOT/p for p in ('frontend/package.json','frontend/package-lock.json',
                                           'frontend/vite.config.js','tests/browser_hw04_part1.cjs',
                                           'tests/browser_hw04_part1_runtime.py')]])


def source_fingerprints():
    paths = [*sorted((ROOT/'code/web_application').rglob('*.py')),
             *sorted((ROOT/'frontend/src').rglob('*')),
             *sorted((ROOT/'frontend/dist').rglob('*')),
             ROOT/'requirements.txt',ROOT/'scripts/run_hw04_web.py']
    return {**fingerprint(paths), **browser_fingerprints()}


def test_fingerprints():
    return fingerprint([*sorted((ROOT/'code/web_application').rglob('*.py')),
                        *sorted((ROOT/'scripts/hw04').rglob('*.py')),
                        *sorted((ROOT/'tests').glob('test_hw04*.py')),
                        *[ROOT/p for p in ('tests/conftest.py','tests/test_api.py','tests/test_hw03_auth.py',
                                           'tests/test_hw03_integration.py','tests/browser_hw04_part1.cjs',
                                           'tests/browser_hw04_part1_runtime.py','tests/check_hw04_part1_interruption.py',
                                           'scripts/verify_hw04_parts123.py')]])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-evidence',type=Path,default=ROOT/'reports/hw04/raw/part2/api-acceptance.json')
    parser.add_argument('--browser-evidence',type=Path,default=ROOT/'reports/hw04/raw/part1/real-browser.json')
    parser.add_argument('--benchmark-run',type=Path)
    parser.add_argument('--index-evidence',type=Path)
    parser.add_argument('--pytest-evidence',type=Path,default=ROOT/'reports/hw04/raw/part2/pytest-backend-reviewed.txt')
    parser.add_argument('--part1-commit')
    parser.add_argument('--part3-commit')
    parser.add_argument('--integration-evidence',type=Path,default=ROOT/'reports/hw04/raw/part2/integration-smoke.json')
    parser.add_argument('--output',type=Path,default=ROOT/'reports/hw04/verification.parts123.json')
    args = parser.parse_args(argv)
    # A report-output override must never turn this tool into a source writer.
    output = args.output.resolve()
    if not output.is_relative_to((ROOT/'reports/hw04').resolve()) or output.suffix != '.json' or output.name=='verification.json':
        parser.error('Output must be a partial JSON artifact under reports/hw04/, never verification.json')
    before = source_fingerprints()
    checks = []
    def check(name,passed,**details):
        checks.append({'name':name,'passed':bool(passed),**details})
    revision = git('rev-parse','HEAD')
    check('hw3_baseline_unchanged',git('rev-parse','hw3^{commit}')==BASELINE)
    for label,commit in [('foundation',FOUNDATION),('part1',args.part1_commit),('part3',args.part3_commit)]:
        valid = bool(commit and re.fullmatch(r'[0-9a-f]{40}',commit))
        merged = valid and subprocess.run(['git','merge-base','--is-ancestor',commit,'HEAD'],cwd=ROOT,
                                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
        check(label+'_commit_integrated',merged,commit=commit)
    untouched = git('diff','--name-only',BASELINE,'--','src','code/retrieval_compare.py','code/retrieval_summarize.py',
                    'code/agents_graph.py','code/agents_demo.py','reports/hw01','reports/hw02','reports/hw03')
    check('historical_reports_and_unrelated_code_preserved',not untouched,changed_paths=untouched.splitlines())
    for path, browser in [(args.api_evidence,False),(args.browser_evidence,True),(args.integration_evidence,False)]:
        found,data = artifact_checks(path,real_browser=browser)
        checks.extend(found)
        if path==args.integration_evidence:
            check('integration_matches_current_sources',bool(data) and data.get('source_sha256')==before)
    try:
        test_text=args.pytest_evidence.read_text()
        test_match=re.search(r'(\d+) passed',test_text)
        test_metadata=json.loads(args.pytest_evidence.with_suffix('.metadata.json').read_text())
        provenance=(test_metadata.get('real_mysql') is True and test_metadata.get('exit_code')==0
                    and test_metadata.get('database')=='s6102_rel'
                    and test_metadata.get('output_sha256')==hashlib.sha256(args.pytest_evidence.read_bytes()).hexdigest()
                    and test_metadata.get('tested_source_sha256')==test_fingerprints())
        check('real_mysql_pytest_passed',provenance and bool(test_match) and not re.search(r'\d+ (failed|error|skipped)',test_text),
              test_count=int(test_match[1]) if test_match else 0,artifact=str(args.pytest_evidence))
    except (OSError,ValueError):
        check('real_mysql_pytest_passed',False,artifact=str(args.pytest_evidence))
    measured_revision=None
    try:
        if args.benchmark_run is None:
            raise ValueError('No selected run supplied')
        manifest=json.loads((args.benchmark_run/'manifest.json').read_text())
        script=ROOT/'scripts/hw04/part3/summarize.py'
        spec=importlib.util.spec_from_file_location('hw4_metric_summary',script)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        summary=module.summarize_rows(module.read_rows(args.benchmark_run/'requests.jsonl'))
        measured_revision=summary['code_revision']
        check('benchmark_180_validated_requests',summary['request_count']==180 and manifest['status']=='success',
              measured_revision=measured_revision,run_id=summary['run_id'])
        check('benchmark_clean_measured_revision',summary['dirty'] is False)
        # These executed source files are what could invalidate old measurements.
        runtime_paths=[p for p in git('ls-files','code/web_application','requirements.txt','scripts/run_hw04_web.py').splitlines()
                       if p.endswith(('.py','.sql')) or p=='requirements.txt']
        changed=git('diff','--name-only',measured_revision,'--',*runtime_paths)
        # Only ordinary CRUD search changed after the measured run. Neither
        # measured endpoint imports or calls that router's handlers. Record this
        # explicit exclusion rather than pretending all backend source matches.
        ordinary_only={'code/web_application/routers/rentals.py'}
        changed_paths=changed.splitlines()
        relevant=[p for p in changed_paths if p not in ordinary_only]
        check('integrated_measured_execution_matches',not relevant,
              changed_executed_paths=relevant,
              changed_unmeasured_crud_paths=[p for p in changed_paths if p in ordinary_only])
    except (OSError,ValueError,KeyError,AttributeError,subprocess.CalledProcessError) as exc:
        check('benchmark_180_validated_requests',False,error_type=type(exc).__name__)
    try:
        if args.index_evidence is None:
            raise ValueError('No index evidence supplied')
        directory=args.index_evidence.parent
        comparison=json.loads(args.index_evidence.read_text())
        before_index=json.loads((directory/'before.json').read_text())
        after_index=json.loads((directory/'after.json').read_text())
        index_status=json.loads((directory/'status.json').read_text())
        sys.path.insert(0,str(ROOT/'scripts/hw04/part3'))
        import index_experiment
        index_experiment.assert_unindexed(before_index['indexes'],before_index['schema_migrations'])
        recomputed=index_experiment.compare_snapshots(before_index,after_index)
        check('index_before_after_verified',index_status['status']=='complete'
              and comparison==recomputed and len(before_index['results'])==1
              and bool(before_index['explain_traditional']) and bool(after_index['explain_traditional']),
              artifact=str(args.index_evidence))
    except (OSError,ValueError,KeyError,ImportError):
        check('index_before_after_verified',False)
    capture_manifest=ROOT/'reports/hw04/manual-captures.json'
    try:
        captures=json.loads(capture_manifest.read_text())
    except (OSError,ValueError):
        captures=[]
    required=['part2/postman-create','part2/postman-list','part2/postman-id','part2/postman-update','part2/postman-delete',
              'part2/database','part2/project-structure',
              *[f'part3/postman-{version}-{size}' for version in ('naive','fixed') for size in (10,50,200)]]
    by_name={entry['name']:entry for entry in captures if isinstance(entry,dict) and isinstance(entry.get('name'),str)} if isinstance(captures,list) else {}
    for name in required:
        entry=by_name.get(name,{})
        filename=entry.get('file')
        check('manual_capture:'+name,entry.get('captured') is True and screenshot_valid(filename),
              category='manual_evidence',file=entry.get('file'),reason=entry.get('reason','Capture not supplied'))
    check('verifier_did_not_modify_application_source',before==source_fingerprints())
    automatic=[c for c in checks if c.get('category')!='manual_evidence']
    result={'scope':'HW4 Parts1–3 only; not final whole-homework verification',
            'timestamp_utc':datetime.now(timezone.utc).isoformat(),'revision':revision,
            'seed':6102,'verify_seed':266102,'database':'s6102_rel','port':8702,
            'measured_revision':measured_revision,'checks':checks,
            'automated_status':'pass' if all(c['passed'] for c in automatic) else 'fail',
            'status':'pass' if all(c['passed'] for c in checks) else 'incomplete',
            'outside_scope':['Part4','final whole-homework PDF','collaborator checks','hw4 tag','tagged verification.json']}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'automated_status':result['automated_status'],
                      'passed':sum(c['passed'] for c in checks),'total':len(checks),'output':str(output)}))
    return 0 if result['status']=='pass' else 1


if __name__=='__main__':
    raise SystemExit(main())
