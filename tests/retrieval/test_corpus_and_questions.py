import hashlib
import json
import subprocess
from pathlib import Path
import pytest
import yaml
from src.retrieval.corpus import validate_corpus, validate_questions, require_frozen_inputs


def fixture(tmp_path):
    p = tmp_path/'reports/hw03/corpus/sample.txt'
    p.parent.mkdir(parents=True)
    p.write_text('A housing fact: the limit is 12 months.\n')
    manifest={'sources':[{'source_id':'sample','path':str(p.relative_to(tmp_path)),
        'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}]}
    return p,manifest


def test_hash_size_duplicate_guard(tmp_path):
    p,m=fixture(tmp_path)
    assert validate_corpus(tmp_path,m,minimum_bytes=1)
    with pytest.raises(ValueError, match='Duplicate'):
        validate_corpus(tmp_path,{'sources':m['sources']*2},minimum_bytes=1)
    p.write_text('changed')
    with pytest.raises(ValueError):
        validate_corpus(tmp_path,m,minimum_bytes=1)


def test_questions_require_exact_evidence(tmp_path):
    p,m=fixture(tmp_path)
    q={'questions':[{'id':f'Q{i}','designation':'baseline','question':'What is limit?',
        'expected_answer':'12 months', 'expected_source_ids':['sample'],
        'expected_source_files':[str(p.relative_to(tmp_path))],
        'single_source':True,'single_source_verification':'Whole corpus inspected.',
        'evidence':[{'source_id':'sample','quote':'the limit is 12 months.','location':'line 1'}]} for i in range(5)]}
    assert len(validate_questions(tmp_path,m,q))==5
    q['questions'][0]['evidence'][0]['quote']='fabricated'
    with pytest.raises(ValueError,match='quote'):
        validate_questions(tmp_path,m,q)


def test_freeze_rejects_modified_and_untracked(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    def git(*args): return subprocess.run(['git','-C',str(tmp_path),*args],check=True,capture_output=True,text=True).stdout.strip()
    p=tmp_path/'questions.yaml'; p.write_text('original')
    git('add','questions.yaml')
    git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','freeze')
    commit=git('rev-parse','HEAD')
    assert require_frozen_inputs(tmp_path,commit,['questions.yaml'])['questions.yaml']
    p.write_text('changed')
    with pytest.raises(ValueError,match='changed'):
        require_frozen_inputs(tmp_path,commit,['questions.yaml'])
    with pytest.raises(ValueError):
        require_frozen_inputs(tmp_path,commit,['absent'])
