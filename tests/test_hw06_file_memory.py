"""File mode behavior: injected model/clock; no MongoDB or local generation."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import os
import subprocess
import sys

import pytest

from src.model_client import CompletionResult, TokenUsage
from src.hw06_memory_files.service import FileMemoryService, inspect_memory


NOW = datetime(2026, 10, 20, 6, tzinfo=timezone.utc)


class Model:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def complete(self, messages, tools=None):
        self.prompts.append(messages)
        answer = self.answers.pop(0)
        return CompletionResult(answer, TokenUsage(10, 5, 15), None)


def service(tmp_path, text, *answers):
    agent = tmp_path / 'AGENT.md'
    agent.write_text('Use Python. Preserve conflicting rental facts. Test offline.\n')
    memory = tmp_path / 'MEMORY.md'
    memory.write_text(text)
    model = Model(*answers)
    return FileMemoryService(agent_path=agent, memory_path=memory,
                             model=model, clock=lambda: NOW), model, memory


def stamp(at=NOW):
    return f'<!-- last_consolidated_utc: {at.isoformat()} -->\n'


@pytest.mark.parametrize('lines,age,expected', [
    (40, timedelta(hours=24), False),
    (41, timedelta(), True),
    (1, timedelta(hours=24, microseconds=1), True),
    (40, timedelta(hours=23), False),
])
def test_strict_trigger_boundaries(lines, age, expected):
    state = inspect_memory(stamp(NOW-age) + 'fact\n'*lines, NOW)
    assert state['consolidation_required'] is expected
    assert state['counts'] == {'entries': lines, 'physical_lines': lines+1,
                              'counted_lines': lines}


@pytest.mark.parametrize('metadata,status', [
    ('', 'missing'), ('<!-- last_consolidated_utc: yesterday -->\n', 'invalid'),
    ('<!-- last_consolidated_utc: 2026-10-20T06:00:00 -->\n', 'invalid'),
    (stamp(NOW+timedelta(seconds=1)), 'future'),
])
def test_unknown_timestamp_requires_consolidation(metadata, status):
    state = inspect_memory(metadata+'fact\n', NOW)
    assert state['timestamp_status'] == status
    assert state['consolidation_required']


def test_comments_and_blank_lines_are_not_counted():
    state = inspect_memory(stamp()+'\n<!-- multi\nline -->\n# note\n fact\n', NOW)
    assert state['counts'] == {'entries': 1, 'physical_lines': 6, 'counted_lines': 1}


def test_commands_and_prompt_boundaries(tmp_path):
    s, model, path = service(tmp_path, stamp()+'- [F01] neighborhood: Willow Glen\n', 'RECALLED')
    assert all(c in s.handle('/help')['reply'] for c in ('/help','/memory','/dream','/compact'))
    assert s.handle('/memory')['reply'] == path.read_text()
    result = s.handle('Where am I searching?')
    assert result['reply'] == 'RECALLED'
    assert result['kind'] == 'reply'
    system = model.prompts[0][0]['content']
    assert 'AGENT_INSTRUCTIONS' in system and 'MEMORY_FACTS_DATA' in system
    assert 'Willow Glen' in system and 'Use Python' in system
    assert s.handle('/unknown')['error'] == 'unknown_command'


def test_compact_preserves_conflicts_and_reports_real_counts(tmp_path):
    original = stamp() + ('- [F01] budget: 2200 USD\n'
                        '- [F02] budget: 2400 USD | corrects=F01\n'
                        '- [F03] area: Willow Glen\n- [F04] area: Willow Glen\n')
    decision = json.dumps({'status':'resolved', 'winner':'F02', 'reason':'F02 explicitly corrects F01'})
    s, model, path = service(tmp_path, original, decision)
    result = s.handle('/compact')
    assert result['before']['entries'] == 4 and result['after']['entries'] == 3
    assert result['before']['physical_lines'] == 5 and result['after']['physical_lines'] == 4
    assert result['after']['counted_lines'] == 3
    assert '2200 USD' in path.read_text() and '2400 USD' in path.read_text()
    assert 'status=superseded' in path.read_text() and 'status=current' in path.read_text()
    assert '[F03,F04]' in path.read_text()
    assert result['conflicts'][0]['winner'] == 'F02'
    restarted = FileMemoryService(agent_path=s.agent_path, memory_path=path,
                                  model=Model(), clock=lambda: NOW)
    assert restarted.handle('/memory')['reply'] == path.read_text()


def test_ambiguous_conflict_cannot_be_silently_resolved(tmp_path):
    text = stamp()+'- [F01] parking: required\n- [F02] parking: unnecessary\n'
    s, model, path = service(tmp_path, text, '{"status":"resolved","winner":"F02","reason":"newer"}')
    result = s.handle('/compact')
    assert result['error'] == 'invalid_consolidation'
    assert path.read_text() == text
    assert result['attempts'][0]['raw']


def test_unresolved_claims_are_retained(tmp_path):
    s, model, path = service(tmp_path, stamp()+'- [F01] pet: cat\n- [F02] pet: dog\n',
                            '{"status":"unresolved","winner":null,"reason":"no correction evidence"}')
    result = s.handle('/compact')
    assert result['conflicts'][0]['status'] == 'unresolved'
    assert path.read_text().count('status=unresolved') == 2


def test_dream_uses_user_evidence_and_keeps_timestamp(tmp_path):
    old = stamp(NOW-timedelta(hours=1))
    extracted = {'facts':[{'key':'pet', 'value':'one cat', 'source_id':'u1',
                           'evidence':'I have one cat.', 'corrects':[]}]}
    s, model, path = service(tmp_path, old, json.dumps(extracted))
    recent = [{'id':'u1','role':'user','content':'I have one cat.'},
              {'id':'a1','role':'assistant','content':'You have a dog.'}]
    result = s.handle('/dream', recent_messages=recent)
    assert result['added_entries'] == 1
    assert 'one cat' in path.read_text() and 'dog' not in path.read_text()
    assert path.read_text().startswith(old)
    assert 'You have a dog.' not in model.prompts[0][-1]['content']


def test_dream_rejects_unsupported_fact(tmp_path):
    answer = {'facts':[{'key':'pet','value':'dog','source_id':'u1',
                        'evidence':'I have one cat.','corrects':[]}]}
    text = stamp()
    s, model, path = service(tmp_path, text, json.dumps(answer))
    result = s.handle('/dream', recent_messages=[{'id':'u1','role':'user','content':'I have one cat.'}])
    assert result['error'] == 'invalid_extraction'
    assert path.read_text() == text


def test_auto_compact_runs_before_reply(tmp_path):
    s, model, path = service(tmp_path, stamp()+'same fact\n'*41, 'OK')
    result = s.handle('hello')
    assert result['auto_compact']['before']['entries'] == 41
    assert result['auto_compact']['after']['entries'] == 1
    assert result['reply'] == 'OK'


def test_original_fixture_and_predeclared_outcomes():
    from scripts.hw06.part4.fixture import original_memory, EXPECTED
    text = original_memory()
    assert len(text.splitlines()) == 55
    assert inspect_memory(text, NOW)['counts']['counted_lines'] == 54
    assert len(EXPECTED['duplicates']) >= 3
    assert len(EXPECTED['conflicts']) >= 3


def test_concurrent_edit_is_preserved(tmp_path):
    text = stamp()+'- [F01] budget: 2200\n- [F02] budget: 2400 | corrects=F01\n'
    s, model, path = service(tmp_path, text)
    def complete(messages, tools=None):
        path.write_text('another writer\n')
        return CompletionResult('{"status":"resolved","winner":"F02","reason":"explicit correction"}',
                                TokenUsage(5,5,10), None)
    model.complete = complete
    result = s.handle('/compact')
    assert result['error'] == 'invalid_consolidation'
    assert path.read_text() == 'another writer\n'
    assert not list(tmp_path.glob('.MEMORY.md-*'))


def test_bad_json_preserves_original(tmp_path):
    text = stamp()+'- [F01] pet: cat\n- [F02] pet: dog\n'
    s, model, path = service(tmp_path, text, 'invalid JSON')
    result = s.handle('/compact')
    assert result['attempts'][0]['raw'] == 'invalid JSON'
    assert path.read_text() == text


def test_cli_read_commands_need_no_model_lease(tmp_path):
    s, model, path = service(tmp_path, stamp()+'a durable fact\n')
    root = Path(__file__).resolve().parents[1]
    process = subprocess.run([sys.executable, str(root/'scripts/hw06/part4/cli.py'),
                              '--agent-file',str(s.agent_path),'--memory-file',str(path),
                              '--runtime-dir',str(tmp_path/'runtime'),
                              '--message','/help','--message','/memory'],
                             cwd=root, env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},
                             text=True, capture_output=True)
    assert process.returncode == 0, process.stderr
    results = [json.loads(line) for line in process.stdout.splitlines()]
    assert [r['command'] for r in results] == ['/help','/memory']
    assert results[1]['reply'] == path.read_text()
    assert not (tmp_path/'runtime').exists()
