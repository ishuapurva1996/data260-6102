"""Corpus integrity, independent gold evidence, and Git input-freeze guard."""
from pathlib import Path
import hashlib
import json
import subprocess
import yaml


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f'Git check failed: {args}: {result.stderr.strip()}')
    return result.stdout.strip()


def safe_path(root, relative):
    p = (Path(root) / relative).resolve()
    if not p.is_relative_to(Path(root).resolve()):
        raise ValueError(f'Corpus path leaves repository: {relative}')
    return p


def validate_corpus(root, manifest, minimum_bytes=204800):
    ids, hashes = set(), set()
    total = 0
    for source in manifest['sources']:
        if source['source_id'] in ids:
            raise ValueError('Duplicate source ID')
        ids.add(source['source_id'])
        p = safe_path(root, source['path'])
        data = p.read_bytes()
        data.decode('utf-8')
        if len(data) != source['bytes'] or sha256(p) != source['sha256']:
            raise ValueError(f'Corpus size/hash mismatch: {p}')
        if source['sha256'] in hashes:
            raise ValueError('Duplicate source text')
        hashes.add(source['sha256'])
        total += len(data)
        if source.get('original_path'):
            if sha256(safe_path(root,source['original_path'])) != source['original_sha256']:
                raise ValueError('Original source hash mismatch')
    if total < minimum_bytes:
        raise ValueError(f'Corpus below minimum bytes: {total} < {minimum_bytes}')
    if 'total_text_bytes' in manifest and total != manifest['total_text_bytes']:
        raise ValueError('Manifest total byte count mismatch')
    return {'total_text_bytes': total, 'sources': len(ids)}


def validate_questions(root, manifest, data, baseline=True):
    questions = data['questions']
    if baseline and len(questions) != 5:
        raise ValueError('Exactly five baseline questions required')
    sources = {s['source_id']: s for s in manifest['sources']}
    texts = {sid: ' '.join(safe_path(root,s['path']).read_text().split()) for sid,s in sources.items()}
    seen = set()
    for q in questions:
        if q['id'] in seen:
            raise ValueError('Duplicate question ID')
        seen.add(q['id'])
        if not q['question'] or not q['expected_answer'] or not q['expected_source_ids']:
            raise ValueError('Question missing query or gold answer/source')
        if len(set(q['expected_source_ids'])) != len(q['expected_source_ids']):
            raise ValueError('Duplicate expected source')
        expected_files = [sources[s]['path'] for s in q['expected_source_ids']]
        if sorted(expected_files) != sorted(q['expected_source_files']):
            raise ValueError('Expected source file mismatch')
        if not q.get('evidence'):
            raise ValueError('Question has no supporting evidence')
        for ev in q['evidence']:
            if ev['source_id'] not in q['expected_source_ids'] or not ev.get('location'):
                raise ValueError('Evidence source/location mismatch')
            quote = ' '.join(ev['quote'].split())
            if not quote or quote not in texts[ev['source_id']]:
                raise ValueError(f'Gold quote absent from source: {q["id"]}')
        if q.get('single_source') and (len(q['expected_source_ids']) != 1 or not q.get('single_source_verification')):
            raise ValueError('Single-source claim needs one source and independent audit')
        if q.get('designation') != ('baseline' if baseline else 'diagnostic'):
            raise ValueError('Question designation mismatch')
    if baseline and sum(q.get('single_source',False) for q in questions) < 2:
        raise ValueError('At least two audited single-source questions required')
    return questions


def input_paths(root, manifest, questions_path='reports/hw03/questions.yaml'):
    paths = ['reports/hw03/CORPUS_MANIFEST.json', 'reports/hw03/SOURCES.md',
             'reports/hw03/experiment_config.yaml', questions_path]
    for s in manifest['sources']:
        paths.append(s['path'])
        if s.get('original_path'):
            paths.append(s['original_path'])
    return sorted(set(paths))


def require_frozen_inputs(root, freeze_commit, paths):
    git(root, 'merge-base', '--is-ancestor', freeze_commit, 'HEAD')
    hashes = {}
    for name in paths:
        p = safe_path(root,name)
        git(root, 'ls-files', '--error-unmatch', name)
        if git(root, 'status', '--porcelain', '--', name):
            raise ValueError(f'Frozen input changed or uncommitted: {name}')
        committed = subprocess.run(['git','-C',str(root),'show',f'{freeze_commit}:{name}'],
                                   capture_output=True)
        if committed.returncode or committed.stdout != p.read_bytes():
            raise ValueError(f'Frozen input changed since freeze commit: {name}')
        hashes[name] = sha256(p)
    return hashes


def load_inputs(root, questions_path='reports/hw03/questions.yaml', baseline=True):
    root = Path(root)
    manifest = json.loads((root/'reports/hw03/CORPUS_MANIFEST.json').read_text())
    validate_corpus(root, manifest)
    questions = validate_questions(root,manifest,yaml.safe_load((root/questions_path).read_text()),baseline)
    return manifest,questions


def load_documents(root, manifest):
    from llama_index.core import Document
    return [Document(text=safe_path(root,s['path']).read_text(), id_=s['source_id'],
                     metadata={'source_id': s['source_id']},
                     excluded_embed_metadata_keys=['source_id'],excluded_llm_metadata_keys=['source_id'])
            for s in sorted(manifest['sources'],key=lambda x:x['path'])]
