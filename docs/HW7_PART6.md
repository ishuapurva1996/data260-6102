# HW7 Part 6 file-tool demonstration

`src/course_files` is an opt-in course capability. It does not change rental,
bike-share, authentication or web tool permissions. Its gate is standard-library
Python and can be imported without a model. The optional discovery demo reuses
the pinned Part 4 environment and unchanged HW1 adapter.

Create a fresh private temporary course directory, then use `FileTools(root)` as
a context manager. No default project root is supplied. All repository tests and
the combined demonstration use new temporary directories outside Git. Paths are
relative, traversal is rejected, and descriptor-relative opens reject symlink
components, special files and multiply linked files. The trusted caller chooses
the root; this is not an operating-system security boundary against a hostile
process already running as the same user.

The six methods return timestamped `success/data/error/source/ts` envelopes:

- `read_file(path, max_lines=200)` returns UTF-8 text and a truncation flag.
- `write_file(path, content)` writes bounded text, creating relative parents.
  It prepares and syncs a uniquely created sibling, then atomically replaces the
  target; failed writes preserve existing bytes and remove the candidate.
- `edit_file(path, old, new)` requires one exact match, checks for a changed file,
  and returns a short unified diff.
- `glob_files(pattern='*.py')` returns sorted relative regular-file names.
- `search_in_files(query, file_pattern='*.py')` uses literal substring search.
- `bash(command, auto_approve=False)` gates and executes only the grammar below.

Glob filters use `fnmatch` over the complete relative path; `*.py` includes nested
Python paths. All symlinks in a scanned tree are rejected. Files are limited to
65,536 bytes, scans to 100 files/eight directory levels/three seconds, searches to
50 matches, and read requests to 1–1,000 lines. Diffs show at most 30 lines/4,000
characters. This is a bounded text-file exercise, not a general filesystem API.

`SAFE_PREFIXES` contains `pwd`, `ls`, `python --version`, `head -n` and `rg`.
Matching is by tokens followed by full argument validation. The supported forms
are exactly `pwd`, `ls`, `python --version`, `head -n N relative_file` (N≤200), and
`rg literal --glob relative_pattern .`. Shell chains, substitutions, redirections,
environment assignments, interpreter code execution and other forms are rejected.
Destructive classification runs independently of prefix matching and auto-approval.
Within the complete supported read-only grammar, query/path operands are literal
data; searching for `sudo` or `chmod` does not execute either command.

`confirmed_command` is a trusted-Python-only input to the pure `confirm_bash`
decision. A caller may supply it only after explicit human confirmation of that
exact command. Tests exercise matching/mismatched confirmation as strings only.
It is not a model argument, and `FileTools.bash` exposes no confirmation bypass:
the course executor never executes destructive commands.

Allowed commands use absolute executable paths, `shell=False`, a minimal child
environment, a sandbox directory descriptor, and a three-second/16,384-byte bound.
`head` reads a validated open file descriptor. `rg` performs fixed-string searches
on validated file descriptors through stdin, preserving the requested file filter.
No unvalidated filesystem operand reaches either program. Child process groups
are killed on time/output limits. This POSIX runner is intended for the sequential
course CLI; its `fchdir` pre-exec hook is not a general multithreaded web service.

After implementation is reviewed and committed:

```sh
python scripts/hw07/file_demo.py --freeze reports/hw07/raw/part6/freeze.json
python scripts/hw07/file_demo.py --freeze reports/hw07/raw/part6/freeze.json \
  --run --output /absolute/external/part6/final \
  --runtime-dir /absolute/private/shared-runtime
```

The supervisor permits 260 seconds. The discovery agent uses at most five model
requests, six tool calls, 16,000 charged tokens and 240 seconds. It exposes only
glob/search/read, requires an initial `*.py` glob and a `DEBUG`/`*.py` search,
requires observations between calls, and checks the read path
against the actual unique search match. The final answer must reproduce the
observed path and contents. Controlled-response tests are separate from this
genuine local-model run.

The fixed matrix and three input files are in `reports/hw07/cases`. The combined
run writes actual traces, raw model output, gate reasons, safe-command outputs,
edit/truncation/filter checks, timestamps and source/configuration metadata. Even
a false allow on an expected-block case is retained without executing that string.
Temporary course files are removed when the run ends; frozen cases reproduce them.
