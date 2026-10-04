# Follow-up: reject optimized live evidence capture

The live verifier used Python assertions for its inventory, outcome, field, and privacy checks. Python `-O`, `-OO`, or `PYTHONOPTIMIZE` disables those assertions. The verifier now explicitly rejects disabled assertions at the start of `capture()`, before configuration lookup, filesystem receipt checks, or STDIO startup. `main()` catches that error and exits nonzero without writing a receipt or printing PASS.

The only implementation change is:

```python
if not __debug__:
    raise RuntimeError("Live STDIO verification requires enabled assertions.")
```

Tests use real optimized Python subprocesses for `-O`, `-OO`, `PYTHONOPTIMIZE=1`, and `PYTHONOPTIMIZE=2`. They require zero environment/STDIO access, no receipt, empty stdout, a safe diagnostic, and nonzero exit. Two ordinary-mode controls verify rejection of an empty inventory and a transport-error tool response; each proves it reached the intended failing response. These controlled doubles test the verifier and are not live database evidence.

Before the fix, the new regressions produced **4 failures and 2 passes**: each optimized mode accessed the environment before rejection. After the guard, the focused runtime/capture suite produced **9 passed in 4.90s**, with no failures or skips. [Test transcript](capture-guard-tests.txt).

The corrected code was then committed at `f21006d06d925c8062f58bf59811310da737aaaa`. On that clean revision, the [actual optimized CLI checks](../../raw/part3/review-fixes/capture-guard/optimization-rejections.json) used valid private configuration and the ready owned MySQL instance. All four exited **1**, wrote no receipt, and printed no PASS. The [ordinary live receipt](../../raw/part3/review-fixes/capture-guard/live-stdio.json) separately passed the unchanged 8 application outcomes and 3 native schema rejections. [Live transcript](capture-guard-live.txt).

Only the positively identified Part 3 MySQL3310 container was restarted. It was stopped afterward; its existing data/configuration were retained without reseeding or migration. [Cleanup receipt](../../raw/part3/review-fixes/capture-guard/cleanup.json).

The original selected 150-call rows, metrics, replay, timestamps, and evidence files remain byte-for-byte unchanged. The runtime and experiment sources are untouched, so the fault experiment was not rerun. Their original manifests still identify the historical tested revisions. [Follow-up provenance and preservation hashes](../../raw/part3/review-fixes/capture-guard/manifest.json).

Screenshots remain deferred; no capture was retried. Central U5/U6c verification against the upgraded schema remains coordinator-owned. This follow-up makes no claim that the whole homework is complete.
