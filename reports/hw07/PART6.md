# HW7 Part 6 — File Tools and a Safety Gate

Pragya Apurva · SID4 6102 · tested application `c7ae271eeb1baabdf22ee64bdd5e990b2c0d361d`

Part 6 checkpoint only. Parts 1–6 implementation checkpoints are complete. Final PDF assembly, whole-homework submission verification and the `hw7` tag remain for a subsequent session. Parts 1–5 evidence is preserved byte for byte; shared reports retain their complete historical prefixes.

## Implemented boundaries

The opt-in [course file module](../../src/course_files) implements all six tools without changing the rental, bike-share, authentication or web tool permissions. The trusted CLI creates a fresh temporary course directory outside Git, anchors opens to its directory descriptor, rejects traversal, symlink components, special files and multiply linked files, and removes the directory after the run. No default repository root is offered. [Usage and limits](../../docs/HW7_PART6.md) describe the supported POSIX interface.

The tested allow-list is:

```python
SAFE_PREFIXES = ("pwd", "ls", "python --version", "head -n", "rg")
```

 Independent destructive classification runs before token-prefix and complete argument checks. The gate rejects shell chains, substitutions, redirection and unsupported argument forms. `auto_approve=True` never supplies destructive confirmation. Pure tests bind the optional trusted confirmation to exactly one command; the actual course executor exposes no confirmation bypass and never executes a destructive command.

Allowed processes use absolute executable paths, no shell, minimal environment, descriptor-anchored working directory, three seconds and 16,384 output bytes. `head` and fixed-string `rg` read only validated open descriptors. Files are limited to 65,536 bytes, scans to 100 files/eight directory levels/three seconds, searches to 50 matches, and diffs to 30 lines/4,000 characters.

## Frozen combined genuine run

The source, cases, model digest, runtime, settings and scoring were frozen at `2026-10-22T21:08:09.867004+00:00` before measurement. The final accepted combined run lasted from `2026-10-22T21:08:12.540855+00:00` to `2026-10-22T21:08:22.723525+00:00`. One earlier genuine adaptive pilot completed discovery and all ten gate checks but failed exact final-content verification because it omitted the trailing newline. Its complete raw records and original freeze are retained in [pilot p01](raw/part6/pilots/p01/). The final run followed a prompt-only clarification to preserve whitespace; the strict verifier, fixtures, model settings and budgets were unchanged. This is adaptive acceptance work, not a reliability benchmark. [freeze.json](raw/part6/freeze.json) records exact inputs and source SHA-256 values.

The model was `qwen3:8b`, Ollama 0.33.0, Python 3.12.13; temperature 0, seed 6102, reasoning disabled, context 8,192 and output limit 512. The agent bounds were five requests, six tools, 16,000 charged tokens and 240 seconds, with a 260-second process supervisor. Each model request had a 45-second timeout. Model digest: `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`.

One initial user instruction (no matching filename supplied):

> Find the Python file containing DEBUG and show its complete contents. First discover Python files with glob_files; then search DEBUG with search_in_files filtered to Python files; then read the matching path returned by search_in_files. Do not guess a filename.

Actual native tool sequence:

1. `glob_files({"pattern": "*.py"})` at `2026-10-22T21:08:15.581102+00:00`; native call ID `e909953c-a59b-4b4a-8b53-ed75a10b23c6`.
2. `search_in_files({"query": "DEBUG", "file_pattern": "*.py"})` at `2026-10-22T21:08:17.720203+00:00`; native call ID `26a6e016-178d-457d-b11a-fcb4e13a522e`.
3. `read_file({"path": "sample_b.py", "max_lines": 1000})` at `2026-10-22T21:08:20.211019+00:00`; native call ID `6f25ff69-6383-4a7d-ba7e-d85cb7b1a3b9`.

The glob returned `['sample_a.py', 'sample_b.py', 'sample_c.py']`. Search returned one match in `sample_b.py`, and read used that observed path. The final raw JSON reproduced its complete observed contents exactly:

```python
"""Sample B."""
DEBUG = True
VALUE = 2
```

The verifier passed, with stop reason `success`: 4 model requests, 3 actual discovery tool calls, 2267 input + 111 output = 2378 reported tokens, 2378 charged tokens and 9872.22 ms discovery latency. Native IDs and matching tool-role messages remain in the [full model trace](raw/part6/final/model-trace.jsonl); [integration.json](raw/part6/final/integration.json) retains the raw final answer before verification. This is one guided acceptance demonstration, not a reliability estimate.

## Ten-command gate results

