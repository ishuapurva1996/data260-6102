"""Part 4 deterministic contracts; real-model results are separately retained."""
import copy
import io
import json

import pytest

from src.rag.pipeline import (
    REFUSAL, chunk_source, construct_prompt, select_context, validate_sources,
    token_bound, validate_questions, print_retrieval,
)


class Tokenizer:
    def encode(self, text, **kwargs):
        return list(range(len(text.split()) + 2))


def hit(text, i=1, score=.8, source='test'):
    return dict(text=text, chunk_id=f'{source}-{i}', source_id=source,
                title='Test document', location='section 1', start=i * 10,
                end=i * 10 + len(text), score=score)


def test_offsets_limits_ids_and_overlap():
    text = ('Rent is due on the first day. ' * 45)
    source = dict(source_id='one', title='One', sha256='hash')
    rows = chunk_source(source, text, Tokenizer(), [])
    assert rows == chunk_source(source, text, Tokenizer(), [])
    assert rows[0]['start'] == 0 and rows[-1]['end'] == len(text)
    assert len({r['chunk_id'] for r in rows}) == len(rows)
    for i, row in enumerate(rows):
        assert row['text'] == text[row['start']:row['end']]
        assert len(row['text']) <= 500 and row['embedding_tokens'] <= 256
        if i:
            assert rows[i-1]['end'] - row['start'] == row['actual_overlap'] == 50


def test_token_overflow_is_shortened_and_diagnosed():
    class Characters:
        def encode(self, text, **kwargs):
            return list(range(len(text) + 2))
    rows = chunk_source(dict(source_id='x', title='X', sha256='x'), 'x' * 600, Characters(), [])
    assert max(r['embedding_tokens'] for r in rows) <= 256
    assert rows[0]['original_embedding_tokens'] == 502
    assert rows[0]['deviation'] == 'embedding_token_limit'
    assert rows[-1]['end'] == 600


def test_context_cutoff_dedup_and_numeric_negation_safety():
    hits = [hit('Tenants may file within 14 days.', 1),
            hit('Tenants may file within 14 days.', 2),
            hit('Tenants may not file within 14 days.', 3),
            hit('Tenants may file within 30 days.', 4),
            hit('Unrelated detail', 5, .2)]
    kept, decisions = select_context(hits, cutoff=.4, budget=1800)
    assert len(kept) == 3
    assert [d['reason'] for d in decisions].count('redundant_text') == 1
    assert [d['reason'] for d in decisions].count('below_relevance_cutoff') == 1
    assert len(hits) == 5


def test_cross_source_scope_kept_and_budget_whole_chunks():
    hits = [hit('This rule applies.', 1, source='old'), hit('This rule applies.', 2, source='new')]
    kept, _ = select_context(hits, cutoff=0, budget=1800)
    assert len(kept) == 2
    kept, decisions = select_context(hits, cutoff=0, budget=1)
    assert kept == [] and all(d['reason'] == 'budget_limit' for d in decisions)


def test_raw_basic_and_empty_context_prompt_contracts():
    hits = [hit('alpha'), hit('beta', 2)]
    a = construct_prompt('What?', 'A', hits)
    b = construct_prompt('What?', 'B', hits)
    c = construct_prompt('What?', 'C', [])
    assert a['prompt'] == 'What?' and a['context'] == ''
    assert 'alpha' in b['prompt'] and 'beta' in b['prompt']
    assert REFUSAL in c['prompt'] and c['source_labels'] == {}
    assert 'clarif' in c['prompt'].lower()
    with pytest.raises(ValueError, match='window'):
        construct_prompt('x' * 5000, 'A', [])


def test_conservative_budget_and_retrieval_written_first():
    assert token_bound('é') == 2
    stream = io.StringIO()
    print_retrieval('Q', 3, [hit('real text')], stream)
    before_generation = stream.getvalue()
    assert 'requested=3 returned=1' in before_generation
    assert 'real text' in before_generation and '0.800' in before_generation


def test_question_shape_handles_empty_gold():
    qs = [dict(id=f'Q{i}', question=f'Question {i}', evidence_groups=([[]] if i < 4 else [])) for i in range(1, 7)]
    validate_questions(qs)
    with pytest.raises(ValueError):
        validate_questions(qs[:-1])


