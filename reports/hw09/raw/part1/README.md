# Part 1 — Rental view counter

Pragya Apurva · DATA 260 · SID4 6102

The live count comes from `X-View-Count` on the authenticated SQL rental detail
response. The response body keeps the existing rental JSON. Each listing has
its own `s6102:views:rental:<id>` key with no expiration. MySQL checkpoints at
multiples of ten and only advances its saved count.

A missing key starts from the latest saved count. If Redis loses the key after
read 25, the five views since the checkpoint at 20 are lost. A configured Redis
failure surfaces as a request error. A failure after Redis accepts an increment
may still leave that increment in Redis. After a failed MySQL checkpoint, the
next successful checkpoint catches up with the live count.

## Evidence

- [Live HTTP transcript](counter-run.log) and [machine-readable counts](counter-run.json)
- [FastAPI sync log](counter-server.log) and [labeled capture](counter-proof.png)
- [Short code excerpt](counter-snippet.md)

The capture shows the live terminal transcript and FastAPI log excerpts in
Chrome. The raw files preserve the complete output.

## Reproduce on isolated services

The live check used arm64 macOS, Python 3.12, MySQL 8.4.11, Redis 7.4.12, and
redis-py 6.4.0. Use dedicated
MySQL and Redis instances and a fresh HTTP port. The verifier creates three
synthetic listings and retains them and their counters for inspection. Supply
`HW4_DATABASE_URL` with database `s6102_rel`, `HW9_REDIS_URL`, `HW7_JWT_SECRET`,
and the HW7 reader and writer login pairs through an external private env file.
To seed teaching accounts, that file also needs the moderator login pair.

Install `requirements-hw09-part1.txt` in an external virtual environment. From
the repository root, export `PYTHONPATH=.:code`, load the private env file, then
prepare a fresh database and apply the numbered migration.

```bash
python scripts/hw05/part1/db_setup.py --create-database --migrate
python scripts/hw07/db_setup.py --env-file "$HW9_PRIVATE_ENV" --seed-accounts
python -c 'from scripts.hw04.db_setup import migrate; print(migrate(through=6))'
```

The existing SQL runner also applies the numbered 003 index if it is absent.
Apply 006 before starting the new application. Unset `HW9_REDIS_URL` to serve
the previous rental detail response without counting views. For a standalone
counter run, set the URL and start the app with `HW8_KAFKA_ENABLED=0`.

```bash
HW8_KAFKA_ENABLED=0 python -c 'import logging, uvicorn; logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s"); uvicorn.run("web_application.main:app", host="127.0.0.1", port=18706)'
```

From a second shell with the same private settings and an existing output
directory outside the worktree, run the verifier.

```bash
python -u scripts/hw09/verify_counter.py --base-url http://127.0.0.1:18706 \
  --output "$HW9_COUNTER_RUNTIME/counter-run.json"
```