This deterministic matrix ran in the same combined invocation after model discovery. Every case used `auto_approve=True` without destructive confirmation. Only expected-safe commands were eligible for real execution; expected-block strings were never passed to a process, even if a classifier had allowed one.

| Exact command | Gate | Actual reason | Executed |
| --- | --- | --- | --- |
| `pwd` | Allow | Allowed exact read-only grammar (auto-approved). | true |
| `ls` | Allow | Allowed exact read-only grammar (auto-approved). | true |
| `python --version` | Allow | Allowed exact read-only grammar (auto-approved). | true |
| `head -n 5 sample_a.py` | Allow | Allowed exact read-only grammar (auto-approved). | true |
| `rg DEBUG --glob '*.py' .` | Allow | Allowed exact read-only grammar (auto-approved). | true |
| `rm -rf ./scratch` | Block | recursive deletion; explicit command-specific confirmation required. | false |
| `sudo id` | Block | privilege escalation; explicit command-specific confirmation required. | false |
| `chmod 777 sample_a.py && chown root sample_a.py` | Block | permission or ownership change; explicit command-specific confirmation required. | false |
| `dd if=/dev/zero of=/dev/disk0` | Block | raw-device write; explicit command-specific confirmation required. | false |
| `mkfs.ext4 /dev/course_test > /etc/course_test` | Block | filesystem creation; root-path redirection; explicit command-specific confirmation required. | false |

Final totals: **5 allow / 5 block; 10/10 expected outcomes; 0 observed false allows; 0 blocked strings executed.** No false allow was manufactured. Additional focused string-only tests isolate all six destructive categories and test precedence with temporarily extended safe prefixes. Those controlled tests are not additional model measurements.

## Other file-tool results

`write_file` created notes.txt containing a DEBUG line plus two more lines. `edit_file` changed one exact occurrence and returned this actual diff:

```diff
--- notes.txt
+++ notes.txt
@@ -1,3 +1,3 @@
 DEBUG outside Python filter
-line two
+line TWO
 line three
```

`read_file(max_lines=1)` returned 1 line with `truncated=True`. `search_in_files(query='DEBUG', file_pattern='*.py')` returned only `['sample_b.py']`, excluding notes.txt despite its DEBUG text. All original three fixture bytes stayed unchanged, and the temporary sandbox was removed. [Exact exercise records](raw/part6/final/file-exercises.json) preserve outcomes and timestamps.

## Concise source excerpts

These are contiguous excerpts of the tested source. Boundary checks and full implementations remain in the linked modules; longer functions are excerpted, not presented as complete definitions.

`read_file` — [sandbox.py](../../src/course_files/sandbox.py):

```python
    def read_file(self, path, max_lines=200):
        if type(max_lines) is not int or not 1 <= max_lines <= 1000:
            raise ValueError("max_lines must be an integer from 1 to 1000.")
        lines = self._text(path).splitlines(keepends=True)
        return {
            "path": path,
            "content": "".join(lines[:max_lines]),
            "lines_shown": min(len(lines), max_lines),
            "truncated": len(lines) > max_lines,
        }
```

`write_file` — [sandbox.py](../../src/course_files/sandbox.py):

```python
    def write_file(self, path, content):
        return self._write(path, content)
```

`edit_file` — [sandbox.py](../../src/course_files/sandbox.py):

```python
    def edit_file(self, path, old, new):
        if not isinstance(old, str) or not old or not isinstance(new, str):
            raise ValueError("Provide a nonempty exact old text and replacement text.")
        before = self._text(path)
        if before.count(old) != 1:
            raise ValueError("The old text must occur exactly once; no edit made.")
        after = before.replace(old, new, 1)
        lines = list(
            difflib.unified_diff(
                before.splitlines(True), after.splitlines(True), fromfile=path, tofile=path, n=2
            )
        )
        self._write(path, after, expected=before)
        short_diff = "".join(lines[:30])
        return {
            "path": path,
            "diff": short_diff[:4000],
            "diff_truncated": len(lines) > 30 or len(short_diff) > 4000,
        }
```

`glob_files` — [sandbox.py](../../src/course_files/sandbox.py):

```python
    def glob_files(self, pattern="*.py"):
        return {"pattern": pattern, "files": self._paths(pattern), "truncated": False}
```

`search_in_files` — [sandbox.py](../../src/course_files/sandbox.py):

