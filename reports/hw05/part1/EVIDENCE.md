# Part 1 evidence — Pragya Apurva

Code and live verification are complete. Required evidence is **incomplete**: genuine Postman action/error screenshots and a database-client screenshot remain. The available computer-use surface exposed browser tabs but no native Postman or database-client control. No fabricated GUI evidence is included.

Configuration: Rental Housing Listings; `SID4=6102`, `PORT_BASE=8702`, `PREFIX=s6102`, `SEED=6102`, `VERIFY_SEED=266102`, `DOMAIN_ID=6`; MySQL database `s6102_rel`. The owned MySQL instance used port 3307 and the HTTPS application used port 8702; migration tests used disposable MySQL port 3309.

| Requirement | Selected evidence | Actual outcome |
| --- | --- | --- |
| R3 / U1: schema, related entities, constraints | `../raw/part1/database.json`, `migration-tests.xml`, `preservation.json` | 11 migration tests passed; populated upgrade, reruns and interrupted resumes; original fields, associations, auth rows and indexes preserved |
| R4 / U1: authenticated CRUD, lists, relationship, errors | `../raw/part1/backend-tests.xml`, `live-api.json` | 160 backend/regression tests and 25 real HTTPS checks passed; 201/200/204/404/409/422, pagination and RESTRICT tested |
| Persistence and secure sessions | `../raw/part1/restart.json` | Same record and secure-cookie login survived a real app-process restart |
| R5 / U2: Redux/Axios CRUD | `../raw/part1/browser-real.json` | Seven real HTTPS/MySQL browser checks passed, including create, direct-ID update, per-row delete, reload, pagination and logout |
| R5 / U2: loading/errors/races | `../raw/part1/browser-mock.json` | 16 controlled browser scenarios passed; includes invalid input, manager loading failure, duplicate submissions, stale responses, stale 401 and auth expiry. Mock responses prove UI behavior only |
| Build and dependencies | `RUN_LOG.txt`, `../raw/part1/runs.json` | `pip check`, `npm ci`, production build passed |
| R6: four Redux frames | `../screenshots/part1/redux-home.png`, `redux-create.png`, `redux-update.png`, `redux-delete.png` | Exactly four genuine single browser captures: repository thunk source above the corresponding live UI result |
| R6: Postman CRUD/relationship/errors | `../raw/part1/postman_collection.json` | Reproducible inputs/assertions prepared; Postman execution and captures pending |
| R6: database screenshot | `../raw/part1/database_checks.sql`, `database.json` | Actual SQL output retained; required GUI screenshot pending |

All final tests passed with zero skips. Existing dependency deprecation warnings remain. `npm ci` reported two moderate audit findings in the existing React Router 6 dependency family; the suggested remediation requires a major router upgrade. No forced major upgrade was applied in this Part 1 change.

## Screenshot provenance

`../raw/part1/redux-captures.json` records UTC capture times, actual app URL, source hashes and screenshot hashes. The source viewer reads repository files and embeds the running HTTPS application. It performs real create/update/delete actions without response interception. Each PNG is the unchanged output of one browser screenshot; no images were combined or reconstructed. The viewer is temporary and is not an application route. The created test record was deleted.

Tests and captures ran before the local commits. Their logs retain the then-current HEAD. `../raw/part1/provenance.json` records the resulting code commits and verifies that the browser/capture source hashes match the committed source. Ordinary diagnostic screenshots referenced by raw browser receipts remain external and are not selected submission frames. No terminal screenshots were selected.

## Pending genuine captures

1. Start the owned MySQL 3307 and HTTPS 8702 application using private local configuration. Import the collection in actual Postman, configure the localhost CA and private email/password environment, and send request 00 to log in. Keep passwords and cookie headers out of images.
2. Capture the eleven actions numbered 01–09, 15 and 17: manager create/list/detail/update; rental create/list/detail/update; manager-related rentals; rental delete; manager delete. Show method/URL, relevant input, response status/body, and list pagination plus `X-Total-Count`.
3. Capture meaningful failures from 10–14 and 16/18: referenced-manager conflict, duplicate email/code, negative units, invalid listing code and absent records. Preserve collection order.
4. In a genuine database client, connect to owned port 3307, select `s6102_rel`, and run `database_checks.sql`. Capture the selected database, both tables, representative related rows, and unique/FK/check constraints. If using terminal evidence, print `Pragya Apurva` in that terminal before capture.
5. Add selected images and actual capture metadata, then update this status after review. API JSON and this collection are not substitutes for Postman screenshots.

## Interpretation and cleanup

Legacy manager emails are synthetic `legacy-manager-<id>@example.com`; company is `Legacy import`. Historical timestamps are the recorded UTC upgrade time, not reconstructed original dates. The populated baseline was an owned test fixture, not a copy of someone else's production database.

`../raw/part1/shutdown.json` confirms only this session's HTTPS process and two MySQL containers were stopped. Data and containers were retained; ports 8702/3307/3309 are free. Final application data contains the original 55 rentals and 2 managers. Other sessions' services were untouched. Parts 2–5, shared final documents, final report, verifier and tags remain outside this session's scope.
