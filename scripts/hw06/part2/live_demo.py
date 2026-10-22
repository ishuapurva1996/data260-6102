#!/usr/bin/env python3
"""Authenticated 10+5+1-turn Part 2 capture against A's integrated HTTPS app.

Acquires the shared runtime lease once. Never seed accounts, launch/kill servers,
delete records, or fall back to fake storage. Credentials come from environment.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from time import perf_counter
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from pymongo.errors import PyMongoError

from scripts.hw06.runtime_lease import LeaseBusy, RuntimeLease
from src.hw06_shared.config import HW6Config
from src.hw06_shared.contracts import ChatResponse, MemorySnapshot, AggregateResponse
from src.hw06_shared.database import MongoConnection
from src.hw06_shared.serialization import json_value


SESSION_ONE = [
    'My maximum monthly rent is $2400. Please remember that budget.',
    'I am targeting the Japantown neighborhood of San Jose.',
    'I have one cat and need a rental that allows cats.',
    'I want to move on January 15, 2027.',
    'I need an elevator or step-free access because stairs are difficult for me.',
    'What questions should I ask during a rental tour? Keep it brief.',
    'What should I check about the lease deposit? Keep it brief.',
    'How should I compare laundry arrangements? Keep it brief.',
    'What documentation should I prepare for an application? Keep it brief.',
    'Recall my budget, neighborhood, pet, move-in date and accessibility requirement.',
]
SESSION_TWO = [
    'This is a new search session. I prefer a one-bedroom apartment.',
    'A secure bicycle storage area would be useful for me.',
    'I prefer an annual lease rather than a month-to-month arrangement.',
    'What should I ask about utility billing? Keep it brief.',
    'Please summarize my current rental requirements across our sessions.',
    'What do you remember from both sessions, including my earlier budget and cat?',
]


def save(path, value):
    path.write_text(json.dumps(json_value(value), ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def source_commit():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()


def capture(args):
    load_dotenv(args.env_file)
    config = HW6Config.from_env()
    # A fresh directory prevents failed attempts from overwriting earlier evidence.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    receipt = {'student': 'Pragya Apurva', 'kind': 'part2_live_acceptance',
        'started_at': datetime.now(timezone.utc).isoformat(),
        'runner_source_commit': source_commit(), 'status': 'running',
        'checks': {}, 'http_calls': [], 'pending': [],
        'count_semantics': 'UTC daily counts include stored user and assistant messages, all user sessions',
        'latency_semantics': 'http_latency_ms includes transport/auth/serialization and all memory work'}
    output = args.output_dir
    def checkpoint():
        save(output / 'receipt.json', receipt)
    checkpoint()
    try:
        with RuntimeLease(args.runtime_dir, owner='C', purpose='Part 2 authenticated live demo'):
            with MongoConnection(config) as connection:
                try:
                    connection.ping()
                except PyMongoError as exc:
                    receipt['checks']['mongodb'] = {'ok': False, 'error_type': type(exc).__name__}
                    receipt['pending'] = ['A must provision the configured s6102_doc MongoDB instance.',
                        'Mount C routes with the shared database and real SQL authentication.',
                        'Rerun this command with HTTPS/login; capture 10+5+1 real replies, memory, aggregate, '
                        'collection documents, restart persistence, second-user isolation and screenshots.']
                    receipt['status'] = 'blocked'
                    checkpoint()
                    return 2
                receipt['checks']['mongodb'] = {'ok': True}
                with httpx.Client(base_url=args.base_url, verify=str(args.ca_cert), timeout=args.timeout,
                                  follow_redirects=False) as client:
                    username = os.environ.get('HW6_DEMO_USERNAME')
                    password = os.environ.get('HW6_DEMO_PASSWORD')
                    if not username or not password:
                        raise RuntimeError('demo_credentials_missing')
                    from scripts.hw07.client_auth import authenticate
                    user = authenticate(client, username, password)
                    owner = str(user['id'])
                    receipt['checks']['real_login'] = {'ok': True, 'owner_id': owner}
                    installed = client.get('/api/hw06/config')
                    installed.raise_for_status()
                    save(output / 'server-config.json', installed.json())
                    suffix = uuid4().hex
                    user_id = owner + ':hw6:C-demo:' + suffix
                    sessions = [user_id + ':s1', user_id + ':s2']
                    receipt.update(user_id=user_id, sessions=sessions)
                    rental_count_before = connection.database['rentals'].count_documents({})
                    for session_index, messages in enumerate([SESSION_ONE, SESSION_TWO]):
                        for index, message in enumerate(messages, start=1):
                            request_id = uuid4().hex
                            payload = {'user_id': user_id, 'session_id': sessions[session_index], 'message': message}
                            timer = perf_counter()
                            response = client.post('/api/chat', json=payload, headers={
                                'X-HW6-Request-ID': request_id, 'X-HW6-Run-ID': suffix,
                                'X-HW6-Turn-ID': str(index), 'X-HW6-Phase': 'demo'})
                            elapsed = (perf_counter() - timer) * 1000
                            entry = {'session_index': session_index + 1, 'turn': index, 'request': payload,
                                     'http_status': response.status_code, 'http_latency_ms': elapsed,
                                     'response': response.json()}
                            receipt['http_calls'].append(entry)
                            checkpoint()
                            response.raise_for_status()
                            parsed = ChatResponse.model_validate(entry['response'])
                            if not parsed.reply or parsed.request_id != request_id:
                                raise RuntimeError('response_correlation_failed')
                        memory_response = client.get('/api/memory/' + user_id,
                                                     params={'session_id': sessions[session_index]})
                        memory_response.raise_for_status()
                        memory = MemorySnapshot.model_validate(memory_response.json())
                        save(output / f'memory-session-{session_index + 1}.json', memory.model_dump())
                    aggregate_response = client.get('/api/aggregate/' + user_id)
                    aggregate_response.raise_for_status()
                    aggregate = AggregateResponse.model_validate(aggregate_response.json())
                    save(output / 'aggregate.json', aggregate.model_dump())
                    evidence = {}
                    for name in ['messages', 'summaries', 'episodes']:
                        collection = connection.database[name]
                        evidence[name] = {
                            'documents': list(collection.find({'user_id': user_id}).sort([('created_at', 1), ('_id', 1)])),
                            'indexes': list(collection.list_indexes())}
                    save(output / 'collections.json', evidence)
                    s1 = [r for r in evidence['summaries']['documents'] if r['session_id'] == sessions[0]]
                    s2 = [r for r in evidence['summaries']['documents'] if r['session_id'] == sessions[1]]
                    lifetime = [r for r in evidence['summaries']['documents'] if r['scope'] == 'user']
                    count = sum(day.count for day in aggregate.daily_message_counts)
                    receipt['checks'].update(
                        messages_32={'ok': count == 32, 'actual': count},
                        summaries_2_1_lifetime={'ok': len(s1) == 2 and len(s2) == 1 and len(lifetime) == 1},
                        lifetime_used={'ok': bool(receipt['http_calls'][-1]['response']['memory_used']['lifetime_summary'])},
                        episodes_saved={'ok': bool(evidence['episodes']['documents'])},
                        no_part1_count_change={'ok': connection.database['rentals'].count_documents({}) == rental_count_before})
                    receipt['pending'] = ['Capture conversation and Compass/mongosh screenshots with Pragya Apurva visible '
                        'in terminal frames.', 'A must verify persistence after restarting the real app and second-user isolation.',
                        'A must preserve matching server JSONL telemetry with source/model identities for this capture.']
                    receipt['status'] = 'branch_live_capture' if all(c['ok'] for c in receipt['checks'].values()) else 'failed'
                    checkpoint()
                    return 0 if receipt['status'] == 'branch_live_capture' else 1
    except LeaseBusy:
        receipt.update(status='blocked', pending=['Shared runtime is leased. Inspect owner.json and retry after release.'])
    except Exception as exc:
        # Do not persist exception strings: HTTP/connection messages may include credentials.
        receipt.update(status='failed', error_type=type(exc).__name__)
    finally:
        receipt['finished_at'] = datetime.now(timezone.utc).isoformat()
        checkpoint()
    return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True, type=Path)
    parser.add_argument('--runtime-dir', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--base-url', default='https://localhost:8702')
    parser.add_argument('--ca-cert', required=True, type=Path)
    parser.add_argument('--timeout', type=float, default=600)
    return capture(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
