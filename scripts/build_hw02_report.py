"""Build the HW2 PDF and editable Markdown from source and saved evidence.

Uses ReportLab and Pillow. Does not run experiments or change application code.
Run with --code-ref hw2-code after freezing the verified implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import subprocess
import textwrap
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/hw02"
W, H = A4
MARGIN = 40
WIDTH = W - 2 * MARGIN
NAVY = colors.HexColor("#17354d")
TEAL = colors.HexColor("#167d8d")
GRAY = colors.HexColor("#52606b")
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=14, textColor=NAVY)
CAPTION = ParagraphStyle("caption", parent=BODY, fontSize=8.2, leading=11, textColor=GRAY)


def read(relative):
    return (ROOT / relative).read_text()


def lines(path, start, end):
    source = read(path).splitlines()
    return (f"{path} | lines {start}-{end}", "\n".join(source[start - 1:end]))


def function(path, name):
    source = read(path).splitlines()
    start = next(i for i, line in enumerate(source) if line.startswith(f"def {name}("))
    end = next((i for i in range(start + 1, len(source)) if source[i].startswith("def ")), len(source))
    return lines(path, start + 1, end)


def page(title, text, code=(), pictures=(), caption="", table=None):
    return dict(title=title, text=text, code=list(code), pictures=list(pictures), caption=caption, table=table)


def pages(code_ref, commit):
    web = "code/web_application/"
    js = web + "static/app.js"
    css = web + "static/styles.css"
    backend = web + "main.py"
    graph = "src/agent_graph/"
    shot = "reports/hw02/screenshots/"
    panels = shot + "final-panels/"
    p = []
    p.append(page("Homework 2 | Rental Housing Listings", [
        "Pragya Apurva | DATA 260 | September 14, 2026",
        "This report extends the HW1 rental project with a responsive web interface, a FastAPI backend, and a Planner-Reviewer graph with strict output checks and bounded retries.",
        f"Verified implementation tag: {code_ref}<br/>Tagged commit: {commit}",
        'Repository: <link href="https://github.com/ishuapurva1996/data260-6102" color="#167d8d">https://github.com/ishuapurva1996/data260-6102</link>',
        "Hardware: MacBook Air, Apple M4 (10 CPU cores), 24 GB memory; macOS 15.7.4, arm64. Python 3.12.14. Local model: qwen3:1.7b through Ollama 0.33.0.",
        "The same documented HW1 model substitute is retained: the qwen3:8b download did not complete reliably. All measured model calls use the shared src/model_client.py adapter.",
        "The code tag identifies the tested implementation. The generated PDF and verification result are accompanying artifacts produced after that code freeze; their own hashes are in the submission manifest.",
    ], table=[
        ["Personal configuration", "Value", "Calculation / meaning"],
        ["SID4", "6102", "Last four student-ID digits"],
        ["PORT_BASE", "8702", "8000 + (6102 mod 900) = 8000 + 702"],
        ["PREFIX", "s6102", '"s" + SID4'],
        ["SEED", "6102", "SID4"],
        ["VERIFY_SEED", "266102", "260000 + SID4"],
        ["DOMAIN_ID", "6", "6102 mod 8; rental housing"],
    ]))
    p.append(page("Project structure and evidence", [
        "The browser interface and FastAPI manage rental records. Separately, the command-line agent graph reads a rental description and proposes three tags and a short summary. The parts share the rental domain and repository, but the graph is not automatically called when a user saves a listing.",
        "All runnable application code remains in the shared root-level code/ and src/ folders. Homework-specific reports, inputs, recorded runs and screenshots are in reports/hw02/. The raw campaign's sources/ directory contains audit snapshots, not another application to run.",
        "The rental's primary field is Listing Title; its secondary field is Address. Creation also collects email, description, property type and accepted terms. The server assigns IDs. A server restart restores two seed records; a browser reload preserves the current in-memory records.",
        "Evidence types are labeled throughout: actual browser UI captures; browser screenshots of saved console/JSON/tables; real local-model experiments; and deterministic tests using scripted responses. A scripted repair check is not counted as a successful model trial.",
        "Part 1 images are original 375 x 812 screenshots. The capture manifest records innerWidth = document scrollWidth = body scrollWidth = 375. The images contain page content; the viewport measurements are recorded separately.",
        "The repeatable CRUD capture used an isolated instance on port 18702 to preserve the existing app's data. A separate read-only capture and live smoke check confirm that the required app responds on port 8702. The submitted startup command uses 8702.",
        "The repository web link was opened successfully on September 14. GitHub required identity confirmation before showing collaborator settings; access for Sbnikitha and supriyaselvanganesan still needs confirmation. The HW2 work is on the codex/fix-hw1-form branch; a direct link is provided on the last page.",
    ], table=[
        ["Requirement", "Where to find the evidence"],
        ["Parts 1-2", "screenshots/part1, screenshots/part2, raw/part12"],
        ["Part 3 graph", "src/agent_graph, code/agents_graph.py; current smoke output"],
        ["Part 4 experiments", "raw/part4/20260914T0610-baseline; METRICS.md"],
        ["Reproduction / verification", "REPRODUCIBLE_RUN_INSTRUCTIONS.md; verification.json"],
    ]))
    p.append(page("Part 1 | Form at 375px", [
        "The form scales to the available width, and its controls stay inside the page. The two scrolled views below show the same filled form, including the description, property type, terms and submit button."
    ], code=[lines(web + "static/index.html", 5, 7), lines(css, 77, 89)], pictures=[shot + "part1/P1-02a-form-upper.png", shot + "part1/P1-02b-form-lower.png"], caption="Actual UI, 375 x 812 viewport per image. The long email is in a single-line input; wrapping is demonstrated in the listing card on the next page."))
    p.append(page("Part 1 | Readable list and usable editor", [
        "Long card text wraps rather than widening the page. Each listing offers Edit and Delete. Edit opens a shared form with that listing's ID, title and address; it is usable at the same 375px width. At widths of 600px or less, the mobile rule stacks the buttons vertically."
    ], code=[lines(css, 255, 263), lines(css, 321, 323)], pictures=[shot + "part1/P1-04-list.png", shot + "part1/P1-05-editor.png"], caption="Actual UI at 375px. Both the record and editor fit without horizontal overflow. Editing any listing is an extra convenience; Part 2 still demonstrates ID 1 as requested."))
    p.append(page("Part 1 | Empty state", [
        "After both seed records are deleted, the UI explicitly reports that there are no rentals. A zero-result search is handled separately because it can occur while records still exist."
    ], code=[lines(js, 168, 176)], pictures=[shot + "part1/P1-01-empty.png"], caption="Actual empty store at 375 x 812: 0 listings, disabled highest-ID action, and a clear message inviting the first record."))
    p.append(page("Part 1 | Loading state", [
        "During a save, the UI shows progress and disables competing controls. The optional slowSave flag waits eight seconds before sending a real POST, making the state easy to capture. It is a demonstration delay, not the server's normal response time."
    ], code=[lines(js, 237, 241), lines(js, 267, 271)], pictures=[shot + "part1/P1-03-loading.png"], caption="Actual 375px UI while the controlled delay is active. The save then succeeded; observed browser completion was 8573 ms including the deliberate wait."))
    p.append(page("Part 1 | Error and retained input", [
        "The controlled simulateError mode fails after about two seconds. It shows a red error, retains input and restores the controls. No POST is sent in this mode, so it is not presented as a backend rejection."
    ], code=[lines(js, 267, 274), lines(js, 246, 251)], pictures=[shot + "part1/P1-06-error.png", shot + "part1/P1-06b-retained-upper.png"], caption="Actual UI at 375px, captured before further typing cleared the error. The stored record count did not change."))
    p.append(page("Part 2 | FastAPI on the required port", [
        "FastAPI serves the home page, static assets and rental API. Running python code/web_application/main.py starts a single worker on 127.0.0.1:8702. The screenshot below is from that existing port, observed without changing its records."
    ], code=[lines(backend, 16, 17), lines(backend, 139, 145)], pictures=[shot + "part2/P2-00-port8702-readonly.png"], caption="Actual UI from port 8702; GET / and GET /api/rentals returned 200. Detailed requests and timestamps are in raw/part12/port8702-readonly.json."))
    p.append(page("Part 2 | Requests and return to home", [
        "The browser sends JSON to the API. After a successful create, update or delete, this shared helper navigates back to /. The refreshed list then comes from the server. On failure it keeps the form available for correction or retry.",
        "The API returns 201 for creation, 200 for update and 204 with no body for deletion. JavaScript sends the browser back to home after the API succeeds. Search updates the list without a full page navigation.",
        "For the following sequence, an isolated server started with IDs 1 and 2. Creation added ID 3; the update changed only ID 1; highest-ID deletion removed ID 3; then title and address searches ran against the two remaining records."
    ], code=[lines(js, 237, 251), lines(js, 253, 266)], table=[
        ["Route", "Observed result"],
        ["POST /api/rentals", "201; new ID 3 persisted"],
        ["PUT /api/rentals/1", "200; title/address changed"],
        ["DELETE /api/rentals/highest", "204; ID 3 removed"],
        ["GET /api/rentals?q=Market", "200; matching ID 1 only"],
    ], caption="Actual statuses and GET snapshots are retained in raw/part12. Immediate navigation prevented retaining POST/PUT response bodies; no response body was reconstructed."))
    p.append(page("Part 2, Q1 | Create a rental", [
        "The form submitted Downtown San Jose Studio, 999 Main Street, San Jose, CA, a valid email, a description, Apartment, and accepted terms. The server assigned the current maximum ID plus one and returned home with ID 3 displayed."
    ], code=[lines(backend, 111, 116)], pictures=[shot + "part2/P2-Q1-created.png"], caption="Actual post-create UI from the isolated capture. IDs 1 and 2 remain, and new ID 3 has the submitted values. Request status: 201."))
    p.append(page("Part 2, Q2 | Update record ID 1", [
        "Edit prefilled ID 1's old title and address. The new values were Updated Downtown Apartment and 900 Market Street, San Jose, CA. Only those fields changed; email, description, type, accepted terms and the other records were preserved."
    ], code=[lines(backend, 118, 122)], pictures=[shot + "part2/P2-Q2-updated.png"], caption="Actual home view after PUT /api/rentals/1 returned 200. The before-editor image and before/after JSON are also included in the evidence directory."))
    p.append(page("Part 2, Q3 | Delete the highest ID", [
        "Before deletion, the store held IDs 1, 2 and 3, as shown in Q1. The global highest-ID action selected 3 from all stored records, including records a search could hide. After confirmation, the API removed it and the browser returned home."
    ], code=[lines(backend, 90, 92), lines(backend, 125, 129)], pictures=[shot + "part2/P2-Q3-after.png"], caption="Actual post-delete UI: only IDs 1 and 2 remain; the highest ID is now 2. DELETE /api/rentals/highest returned 204. A separate before-deletion capture is preserved."))
    p.append(page("Part 2, Q4 | Search by title", [
        "Searching Downtown returns only ID 1. The word is in its updated title but not its address. The OR condition below checks both domain fields after trimming whitespace and ignoring case."
    ], code=[lines(backend, 98, 107)], pictures=[shot + "part2/P2-Q4-title.png"], caption="Actual title-only match. The query, one-result summary and matching card are visible. The global count remains two because search does not delete records."))
    p.append(page("Part 2, Q4 | Search by address", [
        "Searching Market also returns only ID 1, this time through its address. Market is absent from the title. Clear restores all records; a no-match query shows a distinct no-match message."
    ], code=[lines(js, 301, 308)], pictures=[shot + "part2/P2-Q4-address.png"], caption="Actual address-only match, demonstrating the other side of the OR search. Clear and no-match captures are included as supporting evidence."))
    p.append(page("Part 3 | From a sequence to a graph", [
        "HW1 ran Planner then Reviewer in a fixed order. HW2 keeps a shared state and lets a supervisor choose what happens next. A rejected draft can return to Planner, while approved output ends the run.",
        "State holds the rental input, model adapter, current draft, review, revision numbers and turn count. Each worker accepts only state and returns the fields it changed. A turn means one Planner or Reviewer execution; the supervisor itself does not consume a turn.",
        "The worker's LLM object is the shared model-client adapter. The helper calls complete(messages), rather than creating direct Ollama calls in the nodes. The graph is executed once through stream(), and events record each update."
    ], code=[lines(graph + "state.py", 8, 28), lines(graph + "nodes.py", 83, 88)], pictures=[panels + "P3-normal.png"], caption="Fresh integrated-graph smoke output, rendered from saved real console/JSON. This is separate from the 75 measured Part 4 trials."))
    p.append(page("Part 3 | Worker responsibilities", [
        "Planner combines the rental description with previous feedback and proposes metadata. Reviewer checks the current proposal and returns issues, or an empty issues list for approval. A new draft invalidates the previous review, so approval cannot accidentally apply to an older revision."
    ], code=[lines(graph + "nodes.py", 126, 153), lines(graph + "nodes.py", 155, 174)], pictures=[panels + "P3-normal-short.png"], caption="Saved output from the current real smoke run: a schema-valid draft needs Reviewer approval before it becomes final output."))
    p.append(page("Part 3 | Supervisor and routing", [
        "The supervisor counts completed worker turns, then checks errors, approval and the ceiling. Approval on the last allowed turn succeeds. Otherwise the ceiling ends the run with no final output. The router only chooses a node; it does not update state or call the model."
    ], code=[function(graph + "nodes.py", "supervisor_node"), function(graph + "router.py", "router_logic")], pictures=[panels + "P3-controlled-short.png"], caption="Fresh controlled smoke run: the forced Reviewer issue prevents approval and the graph stops at its configured ceiling."))
    p.append(page("Part 3 | Wiring, streaming and correction loop", [
        "Both workers return to the supervisor. Conditional edges select Planner, Reviewer or END. For the correction-loop demonstration, the controlled-reviewer option appends a labeled issue after each valid real Reviewer response. This repeats Planner and Reviewer until the ceiling; it does not claim a natural model-quality failure."
    ], code=[function(graph + "workflow.py", "build_graph"), lines("code/agents_graph.py", 194, 203)], pictures=[panels + "P3-controlled.png"], caption="Screenshot of saved real-model streamed output with controlled Reviewer issues. Raw responses remain separate from the effective forced feedback. Historical Part 3 baseline evidence is preserved, but these report demonstrations use the final integrated graph."))
    p.append(page("Part 4, Q1 | Enforce the output rules", [
        "Pydantic checks the Planner response before Reviewer sees it: exactly three string tags, each 3-30 characters, and a summary of at most 25 words. Extra keys and wrong types are rejected. Tags must also be nonblank. Word count uses whitespace splitting; tag length uses Python string length.",
        "The validator rejects unsuitable output without silently padding tags, changing wording or filling missing values. A two-character tag such as AI therefore fails."
    ], code=[lines(graph + "contracts.py", 15, 24), lines(graph + "contracts.py", 27, 43)], pictures=[panels + "p4q1-schema-valid-output.png"], caption="Browser-rendered saved output from a real schema trial. The raw trial and validation results remain available in the campaign directory."))
    p.append(page("Part 4, Q2 | Feed errors back and retry", [
        "A validation error becomes plain feedback naming the field and problem. The next Planner attempt receives that feedback. Invalid drafts never advance to Reviewer. The same worker-turn ceiling limits repair attempts, so repeated failures cannot loop forever.",
        "The ordinary measured input produced no schema failures. A separate deterministic test therefore supplied an invalid AI tag, then a valid replacement and approval. It exercised the actual graph, but its scripted responses are not counted among model experiment results."
    ], code=[lines(graph + "nodes.py", 97, 107), lines(graph + "nodes.py", 126, 139)], pictures=[panels + "p4q2-scripted-repair-output.png"], caption="Scripted test output, excluded from all 75 measured trials. It shows invalid Planner -> corrected Planner -> Reviewer approval, accepted on turn 3. A separate repeated-invalid test stops at its ceiling."))
    p.append(page("Part 4 | Frozen input and measurement method", [
        "Before measurement, one ordinary rental input was saved as cases/schema_input.json and copied into the frozen campaign, with its path and hash recorded in the manifest. A different adversarial input was also frozen before the run. The same ordinary input and model settings were used for all 30 schema trials and both 20-run ceiling groups.",
        "Each trial used a fresh process, state and adapter. Runs were sequential, with ordinary Ollama caching and model residency retained. One ordinary warm-up was excluded, and no pilot trials were used. The ceiling comparison alternated which ceiling ran first in each pair.",
        "A run means one complete graph execution. An accepted first-attempt run used one Planner attempt plus current Reviewer approval. One retry means two Planner attempts; two-or-more retries means at least three. Reviewer retries are not counted as Planner retries. A ceiling exit takes precedence over an unapproved valid draft.",
        "Latency is the application's elapsed_ms: Git inspection, adapter and graph setup, execution and trace handling. It excludes process startup/imports and evidence writing. Means use unrounded saved values. Empty categories are reported as N/A, not zero milliseconds.",
        "Model settings: qwen3:1.7b, temperature 0, JSON mode, reasoning disabled, context 4096, and 120-second timeout per call. SEED 6102 and VERIFY_SEED 266102 identify the assignment; they were not supplied as random-number seeds to the model. Temperature zero does not guarantee identical text.",
        "The campaign observed HEAD 17fd1b3 with uncommitted Part 4 work. Frozen source hashes identify those actual runtime files. Later changes to the runner and verifier hardened evidence handling; graph, schema, prompts, shared adapter and calculation rules were unchanged. The final code tag identifies the submitted implementation, not a fabricated earlier execution date.",
    ], code=[("Frozen input: reports/hw02/cases/schema_input.json", read("reports/hw02/cases/schema_input.json"))]))
    p.append(page("Part 4, Q3 | Thirty schema trials", [
        "All 30 ordinary-input trials were accepted on the first Planner attempt. There were no schema failures, Planner retries, Reviewer issues or ceiling exits in this group. This result describes the chosen input and settings; it does not prove that all rental descriptions will pass."
    ], code=[lines("code/agents_experiments.py", 101, 107), lines(graph + "evaluation.py", 63, 66), lines(graph + "evaluation.py", 353, 358)], pictures=[panels + "p4q3-schema-thirty-run-table.png"], caption="Screenshot of the table regenerated from the 30 saved trial records. Mean accepted-run latency was 2104.40 ms. Zero-count categories have no mean."))
    p.append(page("Part 4, Q4 | Compare ceilings 2 and 10", [
        "Both ceilings accepted all 20 trials, and every run ended in two worker turns. The predeclared choice rule favored completion rate first, then lower observed mean latency, then the smaller ceiling. That rule selects 10 for this sample.",
        "The mean difference was about 13.39 ms (roughly 0.54%). It is small and does not establish that a larger ceiling causes faster execution. The selected default leaves room for revisions, but these ordinary trials did not use that extra allowance."
    ], code=[lines(graph + "evaluation.py", 373, 382), ("Reproduce the selected deployment configuration", ".venv-agents/bin/python code/agents_graph.py \\\n  --input-json reports/hw02/cases/schema_input.json --max-turns 10")], pictures=[panels + "p4q4-ceiling-comparison-table.png"], caption="Browser-rendered measured table: separate groups of 20 runs, same input/model settings, all-run latency means. The machine-readable decision is deployment_choice.json."))
    p.append(page("Part 4, Q5 | Adversarial input and ceiling", [
        "The adversarial listing mixes conflicting amenity claims with embedded instructions to use short tags and the wrong output format. Across five trials, the Planner repeatedly returned AI and SJ, even after receiving the minimum-length error. Later attempts added a third tag but kept the two invalid short tags.",
        "All five runs reached the 10-turn ceiling, with ten invalid Planner attempts and no Reviewer calls in each. The observed stopping cause was schema-invalid tags, not the amenity contradictions, a Reviewer rejection, or a transport error. Five observations do not establish deterministic failure."
    ], code=[lines(graph + "nodes.py", 97, 107), lines(graph + "nodes.py", 179, 189)], pictures=[panels + "p4q5-adversarial-results.png"], caption="Saved real adversarial results: 5/5 ceiling exits, mean latency 7439.33 ms. The first invalid response, field-specific error and final ceiling state are preserved."))
    p.append(page("Part 4, Q5 | Proposed fix and limits", [
        "Proposed fix: strengthen the trusted Planner retry message to name the rejected short tags, tell it to discard formatting demands embedded in the rental text, and request new topical tags of 3-30 characters. Keep the validator and turn ceiling. Do not pad or replace tags in Python to make invalid output look valid.",
        "This prompt change was not applied to the baseline. It should be evaluated in a separately frozen follow-up campaign so its effect can be compared honestly with the recorded five failures.",
        "Across the full campaign there were 75 terminal outcomes: 70 accepted and five ceiling exits. No operational errors, unknown outcomes, interrupted trials or replacement trials occurred. All original records are retained, including the excluded warm-up. The scripted repair demonstration and fresh smoke runs are separate from these 75 measurements.",
        "The ordinary case, one local model, one machine and a small adversarial sample limit generalization. Reported time is application-run latency, not end-to-end user latency. Model caching and residency can affect timings. A larger and more varied evaluation would be needed before making a broader deployment claim.",
    ], table=[
        ["Stored result", "Purpose"],
        ["manifest.json + input/source hashes", "What was frozen before the campaign"],
        ["75 trial directories", "Raw responses, feedback, events and terminal outcomes"],
        ["results.csv / results.jsonl", "Machine-readable one-row-per-trial results"],
        ["summary.json / METRICS.md", "Recomputed counts and means"],
        ["deployment_choice.json", "Decision tied to this campaign and rule"],
    ]))
    return p


def add_closing(p):
    verification = REPORT / "verification.json"
    v = json.loads(verification.read_text()) if verification.exists() else {}
    checks = v.get("checks", [])
    rows = [["Final smoke check", "Result"]]
    for name, check in (checks.items() if isinstance(checks, dict) else ((str(i), c) for i, c in enumerate(checks))):
        rows.append([name.replace("_", " "), "PASS" if check.get("passed") is True else str(check.get("status", check.get("passed", "recorded")))])
    if len(rows) == 1:
        rows.append(["Combined verification", "Pending final code freeze"])
    p.append(page("Verification and reproducible runs", [
        "The final self-check records the homework identity, tagged code revision, model settings, seeds and objective pass/fail checks in verification.json. It checks behavior and structure rather than requiring the model to repeat exact prose. It does not modify application source.",
        "The Part 4 evidence was also independently checked against 75 raw records and 525 recorded file hashes. Saved arithmetic agrees with the published tables. The implementation-stage suites recorded 95 agent tests and 35 API tests passing; retained HW1 evidence records 46 tests with one skipped. The editing follow-up recorded 22 passing browser checks.",
        "The new smoke runs are separate functional demonstrations. Historical measurements and timestamps have not been rewritten to imply they ran on the final tag. RUN_LOG.txt combines actual console records with links to their detailed raw artifacts.",
    ], table=rows, code=[("Start the web app", "source .venv-web/bin/activate\npython code/web_application/main.py"), ("Run the selected agent configuration", ".venv-agents/bin/python code/agents_graph.py \\\n  --input-json reports/hw02/cases/schema_input.json --max-turns 10")], caption="Full environment setup, offline evidence checks and tagged smoke commands are in REPRODUCIBLE_RUN_INSTRUCTIONS.md."))
    ai = read("reports/hw02/AI_USE.md")
    paragraphs = [line for line in ai.splitlines() if line and not line.startswith("#")]
    p.append(page("AI use and personal verification", paragraphs))
    p.append(page("Submission inventory and final actions", [
        "The assignment is submitted through the same data260-6102 repository, with the uploaded PDF named Apurva_HW2.pdf. The repository's canonical copy is reports/hw02/report.pdf; the upload copy is byte-for-byte identical.",
        "Code and output are paired throughout this report. Additional before/after, input, clear, no-match and historical screenshots remain in the repository for inspection. Browser-rendered saved output is labeled; it is not presented as a native Terminal capture.",
        "The links below identify the repository and its HW2 submission branch. Before submitting to the course portal, confirm that both required collaborators have access and upload the named PDF. Collaborator confirmation and portal upload remain separate steps.",
    ], table=[
        ["Submission item", "Assignment requirement satisfied"],
        ["report.pdf; matching Apurva_HW2.pdf", "Write-up, code/output screenshots, answers and configuration"],
        ["RUN_LOG.txt and RUN_LOG_PART*.txt", "Real console output and timestamps"],
        ["raw/part4/20260914T0610-baseline", "30 + 20 + 20 + 5 measured trial records"],
        ["cases/schema_input.json", "Fixed domain input saved before experiments"],
        ["METRICS.md", "Filled counts, means, completion rates and choice"],
        ["AI_USE.md", "Four disclosure/reflection answers"],
        ["REPRODUCIBLE_RUN_INSTRUCTIONS.md", "Setup and commands to reproduce/check results"],
        ["verification.json + scripts/verify_hw02.py", "Tagged implementation smoke test with objective checks"],
        ["screenshots/ and raw/part12/", "UI captures plus screenshot/request provenance"],
        ["SUBMISSION_CHECKLIST.md", "Requirement mapping and remaining external actions"],
    ]))

    p[-1]["after_text"] = [
        'GitHub repository: <link href="https://github.com/ishuapurva1996/data260-6102" color="#167d8d">https://github.com/ishuapurva1996/data260-6102</link>',
        'HW2 code and report: <link href="https://github.com/ishuapurva1996/data260-6102/tree/codex/fix-hw1-form" color="#167d8d">https://github.com/ishuapurva1996/data260-6102/tree/codex/fix-hw1-form</link>',
    ]


def paragraph(c, text, x, y, width=WIDTH, style=BODY):
    para = Paragraph(text, style)
    _, height = para.wrap(width, H)
    para.drawOn(c, x, y - height)
    return y - height - 8


def draw_code(c, label, source, y):
    y = paragraph(c, html.escape(label), MARGIN, y, style=CAPTION)
    code_lines = []
    for line in source.strip("\n").splitlines():
        code_lines.extend(textwrap.wrap(line, width=108, replace_whitespace=False, drop_whitespace=False, subsequent_indent="    ") or [""])
    height = len(code_lines) * 9.2 + 16
    c.setFillColor(colors.HexColor("#f1f5f8"))
    c.roundRect(MARGIN, y - height, WIDTH, height, 4, fill=1, stroke=0)
    t = c.beginText(MARGIN + 9, y - 12)
    t.setFont("Courier", 7.8)
    t.setLeading(9.2)
    t.setFillColor(colors.HexColor("#183246"))
    for line in code_lines:
        t.textLine(line)
    c.drawText(t)
    return y - height - 9


def draw_table(c, rows, y):
    count = len(rows[0])
    col_widths = [WIDTH / count] * count
    if count == 2:
        col_widths = [WIDTH * 0.46, WIDTH * 0.54]
    if count == 3:
        col_widths = [WIDTH * 0.26, WIDTH * 0.16, WIDTH * 0.58]
    style = ParagraphStyle("tablecell", parent=BODY, fontSize=9, leading=12)
    data = [[Paragraph(html.escape(str(cell)), style) for cell in row] for row in rows]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfeaf0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fb")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cad6df")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    _, height = t.wrap(WIDTH, H)
    t.drawOn(c, MARGIN, y - height)
    return y - height - 12


def build(args):
    commit = subprocess.check_output(["git", "rev-parse", f"{args.code_ref}^{{commit}}"], cwd=ROOT, text=True).strip()
    content = pages(args.code_ref, commit)
    add_closing(content)
    destination = REPORT / "report.pdf"
    c = canvas.Canvas(str(destination), pagesize=A4, pageCompression=1)
    c.setTitle("Pragya Apurva - DATA 260 Homework 2")
    c.setAuthor("Pragya Apurva")
    markdown = ["# DATA 260 Homework 2", "", f"Verified code: `{args.code_ref}` / `{commit}`", ""]
    layout = []
    for i, item in enumerate(content, 1):
        c.setFillColor(TEAL)
        c.rect(MARGIN, H - 38, WIDTH, 3, fill=1, stroke=0)
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 17)
        c.drawString(MARGIN, H - 64, item["title"])
        y = H - 84
        markdown += [f"## {item['title']}", ""]
        for text in item["text"]:
            y = paragraph(c, text, MARGIN, y)
            markdown += [text, ""]
        for label, source in item["code"]:
            y = draw_code(c, label, source, y)
            markdown += [label, "", "```", source, "```", ""]
        if item["table"]:
            y = draw_table(c, item["table"], y)
            rows = item["table"]
            markdown += ["| " + " | ".join(map(str, rows[0])) + " |", "|" + "---|" * len(rows[0])]
            markdown += ["| " + " | ".join(map(str, row)) + " |" for row in rows[1:]] + [""]
        caption_height = 0
        if item["caption"]:
            _, caption_height = Paragraph(html.escape(item["caption"]), CAPTION).wrap(WIDTH, H)
        if item["pictures"]:
            available = y - 55 - caption_height - 15
            assert available >= 100, f"Page {i}: insufficient space for output image ({available})"
            n = len(item["pictures"])
            each_width = (WIDTH - 14 * (n - 1)) / n
            sizes = []
            for filename in item["pictures"]:
                path = ROOT / filename
                with Image.open(path) as im:
                    iw, ih = im.size
                scale = min(each_width / iw, available / ih)
                sizes.append((path, iw * scale, ih * scale, (iw, ih)))
            image_height = max(height for _, _, height, _ in sizes)
            for j, (path, width, height, original) in enumerate(sizes):
                x = MARGIN + j * (each_width + 14) + (each_width - width) / 2
                c.drawImage(str(path), x, y - height, width=width, height=height, preserveAspectRatio=True, mask="auto")
                layout.append(dict(page=i, image=str(path.relative_to(ROOT)), original=original, width_pt=round(width, 2), height_pt=round(height, 2)))
                markdown += [f"![{item['title']}]({path.relative_to(REPORT).as_posix()})", ""]
            y -= image_height + 9
        if item["caption"]:
            y = paragraph(c, html.escape(item["caption"]), MARGIN, y, style=CAPTION)
            markdown += [item["caption"], ""]
        for text in item.get("after_text", []):
            y = paragraph(c, text, MARGIN, y)
            markdown += [text, ""]
        assert y >= 39, f"Page {i} overflow: y={y}"
        c.setFillColor(GRAY)
        c.setFont("Helvetica", 8)
        c.drawString(MARGIN, 23, "DATA 260 | HW2 | Pragya Apurva | SID4 6102")
        c.drawRightString(W - MARGIN, 23, f"{i} / {len(content)}")
        c.showPage()
    c.save()
    (REPORT / "report.md").write_text("\n".join(markdown).rstrip() + "\n")
    (REPORT / "report-layout.json").write_text(json.dumps({"pages": len(content), "code_ref": args.code_ref, "code_commit": commit, "images": layout}, indent=2) + "\n")
    if args.upload_copy:
        target = Path(args.upload_copy).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(destination, target)
    print(json.dumps({"pdf": str(destination), "pages": len(content), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-ref", default="hw2-code")
    parser.add_argument("--upload-copy")
    build(parser.parse_args())
