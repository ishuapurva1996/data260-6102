#!/usr/bin/env python3
"""Verify built React and all performance combinations on an owned HTTPS server.

Uses an existing migrated, seeded MySQL instance. No seed/reset/index mutation.
Only this run's login token and server process are cleaned up.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time

import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from acceptance import cleanup_owned_resources

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('partial_verifier', ROOT/'scripts/verify_hw04_parts123.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8702)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/hw04/raw/part2/integration-smoke.json')
    args = parser.parse_args()
    load_dotenv(args.env_file)
    result = {'scope':'Integrated Parts 1–3, real HTTPS and MySQL',
              'started_at':datetime.now(timezone.utc).isoformat(),
              'revision':verifier.git('rev-parse','HEAD'),
              'source_sha256':verifier.source_fingerprints(),
              'base_url':f'https://127.0.0.1:{args.port}', 'checks':[], 'performance':[]}
    engine = create_engine(os.environ['HW4_DATABASE_URL'], hide_parameters=True)
    client = httpx.Client(base_url=result['base_url'], verify=False, timeout=20, trust_env=False)
    process, token = None, None

    def check(name, passed, **details):
        result['checks'].append({'name':name, 'passed':bool(passed), **details})
        if not passed:
            raise AssertionError(name)

    def stop():
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)

    try:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1',args.port))
        subprocess.run([sys.executable,str(ROOT/'scripts/run_hw04_web.py'),'--prepare-cert'],
                       cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
        # Track Uvicorn itself: waiting only for a launcher could leave its child
        # draining requests while the next evidence runner claims the same port.
        process = subprocess.Popen([sys.executable,'-m','uvicorn','web_application.main:app',
                                    '--app-dir',str(ROOT/'code'),'--host','127.0.0.1',
                                    '--port',str(args.port),'--workers','1',
                                    '--timeout-graceful-shutdown','2',
                                    '--ssl-certfile',str(ROOT/'tmp/https/cert.pem'),
                                    '--ssl-keyfile',str(ROOT/'tmp/https/key.pem')],
                                   cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                   start_new_session=True)
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError('Owned server exited')
            try:
                if client.get('/api/health').status_code==200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(.1)
        else:
            raise RuntimeError('Owned server readiness timeout')
        with engine.connect() as connection:
            result['mysql_version'] = connection.scalar(text('SELECT VERSION()'))
            result['database'] = connection.scalar(text('SELECT DATABASE()'))
            result['mysql_server_uuid'] = connection.scalar(text('SELECT @@server_uuid'))
            result['dataset_counts'] = {table:connection.scalar(text(f'SELECT COUNT(*) FROM {table}'))
                                        for table in ('rentals','property_managers')}
        check('MySQL shared database',result['database']=='s6102_rel')
        check('Exact performance dataset',result['dataset_counts']=={'rentals':5000,'property_managers':200})
        index = (ROOT/'frontend/dist/index.html').read_bytes()
        for route in ('/','/login','/create','/update?id=1','/delete?id=1'):
            response = client.get(route)
            check('Built React deep link '+route,response.status_code==200 and response.content==index)
        assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"',index.decode())
        check('Built asset references present',bool(assets))
        for asset in assets:
            response = client.get(asset)
            check('Built asset served '+asset,response.status_code==200 and response.content==(ROOT/'frontend/dist'/asset.lstrip('/')).read_bytes())
        unknown = client.get('/api/not-a-route')
        check('Unknown API remains JSON404',unknown.status_code==404 and unknown.headers.get('content-type','').startswith('application/json'))
        check('OpenAPI docs retained',client.get('/docs').status_code==200)
        for version in ('naive','fixed'):
            check(version+' requires shared auth',client.get('/api/rentals/'+version).status_code==401)
        response = client.post('/api/auth/login',json={'email':os.environ['HW4_SEED_EMAIL'],'password':os.environ['HW4_SEED_PASSWORD']})
        check('Shared login succeeds',response.status_code==200)
        token = client.cookies.get('s6102_session')
        check('Ordinary CRUD uses same session',client.get('/api/rentals/1').status_code==200)
        for size in (10,50,200):
            payloads=[]
            for version in ('naive','fixed'):
                response = client.get(f'/api/rentals/{version}?page_size={size}&offset=0')
                payload=response.json()
                total=int(response.headers.get('X-SQL-Statements','-1'))
                data=int(response.headers.get('X-Data-SQL-Statements','-1'))
                check(f'{version}/{size} response and SQL counts',response.status_code==200 and len(payload)==size
                      and total==((size+3) if version=='naive' else 3)
                      and data==((size+1) if version=='naive' else 1))
                result['performance'].append({'version':version,'page_size':size,'status':response.status_code,
                                              'total_sql':total,'data_sql':data,'auth_sql':total-data,
                                              'response_sha256':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()})
                payloads.append(payload)
            check(f'Equivalent ordered payloads/{size}',payloads[0]==payloads[1] and [r['id'] for r in payloads[0]]==list(range(1,size+1)))
        check('Logout succeeds',client.post('/api/auth/logout').status_code==204)
        for version in ('naive','fixed'):
            check(version+' rejects revoked token',client.get('/api/rentals/'+version,headers={'Cookie':'s6102_session='+token}).status_code==401)
        check('Application source unchanged during smoke',result['source_sha256']==verifier.source_fingerprints())
    except Exception as exc:
        result['checks'].append({'name':'Integration smoke completed','passed':False,'error_type':type(exc).__name__})
    finally:
        failures=cleanup_owned_resources(engine,None,token,stop,client)
        if failures:
            result['checks'].append({'name':'Owned resources cleaned','passed':False,'failures':failures})
        result['status']='pass' if result['checks'] and all(c['passed'] for c in result['checks']) else 'fail'
        result['finished_at']=datetime.now(timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'status':result['status'],'checks':len(result['checks']),'output':str(args.output)}))
    return 0 if result['status']=='pass' else 1


if __name__=='__main__':
    raise SystemExit(main())
