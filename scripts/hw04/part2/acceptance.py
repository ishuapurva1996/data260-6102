#!/usr/bin/env python3
"""Real HTTPS/MySQL acceptance. Optionally own/restart a server on a free port.

Writes sanitized operation responses and individual checks. No credentials or
cookie values are saved. Only rows created by this run are removed at the end.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8702)
    parser.add_argument('--manage-server', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT/'reports/hw04/raw/part2/api-acceptance.json')
    args = parser.parse_args()
    load_dotenv(args.env_file)
    result = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'base_url': f'https://127.0.0.1:{args.port}',
              'revision': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'working_tree_dirty': bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
              'checks': [], 'operations': [], 'scope': 'Part 2 real HTTPS/MySQL'}
    process = None
    engine = create_engine(os.environ['HW4_DATABASE_URL'], hide_parameters=True)
    created_id = None
    token = None
    client = httpx.Client(base_url=result['base_url'], verify=False, timeout=15, trust_env=False)
    credentials = {'email':os.environ['HW4_SEED_EMAIL'], 'password':os.environ['HW4_SEED_PASSWORD']}

    def check(name, ok, **details):
        result['checks'].append({'name':name, 'passed':bool(ok), **details})
        if not ok:
            raise AssertionError(name)

    def start():
        nonlocal process, client
        cookies = client.cookies
        client.close()
        client = httpx.Client(base_url=result['base_url'], verify=False, timeout=15, trust_env=False, cookies=cookies)
        process = subprocess.Popen([sys.executable,str(ROOT/'scripts/run_hw04_web.py'),'--port',str(args.port),
                                    '--env-file',str(args.env_file)],cwd=ROOT,stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,start_new_session=True)
        for _ in range(100):
            try:
                if client.get('/api/health').status_code == 200:
                    return
            except httpx.TransportError:
                pass
            if process.poll() is not None:
                raise RuntimeError('Owned HTTPS server exited during startup')
            time.sleep(.1)
        raise RuntimeError('Owned HTTPS server did not become ready')

    def stop():
        nonlocal process
        if process is not None and process.poll() is None:
            import signal
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
            for _ in range(100):
                with socket.socket() as probe:
                    if probe.connect_ex(('127.0.0.1', args.port)) != 0:
                        break
                time.sleep(.1)
            else:
                raise RuntimeError('Owned server port did not close after shutdown')
        process = None

    def operation(name, method, path, expected, payload=None):
        response = client.request(method,path,json=payload) if payload is not None else client.request(method,path)
        body = response.json() if response.content else None
        result['operations'].append({'name':name,'method':method,'path':path,'status':response.status_code,'response':body})
        check(name,response.status_code == expected,status=response.status_code)
        return body

    try:
        if args.manage_server:
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1',args.port)) == 0:
                    raise RuntimeError('Port already in use; refusing to stop or reuse another server')
            start()
        with engine.connect() as connection:
            result['mysql_version'] = connection.scalar(text('SELECT VERSION()'))
            check('database name',connection.scalar(text('SELECT DATABASE()')) == 's6102_rel')
            result['tables'] = list(connection.execute(text('SHOW TABLES')).scalars())
        check('anonymous rentals denied',client.get('/api/rentals').status_code == 401)
        check('bad credentials denied', client.post('/api/auth/login',json={**credentials,'password':'incorrect-for-test'}).status_code == 401)
        login = client.post('/api/auth/login',json=credentials)
        check('valid login',login.status_code == 200 and set(login.json()['user']) == {'id','name','email'})
        token = client.cookies.get('s6102_session')
        header = login.headers.get('set-cookie','')
        attrs = header.split(';')[1:]
        result['cookie_attributes'] = [x.strip() for x in attrs]
        check('cookie security',all(x in header.lower() for x in ('httponly','secure','samesite=lax','path=/')))
        title = 'HW4 acceptance ' + uuid.uuid4().hex[:10]
        payload = {'listingTitle':title,'propertyAddress':'260 Verification Lane, San Jose, CA',
                   'submitterEmail':'verification@example.com','description':'A real MySQL acceptance record for verified persistent CRUD.',
                   'propertyType':'apartment','termsAccepted':True}
        row = operation('POST create','POST','/api/rentals',201,payload)
        created_id = row['id']
        rows = operation('GET list','GET','/api/rentals?q='+title,200)
        check('created row listed',len(rows)==1 and rows[0] == row)
        read = operation('GET by ID','GET',f'/api/rentals/{created_id}',200)
        check('ID read matches create', read == row)
        updated = operation('PUT update','PUT',f'/api/rentals/{created_id}',200,
                            {'listingTitle':title+' updated','propertyAddress':'261 Verification Lane'})
        check('other fields preserved',all(updated[k]==row[k] for k in ('submitterEmail','description','propertyType','termsAccepted')))
        check('invalid write rejected',client.put(f'/api/rentals/{created_id}',json={'listingTitle':'','propertyAddress':'bad'}).status_code==422)
        if args.manage_server:
            stop()
            start()
            check('real process restart retains login',client.get('/api/auth/me').status_code==200)
            check('real process restart retains rental',client.get(f'/api/rentals/{created_id}').json()==updated)
        operation('DELETE record','DELETE',f'/api/rentals/{created_id}',204)
        check('deleted row absent',client.get(f'/api/rentals/{created_id}').status_code==404)
        created_id = None
        logout = client.post('/api/auth/logout')
        replay = client.get('/api/rentals',headers={'Cookie':'s6102_session='+token})
        check('logout and copied-token replay',logout.status_code==204 and replay.status_code==401)
        with engine.connect() as connection:
            check('logout removes database token',connection.scalar(text('SELECT COUNT(*) FROM sessions WHERE id=:id'),{'id':token})==0)
        token = None
        for expiry in ('idle','absolute'):
            client.post('/api/auth/login',json=credentials).raise_for_status()
            token = client.cookies.get('s6102_session')
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            with engine.begin() as connection:
                if expiry == 'idle':
                    connection.execute(text('UPDATE sessions SET last_activity_at=:t WHERE id=:id'),{'t':now-timedelta(seconds=301),'id':token})
                else:
                    connection.execute(text('UPDATE sessions SET expires_at=:t WHERE id=:id'),{'t':now-timedelta(seconds=1),'id':token})
            check(expiry+' expiry denied',client.get('/api/auth/me').status_code==401)
        check('unknown API stays JSON 404',client.get('/api/not-a-route').status_code==404 and client.get('/api/not-a-route').headers['content-type'].startswith('application/json'))
        check('docs available',client.get('/docs').status_code==200)
    except Exception as exc:
        result['error'] = type(exc).__name__  # Exceptions may contain credentials; never serialize them.
        result['checks'].append({'name':'acceptance completed','passed':False,'error_type':type(exc).__name__})
    finally:
        with engine.begin() as connection:
            if created_id is not None:
                connection.execute(text('DELETE FROM rentals WHERE id=:id'),{'id':created_id})
            if token:
                connection.execute(text('DELETE FROM sessions WHERE id=:id'),{'id':token})
        stop()
        client.close()
        engine.dispose()
        result['status'] = 'pass' if result['checks'] and all(c['passed'] for c in result['checks']) else 'fail'
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'status':result['status'],'checks':len(result['checks']),'output':str(args.output)}))
    return 0 if result['status']=='pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