def test_source_allowlist_and_hashes(tmp_path):
    import hashlib
    sources = []
    for i in range(5):
        path = tmp_path / 'reports/hw04/part4/corpus' / f'{i}.txt'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'Public document {i}')
        sources.append(dict(source_id=str(i), path=str(path.relative_to(tmp_path)),
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    manifest = dict(sources=sources)
    validate_sources(tmp_path, manifest)
    with pytest.raises(ValueError):
        validate_sources(tmp_path, dict(sources=sources[:-1]))
    bad = copy.deepcopy(manifest)
    bad['sources'][1]['source_id'] = '0'
    with pytest.raises(ValueError):
        validate_sources(tmp_path, bad)
    bad = copy.deepcopy(manifest)
    bad['sources'][0]['path'] = 'reports/hw04/part4/questions.yaml'
    with pytest.raises(ValueError):
        validate_sources(tmp_path, bad)
    (tmp_path / sources[0]['path']).write_text('changed')
    with pytest.raises(ValueError, match='hash'):
        validate_sources(tmp_path, manifest)


def test_near_duplicates_keep_changed_exception_scope():
    common = ' '.join('word' + str(i) for i in range(60))
    kept, decisions = select_context([hit(common+' except students.',1),hit(common+' except veterans.',2)],cutoff=0,budget=1800)
    assert len(kept) == 2, decisions


def test_measured_call_preserves_request_failure_and_pre_call_retrieval(tmp_path):
    from src.rag.runner import measured_answer
    stream = io.StringIO()
    config = dict(relevance_cutoff=.4,evidence_budget=1800,generator='qwen3:1.7b',think=False,
                  options=dict(num_ctx=4096,num_predict=384,temperature=0,seed=6102))
    retrieval = dict(hits=[hit('An unrelated archived rule.')],retrieval_id='fixture',
                     query_embedding_seconds=.01,retrieval_seconds=.02)
    class FailedGenerator:
        def generate(self, request):
            assert 'RETRIEVAL' in stream.getvalue()
            assert 'An unrelated archived rule.' in stream.getvalue()
            assert (tmp_path/'requests.jsonl').exists()
            assert request['think'] is False and 'context' not in request
            raise TimeoutError('deliberate fixture timeout')
    row = measured_answer(dict(id='fixture',question='What?'),'C',3,retrieval,config,tmp_path,FailedGenerator(),'fixture',stream)
    assert row['status']=='failed' and row['answer'] is None
    assert 'deliberate fixture timeout' in row['error']
    assert json.loads((tmp_path/'responses.jsonl').read_text())['error']==row['error']


def test_a_does_not_receive_retrieval_or_history(tmp_path):
    from src.rag.runner import measured_answer
    config = dict(relevance_cutoff=.4,evidence_budget=1800,generator='qwen3:1.7b',think=False,
                  options=dict(num_ctx=4096,num_predict=384,temperature=0,seed=6102))
    class Generator:
        def generate(self, request):
            assert request['prompt']=='Example question?'
            assert 'context' not in request and 'system' not in request
            return dict(response='Unmodified fixture output [99]',done=True,done_reason='stop')
    row = measured_answer(dict(id='fixture',question='Example question?'),'A',0,
        dict(hits=[hit('SECRET EVIDENCE')]),config,tmp_path,Generator(),'fixture',io.StringIO())
    assert row['returned_count']==0 and row['answer']=='Unmodified fixture output [99]'


def test_generator_rejects_remote_endpoint_before_network():
    from src.rag.runner import Ollama
    with pytest.raises(ValueError,match='loopback'):
        Ollama(dict(ollama_url='https://example.com',generator='anything'))


def test_gold_coverage_requires_facts_not_just_matching_source():
    from src.rag.runner import evidence_coverage
    q=dict(evidence_groups=[dict(id='fact',alternatives=[dict(source_id='test',start_character=100,end_character=150)])])
    assert evidence_coverage(q,[hit('related text')])=={'fact':False}
    assert evidence_coverage(q,[dict(source_id='test',start=90,end=120),dict(source_id='test',start=120,end=160)])=={'fact':True}


def test_reject_configuration_that_would_silently_truncate():
    from src.rag.runner import validate_config
    c=dict(max_seq_length=256,chunk_size=500,chunk_overlap=50,chunk_unit='characters')
    validate_config(c)
    for key,value in [('max_seq_length',128),('chunk_size',5000),('chunk_overlap',32),('chunk_unit','tokens')]:
        with pytest.raises(ValueError,match=key):
            validate_config(dict(c,**{key:value}))


def test_generator_counter_budgets_exact_package_and_keeps_raw_output(tmp_path):
    from src.rag.runner import measured_answer
    counter=lambda text:len(text.split())
    hits=[hit('This is a complete source sentence. '+('detail '*30),i) for i in range(1,4)]
    kept,_=select_context(hits,.4,1800,token_counter=counter)
    assert len(kept)==1  # true exact duplicates, independent of counting method
    hits=[hit('Source '+str(i)+' '+('detail '*30),i) for i in range(1,4)]
    kept,_=select_context(hits,.4,1800,token_counter=counter)
    assert len(kept)==3
    package=construct_prompt('Question?','C',kept,options={'token_counter':counter})
    assert package['evidence_token_bound']==counter(package['context'])
    cfg=dict(relevance_cutoff=.4,evidence_budget=1800,generator='local',think=False,
             options=dict(num_ctx=4096,num_predict=384,temperature=0,seed=6102))
    class Generator:
        def generate(self, request):
            assert request['prompt']=='Question?' and 'raw' not in request
            return dict(response='Exact raw answer',done=True,done_reason='stop',prompt_eval_count=12)
    row=measured_answer(dict(id='fixture',question='Question?'),'A',0,None,cfg,tmp_path,Generator(),'fixture',io.StringIO(),counter)
    assert row['prompt']=='Question?' and row['answer']=='Exact raw answer'
