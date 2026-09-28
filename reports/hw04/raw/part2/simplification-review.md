# Backend simplification review

Three independent lenses completed: reuse, quality and efficiency. Scope was the new Part2 backend plus setup/acceptance/launcher scripts. One change applied: reuse the same unknown-route response in acceptance.py, removing a redundant HTTP request.

Small optional proposals were deferred to preserve the published foundation for dependent branches: reuse the identical UTC helper; consolidate repeated no-store headers; reuse idle constant; remove launcher environment copy; replace seed COUNT with LIMIT; pass index file stat to FileResponse. These were not correctness defects. No auth/schema/API behavior changed afterB in this pass.

Verification after harness change: four partial-verifier negative tests passed; the prior authoritative backend run passed122. The complete acceptance rerun remains part of final integration, where the harness will exercise the current merged revision. Subsequent correctness-review fixes are tracked separately; the expanded reviewed suite passed 130 tests.
