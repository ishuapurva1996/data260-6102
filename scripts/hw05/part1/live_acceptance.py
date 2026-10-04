#!/usr/bin/env python3
"""Capture real authenticated HTTPS API checks; never record cookies/passwords.

Requires HW4_SEED_EMAIL/PASSWORD, HW5_CA_CERT and an already running owned
service. Only rows created by this run are deleted. This is HTTP evidence,
not a replacement for the assignment's genuine Postman screenshots.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='https://localhost:8702')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records = []
    stamp = lambda: datetime.now(timezone.utc).isoformat()
    result = {'started_at': stamp(), 'revision': subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], text=True).strip(), 'transport': 'real HTTPS + MySQL',
        'source_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True)),
        'checks': records}
    managers, rentals = set(), set()
    with httpx.Client(base_url=args.base_url, verify=os.environ['HW5_CA_CERT'], timeout=15) as client:
        login = client.post('/api/auth/login', json={'email': os.environ['HW4_SEED_EMAIL'],
                                                    'password': os.environ['HW4_SEED_PASSWORD']})
        assert login.status_code == 200, 'Private test login failed'
        def call(label, method, path, status=200, body=None):
            response = client.request(method, path, json=body)
            data = response.json() if response.status_code != 204 else None
            entry = {'label': label, 'timestamp': stamp(), 'method': method, 'path': path,
                     'input': body, 'expected_status': status, 'status': response.status_code,
                     'total_count': response.headers.get('X-Total-Count'), 'output': data,
                     'pass': response.status_code == status}
            records.append(entry)
            print(f'{"PASS" if entry["pass"] else "FAIL"} {label}: HTTP {response.status_code}')
            assert entry['pass'], label
            return data, response
        try:
            manager_body = {'name': 'HW5 Evidence Manager', 'company': 'Orchard Test Homes',
                            'email': f'hw5-{uuid4().hex}@example.com'}
            manager, _ = call('Manager create', 'POST', '/api/property-managers', 201, manager_body)
            mid = manager['id']; managers.add(mid)
            call('Manager list pagination', 'GET', '/api/property-managers?limit=1&offset=0')
            call('Manager detail', 'GET', f'/api/property-managers/{mid}')
            call('Manager unique email conflict', 'POST', '/api/property-managers', 409, manager_body)
            manager_body['company'] = 'Updated Orchard Test Homes'
            call('Manager update', 'PUT', f'/api/property-managers/{mid}', 200, manager_body)
            empty, _ = call('Empty relationship', 'GET', f'/api/property-managers/{mid}/rentals')
            assert empty == []
            body = {'listingTitle': 'HW5 Live Acceptance Home', 'propertyAddress': '6102 Evidence Lane, San Jose, CA',
                    'submitterEmail': 'evidence-owner@example.com', 'description': 'A sunny rental home used only for the owned acceptance checks.',
                    'propertyType': 'house', 'termsAccepted': True, 'managerId': mid, 'availableUnits': 2}
            rental, _ = call('Rental create generated code', 'POST', '/api/rentals', 201, body)
            rid = rental['id']; rentals.add(rid)
            assert rental['listingCode'] == f'S6102-R-{rid}'
            call('Rental list pagination', 'GET', '/api/rentals?limit=2&offset=1')
            call('Rental detail', 'GET', f'/api/rentals/{rid}')
            related, r = call('Relationship query', 'GET', f'/api/property-managers/{mid}/rentals?limit=1&offset=0')
            assert [x['id'] for x in related] == [rid] and r.headers['X-Total-Count'] == '1'
            call('Referenced manager delete restricted', 'DELETE', f'/api/property-managers/{mid}', 409)
            call('Rental unique code conflict', 'POST', '/api/rentals', 409, {**body,'listingCode':rental['listingCode']})
            call('Negative units invalid', 'PUT', f'/api/rentals/{rid}', 422,
                 {'listingTitle':body['listingTitle'],'propertyAddress':body['propertyAddress'],'availableUnits':-1})
            call('Malformed listing code invalid', 'POST', '/api/rentals', 422, {**body,'listingCode':'INVALID'})
            call('Malformed manager email invalid', 'POST', '/api/property-managers', 422, {**manager_body,'email':'invalid'})
            call('Invalid pagination', 'GET', '/api/rentals?limit=0', 422)
            absent = 2147483647
            while client.get(f'/api/property-managers/{absent}').status_code != 404: absent -= 1
            call('Missing manager invalid FK', 'POST', '/api/rentals', 422, {**body,'managerId':absent})
            call('Missing manager detail', 'GET', f'/api/property-managers/{absent}', 404)
            update = {'listingTitle':'Updated HW5 Live Home', 'propertyAddress':body['propertyAddress'], 'availableUnits':3}
            updated, _ = call('Rental update', 'PUT', f'/api/rentals/{rid}', 200, update)
            for key in ['submitterEmail','description','propertyType','termsAccepted','managerId','listingCode','createdAt']:
                assert updated[key] == rental[key], f'Legacy field changed: {key}'
            assert updated['updatedAt'] >= rental['updatedAt']
            call('Rental delete', 'DELETE', f'/api/rentals/{rid}', 204); rentals.remove(rid)
            call('Deleted rental absent', 'GET', f'/api/rentals/{rid}', 404)
            call('Manager delete after child removed', 'DELETE', f'/api/property-managers/{mid}', 204); managers.remove(mid)
            call('Deleted manager absent', 'GET', f'/api/property-managers/{mid}', 404)
            for route in ['naive','fixed']:
                data, _ = call(f'Legacy performance {route} serialization', 'GET', f'/api/rentals/{route}?page_size=10&offset=0')
                assert all('listingCode' in row for row in data)
            result['pass'] = True
        finally:
            # These IDs were returned by this run's successful creates only.
            for rid in rentals: client.delete(f'/api/rentals/{rid}')
            for mid in managers: client.delete(f'/api/property-managers/{mid}')
            client.post('/api/auth/logout')
            result['finished_at'] = stamp()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2)+'\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
