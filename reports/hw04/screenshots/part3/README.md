# Part 3 Postman screenshot evidence

Status: **PENDING — six real Postman screenshots require manual Postman UI access.**

The owning session's native-app inventory and checks of `/Applications` and `~/Applications` found no available Postman UI. No screenshot has been synthesized, substituted with curl/Newman output, or counted as complete. The supplied [collection](../../part3/postman_collection.json) prepares the requests and assertions; importing or running it does not itself satisfy the screenshot requirement.

| Required primary file | Request at `https://localhost:8702` | Status |
| --- | --- | --- |
| `naive-10.png` | `GET /api/rentals/naive?page_size=10&offset=0` | PENDING |
| `fixed-10.png` | `GET /api/rentals/fixed?page_size=10&offset=0` | PENDING |
| `naive-50.png` | `GET /api/rentals/naive?page_size=50&offset=0` | PENDING |
| `fixed-50.png` | `GET /api/rentals/fixed?page_size=50&offset=0` | PENDING |
| `naive-200.png` | `GET /api/rentals/naive?page_size=200&offset=0` | PENDING |
| `fixed-200.png` | `GET /api/rentals/fixed?page_size=200&offset=0` | PENDING |

## Prepare the real capture session

1. Coordinate with Part 2 and Part 3 through the shared handoff before using port 8702. Do not send capture requests during the quiet 180-request benchmark. Use the dedicated Part 3 MySQL instance and its `s6102_rel` database with the verified 5,000 rentals and 200 managers. Do not seed or reset any database for this checklist. Record the server code revision, capture UTC timestamp, database instance identity without credentials, current listing-title index state, and Postman version in the Part 3 run log when capturing.
2. Start the agreed application at `https://localhost:8702` using the runtime owner's verified launcher/configuration. Confirm that the running application contains both Part 3 routes and the foundation authentication dependency. Use a trusted certificate valid for `localhost`. If the certificate uses a local CA, add its public PEM in Postman **Settings → Certificates → CA Certificates**. Keep SSL certificate verification enabled. Postman documents [custom CA setup](https://learning.postman.com/v11/docs/use/send-requests/authorization/certificates); no client private key is needed for this server-authentication setup.
3. Open the actual Postman desktop app, or the Postman web UI with its Desktop Agent configured to reach localhost, and import `reports/hw04/part3/postman_collection.json` from this worktree. This is a local functional collection run, not a cloud monitor or a Postman performance test.
4. Set `email` and `password` as private local values in the selected Postman environment. Do not share/sync their values or export the environment. They are intentionally unset in the committed collection. Keep `baseUrl` equal to `https://localhost:8702` and keep the cookie jar enabled. Postman can keep [local variable values private](https://learning.postman.com/v11/docs/use/send-requests/variables/share-variables).
5. Run the collection once with one iteration, in its listed order: login, naive 10, fixed 10, naive 50, fixed 50, naive 200, fixed 200. The login sends email/password as JSON. Postman receives `s6102_session` in its automatic cookie jar; do not manually add a Cookie or Authorization header, copy a token into a variable, export the cookie jar, or screenshot the login body or cookie panels. The [cookie jar](https://learning.postman.com/docs/use/send-requests/response-data/cookies/) sends the Secure cookie over HTTPS.
6. Inspect the test results. Each GET must return 200, a JSON array of the exact requested size, ascending positive rental IDs, populated `manager: {id, name}` objects, and numeric `X-SQL-Statements` and `X-Data-SQL-Statements` headers. Test names include the actual observed header values. No count is calculated from the requested page size. Each fixed request must also pass its paired-payload equality test. The first request in a pair reports equality as skipped until the counterpart is available; this is not a successful equality assertion.

The scripts use `pm.variables` to hold only the rental response arrays for the current normal collection run, so paired checks do not persist response data in exported collection/environment variables. Postman's [local-variable lifetime](https://learning.postman.com/docs/tests-and-scripts/write-scripts/postman-sandbox-reference/pm-variables/) is the current request or collection run. Sending two requests separately with **Send** does not establish that shared comparison context; use the full ordered Collection Runner run for equality. Keep the successful run available for inspection.

## Capture each endpoint and size

Repeat these steps for every row of the inventory table above. Keep the application and seeded data unchanged throughout the captures.

1. Select the named GET request. Confirm both query parameters in the URL or Params view. Click **Send** to make a real HTTP request; if the session has expired, send Login again and rerun the collection's equality checks before continuing.
2. Expand the response pane. Select **Body → Pretty → JSON** and show the start of the array, including at least one complete rental and its populated `manager` object. Keep the request name, full `https://localhost:8702/...` URL with `page_size` and `offset`, and response status **200 OK** visible. Capture the actual Postman window as that row's primary filename. The visible Postman response time is this individual capture request's timing.
3. In the same response, open **Headers** and show the actual `X-SQL-Statements` and `X-Data-SQL-Statements` rows. If the Postman layout cannot show these with the JSON body, take a supporting screenshot named `<version>-<size>-headers.png` (for example, `naive-10-headers.png`). Keep the request URL and 200 status visible. Do not expose the request Cookie header, login `Set-Cookie`, or cookie manager.
4. Open **Test Results** and show the passing exact-row-count test and the two SQL-header tests, whose names contain the actual observed values. If they cannot fit alongside the body and headers, take `<version>-<size>-tests.png`. Keep the request name/URL and status visible. Retain the Collection Runner view showing the successful three fixed-request equality tests as an optional `payload-equality.png` supporting screenshot.
5. Save the unaltered screenshots in this directory. Primary body captures plus any required supporting headers/tests captures must let a reviewer see the endpoint/version, page size, status, returned manager data, row-count validation and observed query counts. Do not create composites, replace values, paste benchmark counts into a screenshot, or present a script-generated page as Postman.
6. Review each image for readability and secrets before committing. Update only the relevant inventory row from PENDING to CAPTURED after the real primary image and its required support exist. Add timestamp, code revision and filenames to the run log. Keep failed responses separately with a clear failed-attempt label; they do not satisfy a successful screenshot slot.

The six primary images are the required endpoint/size evidence. Supporting header/test images are additionally needed whenever the UI cannot display all relevant panels at once; their capture is currently pending too. A screenshot of a successful Collection Runner summary alone does not replace the six endpoint response screenshots.

## Separation from benchmark measurements

The collection sends one functional request per endpoint/size after login, and manual captures send additional requests. These requests are **outside** the selected 180-request timing dataset. Never append their timings to its CSV or use their displayed times to replace its p50/p95/p99 values. The selected run's raw rows, measured revision, configuration and metrics remain the benchmark evidence. Record the screenshot capture's own revision and index state, particularly when capturing after the index experiment or a later integration merge.