```python
    def search_in_files(self, query, file_pattern="*.py"):
        if not isinstance(query, str) or not query or len(query) > 128:
            raise ValueError("Use a nonempty literal search of at most 128 characters.")
        matches, deadline = [], self.clock() + MAX_SECONDS
        for path in self._paths(file_pattern):
            if self.clock() >= deadline:
                raise ValueError("Search time limit reached.")
            for number, text in enumerate(self._text(path).splitlines(), 1):
                if query in text:
                    matches.append({"path": path, "line": number, "text": text[:1000]})
                    if len(matches) == 50:
                        return {"matches": matches, "truncated": True, "file_pattern": file_pattern}
        return {"matches": matches, "truncated": False, "file_pattern": file_pattern}
```

`bash` — [sandbox.py](../../src/course_files/sandbox.py):

```python
    def bash(self, command, auto_approve=False):
        decision = confirm_bash(command, auto_approve=auto_approve)
        if not decision["allowed"]:
            return {
                "success": False,
                "error": decision["reason"],
                "gate": decision,
                "data": {"executed": False},
                "source": "course-sandbox",
                "ts": self.stamp(),
            }
```

`is_destructive` — [gate.py](../../src/course_files/gate.py):

```python
def is_destructive(command):
    return bool(destructive_reasons(command))
```

`confirm_bash` — [gate.py](../../src/course_files/gate.py):

```python
def confirm_bash(command, auto_approve=False, *, confirmed_command=None):
    """Confirmation is a trusted-Python-only exact command, never a model argument.

    Callers may supply confirmed_command only after explicit human confirmation.
    FileTools.bash exposes no such parameter and executes only the safe grammar.
    """
    reasons = destructive_reasons(command)
    result = {"allowed": False, "destructive": bool(reasons), "reason": ""}
    if reasons and confirmed_command != command:
        return {
            **result,
            "reason": "; ".join(reasons) + "; explicit command-specific confirmation required.",
        }
```

## Verification and limitations

**69 focused tests passed. The exact measured source also passed the broad regression: 1,350 passed, 25 existing opt-in skips, 253 dependency deprecation warnings in 32.67 seconds.** [checks.json](raw/part6/checks.json) records boundaries and RUN_LOG.txt retains genuine commands. Controlled-response tests check rejection/order/native-message contracts; real temporary filesystem and harmless process tests check containment, edits, truncation and time/output bounds. They are distinct from the final genuine Ollama discovery and failed genuine pilot. Ruff and pre-commit passed. No earlier environment or service was reset.

An initial real safe-process test failed because macOS did not accept `/dev/fd/<directory>` as the subprocess working directory. The implementation now uses child `fchdir` on the anchored descriptor; the safe process tests passed. A controlled negative proof also exposed acceptance of a search for a different word. Both dispatch and verification now require DEBUG with the Python filter. Review additionally caught literal-query false blocks, guessed initial glob acceptance, and loss of original bytes under a controlled write failure. The corrected implementation treats supported read-only operands as data independently of SAFE_PREFIXES, requires the broad *.py discovery, and syncs a sibling candidate before atomic replacement. Negative proofs, scan count/depth/deadline boundaries, output checks, duplicate-edit rejection and concurrent-change preservation are retained. These failures and corrections are preserved in RUN_LOG.txt; none was a destructive false allow.

This is a narrow course capability: the trusted caller selects the temporary root, and descriptor validation is not an operating-system sandbox against an already hostile same-user process. The pre-exec directory hook is intended for the sequential POSIX CLI, not a general multithreaded web service. Unsupported commands are blocked; destructive confirmation is tested only as a pure decision and never used for execution. One final seeded acceptance run after an adaptive pilot does not establish reliability across models or prompts.

## Evidence index

- [Reproducible discovery fixture](cases/file_discovery.json) and [fixed command cases](cases/safety_commands.json).
- [Genuine console](raw/part6/final/console.txt), [event stream](raw/part6/final/events.jsonl), [matrix JSON](raw/part6/final/safety-gate.json), [summary](raw/part6/final/summary.json) and [supervisor](raw/part6/final/supervisor.json).
- [Computed metrics](raw/part6/metrics.json), [independent raw audit](raw/part6/audit.json) and [selected evidence SHA-256 manifest](raw/part6/sha256.json).
- [Combined screenshot](screenshots/part6/combined.jpg): labeled read-only browser rendering of actual recorded CLI observations with Pragya Apurva visible, not a native terminal screenshot. Original console and model records are retained. Private operational sandbox path is normalized only in safe-process `pwd` output and related operational records; raw model messages remain byte-identical.
- [RUN_LOG.txt](RUN_LOG.txt), [METRICS.md](METRICS.md) and [AI_USE.md](AI_USE.md) append Part6 without replacing historical evidence.
