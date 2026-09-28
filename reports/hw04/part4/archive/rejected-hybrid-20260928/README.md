# Rejected hybrid-retrieval experiment — historical archive

This experiment is not used by the selected `scored-20260928-04` dense-retrieval pipeline. It combined dense and BM25 ranks with reciprocal-rank fusion and was rejected after development testing. No historical result was removed or rescored.

- **Exact implementation:** reuse the [existing scored04 frozen helper](../../../raw/part4/scored-20260928-04/frozen/src/rag/hybrid.py). Its bytes match the former live `src/rag/hybrid.py`; no duplicate implementation was created. The adjacent frozen `runner.py` preserves the original integration and snapshot list.
- **Exact dedicated tests:** [test_hw04_rag_hybrid.py.txt](test_hw04_rag_hybrid.py.txt). No earlier test snapshot existed. The `.txt` extension prevents active pytest collection; its content is unchanged Python source. It contains nine parametrized test cases.
- **Proof:** [manifest.json](manifest.json) records the original paths, archived paths, byte sizes and SHA-256 hashes. Both matches were verified before removing the live files.
- **Historical verification:** [65 passing pre-cleanup tests](../../../raw/part4/followup-setup-20260928/tests-focused-final.txt) include the nine rejected-helper tests. This remains a historical result, not the current suite count.

For historical research only, the helper and tests can be copied to their original relative paths inside a separate temporary checkout. Do not restore them into the current dense pipeline or modify the immutable selected run to use them. Current instructions and cleanup receipts are in [HANDOFF.md](../../HANDOFF.md).
