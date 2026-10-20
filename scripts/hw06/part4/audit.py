"""Independent exercise audit: compare final lines with frozen expected outcomes.

Deliberately does not import the service's correction-graph decision function.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


def audit(original: str, final: str, expected: dict) -> dict:
    def records(text):
        result = {}
        for line in text.splitlines():
            if not line.startswith('- ['):
                continue
            head, *tags = line.split(' | ')
            match = re.fullmatch(r'- \[([^]]+)\] ([^:]+): (.+)', head)
            if not match:
                raise ValueError('Malformed evidence line')
            ids, key, value = match.groups()
            metadata = dict(tag.split('=',1) for tag in tags)
            for identifier in ids.split(','):
                if identifier in result:
                    raise ValueError('Source ID appears more than once')
                result[identifier] = {'key':key, 'value':value, 'metadata':metadata, 'line':line}
        return result
    old, new = records(original), records(final)
    coverage = set(old) == set(new)
    unchanged_claims = coverage and all((old[i]['key'],old[i]['value']) ==
                                      (new[i]['key'],new[i]['value']) for i in old)
    pairs = []
    for case in expected['conflicts']:
        errors = []
        for identifier in case['pair']:
            record = new.get(identifier, {})
            meta = record.get('metadata', {})
            expected_status = ('unresolved' if case['winner'] is None else
                               'current' if identifier == case['winner'] else 'superseded')
            if meta.get('status') != expected_status:
                errors.append(f'{identifier}: expected {expected_status}')
            if expected_status == 'superseded' and meta.get('by') != case['winner']:
                errors.append(f'{identifier}: wrong superseding source')
        pairs.append({**case, 'observed_lines':[new.get(i,{}).get('line') for i in case['pair']],
                      'correct':not errors, 'errors':errors})
    duplicates = []
    for case in expected['duplicates']:
        lines = {new.get(i,{}).get('line') for i in case['ids']}
        duplicates.append({**case, 'merged':len(lines) == 1 and None not in lines})
    wrong = sum(not pair['correct'] for pair in pairs)
    counts = {'original_physical_lines':len(original.splitlines()),
              'final_physical_lines':len(final.splitlines()),
              'final_counted_lines':sum(bool(l.strip()) and not l.startswith(('<!--','#'))
                                        for l in final.splitlines())}
    return {'audit_method':'Independent direct inspection against precommitted pair outcomes; no model judge',
            'source_coverage_complete':coverage, 'original_claims_unchanged':unchanged_claims,
            'original_source_ids':len(old),'final_source_ids':len(new), 'counts':counts,
            'conflicts':pairs, 'duplicates':duplicates, 'incorrectly_resolved_contradictions':wrong,
            'incorrect_pairs':[p['pair'] for p in pairs if not p['correct']],
            'original_sha256':hashlib.sha256(original.encode()).hexdigest(),
            'final_sha256':hashlib.sha256(final.encode()).hexdigest(),
            'passed':coverage and unchanged_claims and wrong == 0 and all(d['merged'] for d in duplicates)
                     and counts['original_physical_lines'] == 55
                     and counts['final_physical_lines'] < 40 and counts['final_counted_lines'] < 40}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original',type=Path,required=True)
    parser.add_argument('--final',type=Path,required=True)
    parser.add_argument('--expected',type=Path,required=True)
    args = parser.parse_args()
    result = audit(args.original.read_text(), args.final.read_text(), json.loads(args.expected.read_text()))
    print(json.dumps(result,indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
