#!/usr/bin/env python3
"""Real integrated acceptance and one unscored N30 pilot, never the four-way sweep."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import sys
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'code')]

from scripts.hw06.live_support import add_runtime_arguments, load_config, running_app, save
from scripts.hw06.runtime_lease import RuntimeLease
from scripts.hw06.part1.verify import run_api_checks
from scripts.hw06.part2.live_demo import SESSION_ONE, SESSION_TWO
from scripts.hw06.part4.audit import audit
from src.hw06_experiments.design import load_design
from src.hw06_experiments.live import source_state
from src.hw06_memory_files.service import FileMemoryService, inspect_memory
from src.hw06_shared.config import HW6Config
from src.hw06_shared.contracts import ChatResponse, render_window
from src.hw06_shared.database import MongoConnection
from src.hw06_shared.models import build_generation_client, QwenTokenCounter
from src.hw06_shared.serialization import json_value, utc_now
from src.hw06_shared.telemetry import CallEvent, JsonlTelemetry, RequestContext


def chat(client, user, session, message, result, output, *, phase='demo', turn=None, probe=None):
    rid = uuid4().hex
    headers = {'X-HW6-Request-ID':rid, 'X-HW6-Run-ID':result['run_id'], 'X-HW6-Phase':phase}
    if turn is not None:
        headers['X-HW6-Turn-ID'] = str(turn)
    if probe:
        headers['X-HW6-Probe-ID'] = probe
    payload = dict(user_id=user, session_id=session, message=message)
    timer = perf_counter()
    response = client.post('/api/chat', json=payload, headers=headers)
    row = dict(request_id=rid, phase=phase, turn=turn, probe_id=probe, request=payload,
               status_code=response.status_code, http_latency_ms=(perf_counter()-timer)*1000,
               response=response.json())
    result['requests'].append(row)
    save(output, result)
    response.raise_for_status()
    parsed = ChatResponse.model_validate(row['response'])
    if parsed.request_id != rid or not parsed.reply.strip():
        raise RuntimeError('Chat response identity/content failed')
    print(f'Pragya Apurva | {result["kind"]} | turn {turn or probe} | HTTP 200', flush=True)
    return parsed


def file_checks(config, work):
    original = (ROOT/'reports/hw06/raw/part4/MEMORY.original.md').read_text()
    memory = work/'file-MEMORY.md'
    memory.write_text(original)
    model = build_generation_client(config)
    sink = JsonlTelemetry(work/'file-events.jsonl')
    def service():
        return FileMemoryService(agent_path=ROOT/'AGENT.md', memory_path=memory, model=model, telemetry=sink)
    engine = service()
    result = {'kind':'integrated_file_acceptance', 'source':source_state(), 'commands':[]}
    for command in ('/help','/memory','/compact'):
        answer = engine.handle(command)
        result['commands'].append({'command':command,'result':answer})
        save(work/'file-result.json', result)
        if 'error' in answer:
            raise RuntimeError('File command failed; failed output retained')
    consolidated = memory.read_text()
    (work/'MEMORY.original.md').write_text(original)
    (work/'MEMORY.consolidated.md').write_text(consolidated)
    expected = json.loads((ROOT/'reports/hw06/raw/part4/expected_conflicts.json').read_text())
    result['independent_conflict_audit'] = audit(original, consolidated, expected)
    if not result['independent_conflict_audit']['passed']:
        raise RuntimeError('Independent consolidation audit failed')
    user = {'id':uuid4().hex, 'role':'user', 'content':'Please remember: I require an induction stove.',
            'user_id':'file-local','session_id':'file-local','created_at':utc_now()}
    reply = engine.handle(user['content'])
    result['conversation'] = {'user':user['content'], 'response':reply}
    assistant = {**user, 'id':uuid4().hex, 'role':'assistant','content':reply['reply']}
    dream = engine.handle('/dream', recent_messages=[user,assistant])
    result['commands'].append({'command':'/dream','result':dream})
    if 'error' in dream or dream.get('added_entries',0) < 1:
        save(work/'file-result.json', result)
        raise RuntimeError('Dream did not persist an evidenced user fact')
    persisted = memory.read_bytes()
    restarted = service()
    result['restart'] = restarted.handle('What stove do I require in a rental?')
    result['restart_bytes_unchanged'] = memory.read_bytes() == persisted
    result['restart_fact_recalled'] = 'induction' in result['restart']['reply'].lower()
    result['final_counts'] = inspect_memory(memory.read_text(), utc_now())['counts']
    result['instruction_compliance'] = {
        'source_helper':'src/hw06_memory_files/service.py:inspect_memory',
        'aware_utc_clock':True, 'strict_threshold_tests':'tests/test_hw06_file_memory.py',
        'no_storage_mutation_on_inspection':True,
        'AGENT_categories':'project, stack, conventions, tests, prohibited actions',
        'basis':'Integrated focused tests plus independent conflict audit; AGENT.md and helper content preserved from E.'}
    result['passed'] = result['restart_bytes_unchanged'] and result['restart_fact_recalled']
    save(work/'file-result.json', result)
    if not result['passed']:
        raise RuntimeError('File restart recall failed')


def core(args, config, lease):
    credentials = (os.environ['HW7_MODERATOR_USERNAME'], os.environ['HW7_MODERATOR_PASSWORD'])
    result = {'kind':'integrated_part2_acceptance', 'run_id':uuid4().hex, 'source':source_state(), 'requests':[]}
    output = args.work_dir/'part2-result.json'
    with MongoConnection(config) as mongo:
        mongo.ping()
        with running_app(config, lease=lease, directory=args.work_dir/'core-app',
                env_files=args.env_file, cert=args.cert, key=args.key,
                credentials=credentials) as (client, owner):
            part1 = {'kind':'integrated_part1_acceptance', 'source':source_state()}
            run_api_checks(client, mongo.database, part1, keep_sample=True)
            save(args.work_dir/'part1-result.json', json_value(part1))
            user = owner+':hw6:A-acceptance:'+result['run_id']
            sessions = [user+':one',user+':two']
            result.update(user_id=user,sessions=sessions)
            for session, messages in zip(sessions,(SESSION_ONE,SESSION_TWO)):
                for turn,message in enumerate(messages,1):
                    chat(client,user,session,message,result,output,turn=turn)
            result['memory'] = client.get('/api/memory/'+user,params={'session_id':sessions[1]}).json()
            result['aggregate'] = client.get('/api/aggregate/'+user).json()
            result['collections'] = {name:list(mongo.database[name].find({'user_id':user}).sort([('created_at',1),('_id',1)]))
                                     for name in ('messages','summaries','episodes')}
            result['collections'] = json_value(result['collections'])
            summaries = result['collections']['summaries']
            result['checks'] = {'32_messages':len(result['collections']['messages']) == 32,
                'session_summaries_2_plus_1': [sum(r['scope']=='session' and r['session_id']==s for r in summaries) for s in sessions] == [2,1],
                'lifetime_summary':sum(r['scope']=='user' for r in summaries)==1,
                'lifetime_used':bool(result['requests'][-1]['response']['memory_used']['lifetime_summary']),
                'episodes_saved':bool(result['collections']['episodes']),
                'different_namespace_empty':not client.get('/api/memory/'+owner+':hw6:empty:'+uuid4().hex).json()['messages'],
                'other_owner_denied':client.get('/api/memory/999:hw6:foreign').status_code == 403}
            save(output,result)
        with running_app(config, lease=lease, directory=args.work_dir/'restart-app',
                env_files=args.env_file, cert=args.cert, key=args.key,
                credentials=credentials) as (client,owner):
            after = client.get('/api/memory/'+user,params={'session_id':sessions[1]}).json()
            result['checks']['mongo_restart_persistence'] = after == result['memory']
        result['passed'] = all(result['checks'].values())
        save(output,result)
        if not result['passed']:
            raise RuntimeError('Part 2 acceptance failed')


def comparison(args, config, lease):
    result = {'kind':'integrated_qualitative_comparison', 'run_id':uuid4().hex,
              'source':source_state(), 'requests':[]}
    output = args.work_dir/'comparison.json'
    facts = ['My initial rental budget is 2200 USD per month. I target Willow Glen and have one cat.',
             'Correction: my current rental budget is 2400 USD, replacing 2200 USD.',
             'Briefly explain what to check on a rental tour.',
             'Briefly explain what to check about utilities.',
             'Summarize my current rental preferences briefly.']
    with running_app(config, lease=lease, directory=args.work_dir/'comparison-app',
            env_files=args.env_file, cert=args.cert, key=args.key) as (client,owner):
        user = owner+':hw6:A-compare:'+result['run_id'];session=user+':session'
        for turn,message in enumerate(facts,1):
            chat(client,user,session,message,result,output,turn=turn)
    question = 'What are my current maximum monthly rent, neighborhood and pet requirement?'
    with running_app(config, lease=lease, directory=args.work_dir/'comparison-restart-app',
            env_files=args.env_file, cert=args.cert, key=args.key) as (client,owner):
        recalled = chat(client,user,session,question,result,output,turn=6)
        result['mongo_recall_after_restart'] = recalled.reply
        result['mongo_inspection'] = client.get('/api/memory/'+user).json()
    memory = args.work_dir/'comparison-MEMORY.md'
    memory.write_text('<!-- last_consolidated_utc: '+utc_now().isoformat()+' -->\n'
                      '- [S01] budget: 2200 USD\n- [S02] neighborhood: Willow Glen\n- [S03] pet: one cat\n')
    model = build_generation_client(config)
    sink = JsonlTelemetry(args.work_dir/'comparison-file-events.jsonl')
    service = FileMemoryService(agent_path=ROOT/'AGENT.md',memory_path=memory,model=model,telemetry=sink)
    record = {'id':'comparison-correction','role':'user','content':facts[1],
              'user_id':'file-local','session_id':'file-local','created_at':utc_now()}
    result['file_correction'] = service.handle('/dream',recent_messages=[record])
    result['file_compact'] = service.handle('/compact')
    if 'error' in result['file_correction'] or 'error' in result['file_compact']:
        save(output,result);raise RuntimeError('File comparison update failed')
    persisted = memory.read_bytes()
    restarted = FileMemoryService(agent_path=ROOT/'AGENT.md',memory_path=memory,model=model,telemetry=sink)
    result['file_recall_after_restart'] = restarted.handle(question)['reply']
    result['file_restart_bytes_unchanged'] = persisted == memory.read_bytes()
    result['file_inspection'] = memory.read_text()
    result['checks'] = {}
    for mode in ('mongo','file'):
        answer = result[mode+'_recall_after_restart'].lower().replace(',','')
        result['checks'][mode+'_current_correction_and_facts'] = all(term in answer for term in ('2400','willow glen','cat'))
    result['dimensions'] = {
        'inspectability':'Actual Mongo inspection JSON and Markdown content attached; database records have IDs/timestamps/vectors, file facts are readable with correction statuses.',
        'restart':'Both actual app/service restarts are exercised; answers and file bytes are attached.',
        'many_sessions':'Functional observation: Mongo stores scoped user/session records and indexed retrieval. File service selects one caller-owned path and keeps process-local chat history. No scalability benchmark was run.',
        'indispensable_facts':'Both retained the corrected sample facts in this scenario. Mongo retrieval/top-k and summaries can omit facts; file prompt/context limits and consolidation can also affect recall. Persistence alone is not a guarantee.'}
    result['passed'] = all(result['checks'].values()) and result['file_restart_bytes_unchanged']
    save(output,result)
    if not result['passed']:
        raise RuntimeError('Qualitative recall check failed; actual answers retained')


def pilot(args, config, lease):
    config = HW6Config(**{**config.model_dump(),'short_term_n':30,'policy':'baseline'})
    conversation,probes,hashes = load_design()
    result = {'kind':'unscored_N30_pilot', 'run_id':uuid4().hex, 'source':source_state(),
              'input_hashes':hashes, 'config':config.public_dict(), 'requests':[],
              'excluded_from_measured_results':True, 'probe_order':'sequential_fixed_order'}
    output = args.work_dir/'pilot.json'
    with running_app(config, lease=lease, directory=args.work_dir/'pilot-app',
            env_files=args.env_file, cert=args.cert, key=args.key) as (client,owner):
        user=owner+':hw6:A-pilot:'+result['run_id'];session=user+':session'
        result.update(user_id=user,session_id=session)
        for turn,message in enumerate(conversation['messages'],1):
            chat(client,user,session,message,result,output,phase='test',turn=turn)
        for probe in probes['probes']:
            chat(client,user,session,probe['question'],result,output,phase='test',probe=probe['id'])
        result['inspection'] = client.get('/api/memory/'+user).json()
    events = [CallEvent.model_validate(json.loads(line)) for line in
              (args.work_dir/'pilot-app/events.jsonl').read_text().splitlines()]
    counter = QwenTokenCounter(config.tokenizer_path,expected_sha256=config.tokenizer_sha256)
    main = [event for event in events if event.kind=='request']
    generative = [event for event in events if event.kind!='embedding']
    blocks = ('system','session_summary','lifetime_summary','window','episodes','current_message')
    result['checks'] = {'35_correlated_main_events':len(main)==35 and
        {e.context.request_id for e in main}=={r['request_id'] for r in result['requests']},
        'all_events_successful':all(e.status=='ok' for e in events),
        'model_usage_reported':all(e.usage_source=='model_reported' for e in generative),
        'context_fits':all(e.prompt_tokens+config.output_limit <= config.context_window for e in generative),
        'no_output_cutoff':all(e.finish_reason not in ('length','max_tokens') and e.completion_tokens < config.output_limit for e in generative),
        'N30_reached':max(e.components.window for e in main)>0 and max(r['response']['memory_used']['short_term_count'] for r in result['requests'])==30,
        'components_recomputed':all(all(getattr(e.components,b)==(counter(getattr(e.component_text,b)) if getattr(e.component_text,b) else 0) for b in blocks) for e in main),
        'residuals_correct':all(e.components.template_residual==e.prompt_tokens-sum(getattr(e.components,b) for b in blocks) for e in main),
        'current_message_once':all(e.component_text.current_message==r['request']['message'] and
            all(m['content']!=r['request']['message'] for m in r['response']['memory_used']['short_term_messages']) for e,r in zip(main,result['requests'])),
        'auxiliary_extraction_and_query':sum(e.operation=='extraction' for e in events)==35 and sum(e.operation=='query' for e in events)==35,
        'summary_cadence':sum(e.operation=='session_summary' for e in events)==7}
    result['max_prompt_tokens'] = max(e.prompt_tokens for e in generative)
    result['max_completion_tokens'] = max(e.completion_tokens for e in generative)
    result['n30_context_fit'] = result['checks']['context_fits']
    result['no_prompt_truncation'] = result['checks']['context_fits'] and result['checks']['N30_reached']
    result['passed'] = all(result['checks'].values())
    save(output,result)
    if not result['passed']:
        raise RuntimeError('Pilot pipeline check failed; preserve this attempt')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_arguments(parser)
    parser.add_argument('--stage',choices=['core','file','comparison','pilot'],required=True)
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True,exist_ok=False)
    config=load_config(args)
    with RuntimeLease(args.runtime_dir,owner='A-acceptance',purpose='integration '+args.stage) as lease:
        {'core':core,'file':lambda a,c,l:file_checks(c,a.work_dir),
         'comparison':comparison,'pilot':pilot}[args.stage](args,config,lease)
    print('Pragya Apurva | integrated '+args.stage+' checks passed',flush=True)


if __name__=='__main__':
    main()
