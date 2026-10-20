#!/usr/bin/env python3
"""Objective smoke verifier. Disposable data only; application source is read-only."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'code')]

from scripts.hw06.live_support import add_runtime_arguments, load_config, running_app, save
from scripts.hw06.runtime_lease import RuntimeLease
from src.hw06_experiments.live import source_state
from src.hw06_shared.contracts import ChatResponse
from src.hw06_shared.database import MongoConnection
from src.hw06_shared.models import build_generation_client
from src.hw06_shared.serialization import utc_now
from src.hw06_memory_files.service import FileMemoryService


def verify(args):
    config = load_config(args)
    before = source_state()
    args.work_dir.mkdir(parents=True, exist_ok=False)
    result = {'homework':6, 'sid4':6102, 'student':'Pragya Apurva',
        'commit_hash':before['source_commit'], 'application_source_sha256':before['source_sha256'],
        'source_paths':list(before['source_hashes']), 'model_configuration':config.public_dict(),
        'seed':config.seed, 'verify_seed':config.verify_seed,
        'started_at':utc_now().isoformat(), 'checks':[]}
    def check(name, condition):
        result['checks'].append({'name':name, 'passed':bool(condition)})
        if not condition:
            raise RuntimeError(name)
    user = None
    document_id = None
    try:
        with RuntimeLease(args.runtime_dir, owner='A-smoke', purpose='objective integrated smoke') as lease:
            with MongoConnection(config) as mongo:
                mongo.ping()
                check('mongodb_reachable', True)
                try:
                    with running_app(config, lease=lease, directory=args.work_dir/'app',
                            env_files=args.env_file, cert=args.cert, key=args.key) as (client, owner):
                        check('https_health_on_8702', client.get('/api/health').status_code == 200)
                        check('existing_real_login', client.get('/api/auth/me').status_code == 200)
                        payload = {'listingTitle':'Smoke '+uuid4().hex, 'propertyType':'apartment',
                                   'availableFrom':'2027-01-15T00:00:00Z'}
                        created = client.post('/api/doc-rentals', json=payload)
                        check('document_create', created.status_code == 201)
                        document_id = created.json()['id']
                        path = '/api/doc-rentals/'+document_id
                        check('document_read', client.get(path).status_code == 200)
                        check('document_update', client.put(path, json={**payload,'status':'reserved'}).status_code == 200)
                        check('invalid_document_rejected', client.post('/api/doc-rentals', json={}).status_code == 422)
                        check('document_delete', client.delete(path).status_code == 204 and client.get(path).status_code == 404)
                        user = owner+':hw6:smoke:'+uuid4().hex
                        response = client.post('/api/chat', json={'user_id':user,'message':'My rental budget is $2400. Reply briefly.'})
                        check('chat_http_success', response.status_code == 200)
                        chat = ChatResponse.model_validate(response.json())
                        check('chat_reply_and_memory_shape', bool(chat.reply.strip()) and bool(chat.session_id))
                        check('memory_endpoint', client.get('/api/memory/'+user).status_code == 200)
                        aggregate = client.get('/api/aggregate/'+user)
                        check('aggregate_endpoint', aggregate.status_code == 200 and
                              sum(row['count'] for row in aggregate.json()['daily_message_counts']) == 2)
                        check('other_user_denied', client.get('/api/memory/999:hw6:someone').status_code == 403)
                        memory = args.work_dir/'MEMORY.md'
                        memory.write_text('<!-- last_consolidated_utc: '+utc_now().isoformat()+' -->\n- smoke: persisted\n')
                        service = FileMemoryService(agent_path=ROOT/'AGENT.md', memory_path=memory,
                                                    model=build_generation_client(config))
                        check('file_memory_load_commands', 'persisted' in service.handle('/memory')['reply'] and
                              '/compact' in service.handle('/help')['reply'])
                finally:
                    if user:
                        for name in ('messages','summaries','episodes'):
                            mongo.database[name].delete_many({'user_id':user})
                    if document_id:
                        from bson import ObjectId
                        mongo.database['rentals'].delete_one({'_id':ObjectId(document_id)})
        check('application_source_unchanged', source_state() == before)
        result['passed'] = True
    except Exception as error:
        result.update(passed=False, error_type=type(error).__name__)
    result['finished_at'] = utc_now().isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save(args.output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_arguments(parser)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/hw06/verification.json')
    result = verify(parser.parse_args())
    print(json.dumps({'passed':result['passed'], 'checks':result['checks']},indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
