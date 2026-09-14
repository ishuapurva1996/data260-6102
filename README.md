# DATA 260 assignment submissions

This repository contains the submission code, reports, and supporting evidence for DATA 260 (SID4 `6102`). Each assignment has its own directory.

- [HW1](HW1/README.md): Rental Housing Listings web application, agent pipeline, non-determinism experiment, model client, and completed report. Run its commands from `HW1/` as described in its README.
- [HW2](HW2/Rental%20Housing%20App/index.html): Part 1 rental application with a 375px layout and visible loading, empty, and error states.

To serve HW2 from the repository root:

```bash
python3 -m http.server 8702 --bind 127.0.0.1 --directory "HW2/Rental Housing App"
```

Open [the application](http://127.0.0.1:8702/), [the eight-second loading demo](http://127.0.0.1:8702/?slowSave=true), or [the controlled save-error demo](http://127.0.0.1:8702/?simulateError=true). Stop the server with `Control-C`. HW1 also uses port 8702, so stop its container before starting this server.

The historical Git tag `hw1` preserves the original HW1 submission and its earlier repository layout. The current checkout groups those files under `HW1/`; the submitted report and recorded logs retain their original contents and historical paths.

Course instructions, standalone practice scripts, and agent working notes are kept outside this repository, under the sibling `HW1 assignment instructions/` and `HW2/agent_outputs/` directories in `DATA 260/`. The screenshot evidence plan is in that external `HW2/agent_outputs/` directory.
