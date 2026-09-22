#!/usr/bin/env python3
"""Build the HW3 PDF and Markdown from committed code and saved evidence.

No application, retrieval model, network request, tag, or publication is run here.
The exact existing commit supplied as --code-ref must match the integration
checks. Saved Part 2 measurements retain their original experiment commit.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import textwrap

from PIL import Image as PILImage
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    Image, KeepTogether, PageBreak, Paragraph, Preformatted, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/hw03"
BASELINE = "reports/hw03/raw/part2/manual-screenshots-20260921"
MANUAL_SHOTS = "reports/hw03/screenshots/manual/"
MANUAL_CAPTURE = "reports/hw03/raw/manual-captures/capture-manifest.json"
AUTH = "code/web_application/routers/auth.py"
WEB = "code/web_application/"
REPO_URL = "https://github.com/ishuapurva1996/data260-6102"
WIDTH = A4[0] - 80
NAVY = colors.HexColor("#17354d")
TEAL = colors.HexColor("#167d8d")
GRAY = colors.HexColor("#52606b")
PALE = colors.HexColor("#f1f5f8")
METHODS = ["token", "semantic", "sentence_window"]
NAMES = {"token": "Token", "semantic": "Semantic", "sentence_window": "Sentence window"}

STYLES = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=19,
                            leading=23, textColor=NAVY, spaceAfter=15),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10,
                           leading=14, textColor=NAVY, spaceAfter=9),
    "subhead": ParagraphStyle("subhead", fontName="Helvetica-Bold", fontSize=11,
                              leading=15, textColor=TEAL, spaceBefore=6, spaceAfter=6),
    "caption": ParagraphStyle("caption", fontName="Helvetica", fontSize=8.2,
                              leading=11, textColor=GRAY, spaceAfter=9),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.6,
                           leading=11, textColor=NAVY),
    "headcell": ParagraphStyle("headcell", fontName="Helvetica-Bold", fontSize=8.6,
                               leading=11, textColor=colors.white),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=8.1,
                           leading=10.4, textColor=NAVY, leftIndent=7,
                           rightIndent=7, borderPadding=7, backColor=PALE,
                           spaceAfter=10),
}


class Inputs:
    """Register the exact bytes of every file consumed by the builder."""
    def __init__(self):
        self.hashes: dict[str, str] = {}

    def bytes(self, relative: str) -> bytes:
        path = ROOT / relative
        content = path.read_bytes()
        self.hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(content).hexdigest()
        return content

    def path(self, relative: str) -> Path:
        path = ROOT / relative
        self.bytes(relative)
        return path

    def text(self, relative: str) -> str:
        return self.bytes(relative).decode("utf-8")

    def json(self, relative: str):
        return json.loads(self.text(relative))


def para(text: str):
    return {"kind": "paragraph", "text": text}


def heading(text: str):
    return {"kind": "subhead", "text": text}


def table(rows, widths=None):
    return {"kind": "table", "rows": rows, "widths": widths}


def code(label, source):
    return {"kind": "code", "label": label, "text": source.rstrip()}


def figure(paths, caption, *, max_height=360, max_width=WIDTH):
    if isinstance(paths, str):
        paths = [paths]
    return {"kind": "figure", "paths": paths, "caption": caption,
            "max_height": max_height, "max_width": max_width}


def page(title, *elements):
    return {"title": title, "elements": list(elements)}


def source_lines(inputs, path, start, end):
    lines = inputs.text(path).splitlines()
    return code(f"{path} | lines {start}-{end}", "\n".join(lines[start - 1:end]))


def excerpt(inputs, path, first, last):
    """Extract an inclusive range using unique, checked source text markers."""
    lines = inputs.text(path).splitlines()
    starts = [i for i, line in enumerate(lines) if first in line]
    if len(starts) != 1:
        raise ValueError(f"Expected one start marker {first!r} in {path}")
    start = starts[0]
    end = next(i for i in range(start, len(lines)) if last in lines[i])
    if end + 1 < len(lines) and lines[end + 1].strip() == ")":
        end += 1
    return source_lines(inputs, path, start + 1, end + 1)


def function(inputs, path, name):
    source = inputs.text(path)
    tree = ast.parse(source)
    nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(nodes) != 1:
        raise ValueError(f"Expected one function {name} in {path}")
    node = nodes[0]
    decorators = [d.lineno for d in node.decorator_list]
    return source_lines(inputs, path, min([node.lineno] + decorators), node.end_lineno)


def selected_lines(inputs, path, markers):
    """Show short noncontiguous excerpts without presenting them as a full function."""
    lines = inputs.text(path).splitlines()
    matches = []
    previous = None
    for marker in markers:
        found = [(i, line) for i, line in enumerate(lines) if marker in line]
        if len(found) != 1:
            raise ValueError(f"Expected one excerpt marker {marker!r} in {path}")
        i, line = found[0]
        if previous is not None and i != previous + 1:
            matches.append("")
        matches.append(line)
        previous = i
    return code(path + " | selected source statements", textwrap.dedent("\n".join(matches)))


def part2_picture(name):
    names = {
        "token": "11-token-output.png",
        "semantic": "12-semantic-output.png",
        "sentence_window": "13-sentence-window-output.png",
        "metrics": "14-comparison-table.png",
        "failure": "15-high-score-failure.png",
    }
    return MANUAL_SHOTS + names[name]


def fmt(value, places=4):
    return "N/A" if value is None else f"{value:.{places}f}"


def build_pages(inputs, commit, code_tag=None):
    run = inputs.json(f"{BASELINE}/run.json")
    summary = inputs.json(f"{BASELINE}/summary.json")
    corpus = inputs.json("reports/hw03/CORPUS_MANIFEST.json")
    browser = inputs.json("reports/hw03/raw/part1/browser-evidence.json")
    hardware = inputs.json("reports/hw03/part2/hardware.json")
    checks = inputs.json("reports/hw03/raw/integration/checks.json")
    captures = inputs.json(MANUAL_CAPTURE)
    if captures["retrieval_run"] != BASELINE:
        raise ValueError("Manual screenshots must identify the report's retrieval run")
    for capture in captures["images"].values():
        if hashlib.sha256(inputs.bytes(capture["path"])).hexdigest() != capture["sha256"]:
            raise ValueError(f"Manual screenshot changed: {capture['path']}")
    for source, expected in captures["retrieval_source_sha256"].items():
        if hashlib.sha256(inputs.bytes(source)).hexdigest() != expected:
            raise ValueError(f"Captured retrieval source changed: {source}")
    for script in captures["support_scripts"].values():
        for variant in ("original", "portable"):
            if hashlib.sha256(inputs.bytes(script[variant + "_path"])).hexdigest() != script[variant + "_sha256"]:
                raise ValueError("Screenshot helper changed since capture import")
    access = inputs.json("reports/hw03/raw/integration/github-access.json") if code_tag else None
    if access and access.get("collaborators") != {"Sbnikitha": "Collaborator", "supriyaselvanganesan": "Collaborator"}:
        raise ValueError("Expected confirmed GitHub collaborator access for the final report")
    if checks.get("tested_code_commit") != commit:
        raise ValueError("Integration checks do not identify the requested tested-code commit")
    check_rows = checks.get("checks", [])
    if checks.get("status") != "pass" or not check_rows or any(c.get("exit_code") != 0 for c in check_rows):
        raise ValueError("Integration checks must be present and all exit successfully before report generation")
    if browser.get("status") != "pass" or browser.get("fail_count") != 0:
        raise ValueError("Browser evidence is not a passing capture")
    for source in [
        "reports/hw03/questions.yaml", "reports/hw03/experiment_config.yaml",
        "reports/hw03/SOURCES.md", "reports/hw03/METRICS.md",
        "reports/hw03/part1/REPORT_SECTION.md", "reports/hw03/part2/REPORT_SECTION.md",
        "reports/hw03/part2/ANSWER_SUPPORT_REVIEW.md", "reports/hw03/part2/GOLD_EVIDENCE_AUDIT.md",
        f"{BASELINE}/records.json", f"{BASELINE}/annotations.json", f"{BASELINE}/console.txt",
        "requirements-retrieval.txt", "requirements-report.txt", "scripts/build_hw03_report.py",
    ]:
        inputs.path(source)
    config = run["config"]
    method_stats = summary["baseline"]["techniques"]
    shot = MANUAL_SHOTS
    pages = []
    pages.append(page("Homework 3 | Rental Housing Listings",
        para("Pragya Apurva | DATA 260 | September 21, 2026"),
        table([
            ["Personal configuration", "Value", "Calculation / meaning"],
            ["SID4", "6102", "Last four student-ID digits"],
            ["PORT_BASE", "8702", "8000 + (6102 mod 900)"],
            ["PREFIX", "s6102", '"s" + SID4'],
            ["SEED", "6102", "SID4"],
            ["VERIFY_SEED", "266102", "260000 + SID4"],
            ["DOMAIN_ID", "6", "6102 mod 8; Rental Housing Listings"],
        ], [145, 76, WIDTH - 221]),
        para("Part 1 adds login, logout and session management to the existing rental application. Part 2 compares token, semantic and sentence-window chunking for searching housing documents."),
        para(f"Hardware: MacBook Air, {hardware['cpu']}, {hardware['logical_cpus']} logical CPUs, {hardware['memory_bytes'] // (1024 ** 3)} GiB memory; macOS 15.7.4, arm64. Python 3.12.14."),
        para("Local model: sentence-transformers/all-MiniLM-L6-v2 for Part 2 embeddings, running on CPU with one PyTorch thread. Part 1 does not use an AI model."),
        para(f"Repository: {REPO_URL}"),
        *([para("Repository access confirmed for Sbnikitha and supriyaselvanganesan on September 21, 2026.")] if access else []),
        para(f"Tested code{' (' + code_tag + ')' if code_tag else ''} commit: {commit}"),
        *([para(f"Submission tag: hw3 | {REPO_URL}/tree/hw3")] if code_tag else []),
    ))
    pages.append(page("Part 1 | Login and session management",
        para("HTTP does not remember earlier requests, so a session connects later requests to a user's login. Starlette's SessionMiddleware stores the username and a random session ID in a signed cookie. The signature detects changes; it does not encrypt the contents. The password is not stored in the cookie."),
        para("The server keeps the active session IDs and their last-activity times. Dashboard access requires a valid cookie and an active matching entry. Logout or expiry removes that entry, so even a saved copy of the cookie stops working."),
        table([
            ["Route", "Behavior"],
            ["GET /", "Rental homepage; Login when signed out; Dashboard and Logout when signed in"],
            ["GET /login", "Username and password form"],
            ["POST /login", "admin / password: 303 to /dashboard; invalid credentials: 401 and a Bootstrap alert"],
            ["GET /dashboard", "Welcome with username; 303 to /login without an active session"],
            ["GET /logout", "Revoke the session, clear the cookie and redirect to /"],
        ], [125, WIDTH - 125]),
        excerpt(inputs, WEB + "main.py", "app.add_middleware(", "app.include_router(auth.router)"),
        para("The routes are in routers/auth.py. This single-worker teaching app uses public demo credentials and keeps sessions in memory. A restart clears them. The existing rental API remains unchanged and does not require login."),
        figure(shot + "00-server-startup.png", "HTTPS application startup on port 8702.", max_height=125),
    ))
    pages.append(page("Part 1 | Home page",
        para("The homepage retains the rental controls and changes its navigation when a user signs in."),
        function(inputs, AUTH, "home"),
        figure(shot + "01-home.png", "Homepage before login.", max_height=490),
    ))
    pages.append(page("Part 1 | Home after login",
        para("After login, the homepage displays the username and links to the dashboard and logout."),
        function(inputs, AUTH, "home"),
        figure(shot + "05-home-logged-in.png", "Homepage with an active admin session.", max_height=490),
    ))
    pages.append(page("Part 1 | Login form",
        para("The login page uses a Bootstrap card with labeled username and password fields."),
        function(inputs, AUTH, "login_page"),
        figure(shot + "02-login.png", "Login form.", max_height=490),
    ))
    pages.append(page("Part 1 | Invalid login",
        para("The form uses a Bootstrap card, labeled inputs and a submit button. Invalid credentials return HTTP 401 and display an alert above the form."),
        excerpt(inputs, AUTH, 'if username != "admin"', 'status_code=401, headers=NO_STORE,'),
        figure(shot + "03-invalid-login.png", "Alert after an invalid username or password.", max_height=490),
    ))
    pages.append(page("Part 1 | Protected dashboard",
        para("A successful login redirects to the dashboard, which displays admin and the 300-second idle limit. The route checks the server's session registry before displaying the page."),
        excerpt(inputs, AUTH, "async def dashboard", 'return RedirectResponse("/login"'),
        figure(shot + "04-dashboard.png", "Dashboard after a successful login.", max_height=490),
    ))
    pages.append(page("Part 1 | Logout",
        para("Logout removes the server's session entry, clears the browser cookie and returns to the homepage."),
        excerpt(inputs, AUTH, "async def logout", 'return RedirectResponse("/",'),
        figure(shot + "06-after-logout.png", "Homepage after logout, with Login available again.", max_height=490),
    ))
    pages.append(page("Part 1 | Reusing a logged-out cookie",
        para("The terminal check logs in and saves the cookie. It first reaches /dashboard with HTTP 200, then logs out and sends the same saved cookie again. The second dashboard request returns HTTP 303 to /login."),
        function(inputs, AUTH, "revoke_session"),
        figure(shot + "08-logout-replay.png", "The saved cookie is rejected after logout.", max_height=400),
    ))
    pages.append(page("Part 1 | Secure session cookie",
        para("HttpOnly prevents ordinary page JavaScript from reading the cookie. Secure restricts it to HTTPS, and SameSite=lax limits cross-site sending. Max-Age=3600 sets the cookie lifetime; the server enforces the shorter idle timeout separately."),
        excerpt(inputs, WEB + "main.py", "app.add_middleware(", "https_only=True,"),
        figure(shot + "07-cookie-header.png", "Login response with HttpOnly, SameSite=lax and Secure.", max_height=335),
        para("The curl command trusts the local development certificate for this request. It prints the response headers and hides only the cookie value."),
    ))
    pages.append(page("Part 1 | Idle timeout",
        para("A session expires after 300 seconds without activity. The server checks expiry before renewing the session. Home, login and dashboard requests renew it; static files and rental API requests do not."),
        function(inputs, WEB + "session_store.py", "cleanup"),
        table([
            ["Check", "Result"],
            ["Copied expired cookie", "The live check waited 301.0 seconds with the normal 300-second timeout. Replaying the saved cookie returned 303 to /login."],
            ["300-second boundary", "A controlled clock confirmed renewal before the boundary and denial at exactly the limit."],
            ["Other invalid sessions", "Changed cookies, unknown IDs, mismatched usernames and replaced logins were rejected."],
        ], [126, WIDTH - 126]),
        figure(shot + "09-idle-timeout.png", "The saved cookie is rejected after 301 seconds without activity.", max_height=245),
    ))
    pages.append(page("Part 1 | Bootstrap and templates",
        para("base.html shares the navbar across the home, login and dashboard pages. Bootstrap cards organize content, buttons identify actions and alerts explain errors. Bootstrap 5.3.2 is stored locally."),
        excerpt(inputs, WEB + "templates/base.html", '<nav class="navbar', '<a class="nav-link" href="/login">'),
        figure(shot + "10-templates-directory.png", "Application templates.", max_height=260),
        para("Browser tests checked the pages at 1280px and 375px widths. The content stayed within the screen without horizontal scrolling."),
    ))
    corpus_rows = [["Source", "Document", "Text bytes"]]
    corpus_rows += [[s["source_id"], s["title"], f"{s['bytes']:,}"] for s in corpus["sources"]]
    pages.append(page("Part 2 | Model and housing corpus",
        para("Retrieval splits documents into chunks and compares their embeddings with a question's embedding. An embedding is a vector of numbers representing features of the text. This experiment retrieves passages without generating an answer."),
        para(f"Model: {config['model_name']}, revision {config['model_revision']}. It produces normalized 384-dimensional vectors and accepts at most 256 tokens. Runs use CPU, one PyTorch thread and batch size 32. A token is a word, word part or punctuation mark used by the model."),
        table(corpus_rows, [109, 305, WIDTH - 414]),
        para(f"The four local text files contain {corpus['total_text_bytes']:,} bytes, above the {corpus['hard_minimum_bytes']:,}-byte minimum. They were accessed on September 20, 2026. Repeated headers, footers and duplicate paragraphs were removed. The HUD files are archived documents; the questions refer to their stated rules."),
        para("SOURCES.md and CORPUS_MANIFEST.json record the URLs, access dates, filenames, byte sizes and hashes. Original PDFs are retained, and answer passages were checked against their page images. The first 12,000 characters of Tiny Shakespeare were used only for the warm-up."),
        para(f"Inputs were committed before retrieval at {run['freeze_commit']}. The measured run used code {run['code_commit']}. Package versions are pinned in requirements-retrieval.txt; FAISS is installed, while the indexes use SimpleVectorStore."),
    ))
    short_answers = {
        "Q1": "Within 14 days.",
        "Q2": "$480 per eligible dependent in the archived handbook.",
        "Q3": "Boiling does not remove lead. Use only cold water for drinking, cooking and baby formula.",
        "Q4": "One year after the alleged discrimination occurred or ended.",
        "Q5": "At least 40% of assisted units becoming available during the project fiscal year.",
    }
    question_rows = [["ID", "Question", "Expected answer", "Expected source file"]]
    for question in run["questions"]:
        question_rows.append([question["id"], question["question"], short_answers[question["id"]],
                              "; ".join(Path(p).name for p in question["expected_source_files"])])
    pages.append(page("Part 2 | Five questions",
        para("These questions and expected answers were saved in questions.yaml before the retrieval run. All source files below are in reports/hw03/corpus/text/."),
        table(question_rows, [32, 215, 140, WIDTH - 387]),
        para("The source audit found each requested fact in only one corpus document, exceeding the requirement for at least two such questions. The matching passages and locations are recorded in part2/GOLD_EVIDENCE_AUDIT.md."),
    ))
    pages.append(page("Part 2 | Indexing and retrieval helper",
        para("Each chunker has its own in-memory index. Chunks stay within one document, and source metadata is excluded from embeddings. Settings.llm = None disables answer generation."),
        excerpt(inputs, "src/retrieval/indexing.py", "Settings.llm = None", "embed_model=embed_model, show_progress=False)"),
        para("The helper embeds the question, retrieves three passages and embeds them again to calculate cosine similarity. Selected statements from the helper are shown below."),
        selected_lines(inputs, "src/retrieval/evaluation.py", [
            'query_vector = _vector(embed_model.get_query_embedding(query)',
            'query_values = query_vector.tolist()',
            'retriever = index.as_retriever(similarity_top_k=k)',
            'results = retriever.retrieve(bundle)',
            'vectors = embed_model.get_text_embedding_batch(texts)',
            'cosine = cosine_similarity(query_vector, vector)',
        ]),
        excerpt(inputs, "src/retrieval/evaluation.py", "cosine = np.dot", "cosine = np.dot"),
        figure(part2_picture("token"), "Helper output for Q1 using the token index. [384] is the query vector's shape; [3, 384] represents three document vectors. The table shows store scores, calculated cosines, lengths and text previews.", max_height=360),
    ))
    for method, title, explanation, first, last in [
        ("token", "TokenTextSplitter", "Token splitting uses 192 content tokens per chunk and 32-token overlap. The model's tokenizer counts the tokens. Overlap repeats text near a boundary; this setting produced 440 chunks.", "parser = TokenTextSplitter(", "id_func=stable_id,"),
        ("semantic", "SemanticSplitterNodeParser", "Semantic splitting places boundaries where neighboring sentence groups change in meaning. It uses buffer size 1 and breakpoint percentile 95, producing 143 chunks. AuditedSemanticSplitter subclasses the LlamaIndex parser to record its boundary buffers without changing the split rule.", "parser = AuditedSemanticSplitter.from_defaults(", "id_func=stable_id,"),
        ("sentence_window", "SentenceWindowNodeParser", "Sentence-window splitting embeds each central sentence and keeps up to three sentences on either side as context. Search scores the central sentence; the neighboring text is available afterward. This setting produced 2,735 central sentences.", "parser = SentenceWindowNodeParser.from_defaults(", "include_prev_next_rel=False, id_func=stable_id,"),
    ]:
        pages.append(page("Part 2 | " + title,
            para(explanation),
            excerpt(inputs, "src/retrieval/chunking.py", first, last),
            figure(part2_picture(method), f"{NAMES[method]} output for Q1 (k = 3).", max_height=378),
        ))
    pages.append(page("Part 2 | Evaluation method",
        para("Five questions across three indexes give 15 comparisons. Each query is embedded before timing. One search warms the retriever, then ten searches are timed. Latency covers similarity search only, excluding embedding, index construction and output formatting."),
        table([
            ["Metric", "Definition"],
            ["Top-1 cosine", "Highest explicit cosine among the top three returned hits"],
            ["Mean@3 cosine", "Average explicit cosine of those three hits"],
            ["Source Recall@3", "Distinct expected sources retrieved / expected sources. Repeated hits from one source do not increase recall."],
            ["Central support@3", "At least one central text contains every fact needed to answer the question"],
            ["Context support@3", "At least one available context contains the full answer, including neighbors for sentence windows"],
            ["Macro average", "Each of the five questions has equal weight"],
        ], [134, WIDTH - 134]),
        para("Answer support requires the full answer within one hit. It does not combine partial answers from different hits. Codex reviewed all 45 complete passages and recorded its labels, quotations and reasons in annotations.json. Similarity scores alone do not determine these labels."),
        para("Every comparison returned three hits. The five questions already produced high-scoring passages without answers, so no extra diagnostic questions were needed."),
    ))
    aggregate = [["Method", "Chunks", "Mean chars", "Top-1", "Mean@3", "Recall@3", "Search ms"]]
    support = [["Method", "Central support@3", "Context support@3", "Answers supported (context)"]]
    for method in METHODS:
        row = method_stats[method]
        aggregate.append([NAMES[method], row["chunk_count"], fmt(row["average_character_length"], 1), fmt(row["top1_cosine"]), fmt(row["mean_at_k_cosine"]), fmt(row["source_recall_at_k"]), fmt(row["mean_search_latency_ms"], 3)])
        support.append([NAMES[method], fmt(row["central_support_at_k"]), fmt(row["context_support_at_k"]), f"{round(row['context_support_at_k'] * 5)}/5"])
    pages.append(page("Part 2 | Results across five questions",
        para("All three methods found the expected source for every question. Sentence-window context supplied four complete answers, semantic splitting supplied two and token splitting supplied one."),
        table(aggregate, [103, 48, 62, 65, 65, 78, WIDTH - 421]),
        table(support, [114, 127, 127, WIDTH - 368]),
        code("Recompute the tables from recorded results", "python code/retrieval_summarize.py \\\n  --run-dir reports/hw03/raw/part2/manual-screenshots-20260921"),
        figure(part2_picture("metrics"), "Results across the five questions.", max_height=330),
    ))
    by_query = sorted(summary["per_query"], key=lambda row: (row["question_id"], METHODS.index(row["technique"])))
    query_rows = [["Q", "Method", "Top-1", "Mean@3", "Support central/context", "Search ms"]]
    for row in by_query:
        query_rows.append([row["question_id"], NAMES[row["technique"]], fmt(row["top1_cosine"]), fmt(row["mean_at_k_cosine"]), f"{row['central_support_at_k']}/{row['context_support_at_k']}", fmt(row["mean_search_latency_ms"], 3)])
    pages.append(page("Part 2 | Results by question",
        para("Each row uses k = 3 and has source Recall@3 = 1.0000. A support value of 1 means a complete answer is present within at least one hit."),
        table(query_rows, [28, 113, 68, 68, 142, WIDTH - 419]),
        para("For Q3, separate central sentences give the boiling and cold-water facts. Each alone is incomplete, while their expanded windows contain both facts. Q2's answer is absent from every method's results despite the high cosine scores."),
    ))
    stats = summary["technique_stats"]
    trunc_rows = [["Method", "Mean central tokens", "Over 256 tokens", "Mean context chars"]]
    for method in METHODS:
        row = stats[method]
        trunc_rows.append([NAMES[method], fmt(row["average_token_length"], 1), f"{row['indexed_truncation_count']}/{row['chunk_count']}", fmt(row["average_context_character_length"], 1)])
    pages.append(page("Part 2 | Limits of the comparison",
        para("The model reads only the first 256 input tokens. Text beyond that limit remains in the saved passage but does not affect its embedding. Audit lengths include special tokens; the 192-token chunk setting counts content tokens only."),
        table(trunc_rows, [130, 123, 122, WIDTH - 375]),
        para("76 of 143 semantic chunks (53.15%) exceed the limit, as do 8 of 2,735 semantic boundary buffers (0.29%). No token chunk, central sentence or query exceeds it. Semantic chunks were kept intact. Sentence-window context averages 884.4 characters and 180.9 tokens; it is not embedded for search."),
        para("Q5's semantic rank-2 hit gives an example about the first 40% of expected vacancies. It does not state the complete minimum rule for assisted units becoming available during a project fiscal year, so its strict answer-support label is false. Counting that example as sufficient would raise semantic support from 0.40 to 0.60. Sentence-window context would still lead at 0.80."),
        para("The comparison covers five questions, four documents and one model configuration. The small sample and the answer-label choice limit how broadly the results can be applied."),
    ))
    failure = next(item for item in summary["high_score_failures"] if item["question_id"] == "Q2" and item["technique"] == "token" and item["rank"] == 1)
    pages.append(page("Part 2 | A high score without the answer",
        para(f"Q2 asks for the $480 dependent deduction. The top token hit scores {failure['cosine']:.4f}, above the 0.50 confidence threshold, but omits the amount. It reaches the right source without answering the question. Shared words about income and deductions likely explain the similarity."),
        figure(part2_picture("failure"), "Q2's top token hit, including its complete returned text.", max_height=618),
    ))
    pages.append(page("Part 2 | Observations and conclusion",
        heading("Observations"),
        para("Sentence windows supplied complete answers for four of five questions, compared with two for semantic splitting and one for token splitting. Q3 shows why the extra context helps: a sentence matches part of the question, while nearby text supplies the other fact. All methods found the right source for Q2, but none retrieved its answer. Source recall alone therefore overstates success here."),
        para(f"Semantic search was fastest at {method_stats['semantic']['mean_search_latency_ms']:.3f} ms, followed by token search at {method_stats['token']['mean_search_latency_ms']:.3f} ms and sentence-window search at {method_stats['sentence_window']['mean_search_latency_ms']:.3f} ms. This order is consistent with the number of chunks, although the experiment does not isolate chunk count as the cause. Long semantic chunks often exceeded the model's input limit, and the strict Q5 label also affects the comparison."),
        heading("Conclusion"),
        para(f"Sentence windows worked best for this corpus because their context supported four of five answers and their average top-1 cosine was highest. They took about {method_stats['sentence_window']['mean_search_latency_ms']:.0f} ms per search, compared with 1-4 ms for the other methods. Semantic splitting was faster, but the model could not read all of its longer chunks. The Q2 failure shows that a useful retrieval check needs to examine the answer text as well as its similarity score."),
    ))
    ai = inputs.text("reports/hw03/AI_USE.md")
    ai_elements = []
    for block in re.split(r"\n\s*\n", ai.strip()):
        if block.startswith("# "):
            continue
        if block.startswith("## "):
            ai_elements.append(heading(block[3:].strip()))
        else:
            ai_elements.append(para(" ".join(block.splitlines())))
    pages.append(page("AI assistant use", *ai_elements))
    source_rows = [["Reference", "Source"]]
    source_rows.extend([[s["source_id"], s["url"]] for s in corpus["sources"]])
    source_rows += [
        ["Tiny Shakespeare", "https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt"],
        ["Embedding model", "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2"],
        ["SessionMiddleware", "https://raw.githubusercontent.com/encode/starlette/0.35.1/starlette/middleware/sessions.py"],
        ["FastAPI forms", "https://fastapi.tiangolo.com/tutorial/request-forms/"],
        ["Uvicorn HTTPS settings", "https://uvicorn.dev/settings/#https"],
    ]
    pages.append(page("References and reproduction",
        para("The tutor's examples informed the separate authentication router and Bootstrap templates. Public documents and technical references are listed below."),
        table(source_rows, [162, WIDTH - 162]),
        para("The integration checks passed for authentication, existing rental behavior, retrieval and evidence consistency. Commands and results are recorded in reports/hw03/raw/integration/checks.json. Setup and rerun commands are in reports/hw03/REPRODUCIBLE_RUN_INSTRUCTIONS.md; verification.json contains the combined self-check result."),
        para("The appendix contains the complete auth.py. Supporting application and retrieval files remain in the repository."),
    ))
    auth_lines = inputs.text(AUTH).splitlines()
    for start in range(0, len(auth_lines), 50):
        end = min(start + 50, len(auth_lines))
        pages.append(page("Appendix | Full auth.py" + (" (continued)" if start else ""),
            para(f"{AUTH} | lines {start + 1}-{end} of {len(auth_lines)}"),
            code("Complete source, continued in original order", "\n".join(auth_lines[start:end])),
        ))
    return pages


def pdf_text(value):
    """Convert plain report text to escaped ReportLab text with live web links."""
    text = str(value).replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    text = html.escape(text)
    return re.sub(r"https://[^\s<]+", lambda m: f'<link href="{m.group(0)}" color="#167d8d">{m.group(0)}</link>', text)


def wrapped_code(source):
    # Preserve every character and mark visual wrapping without shrinking fonts.
    output = []
    for line in source.splitlines():
        output.extend(textwrap.wrap(line, width=94, expand_tabs=False,
                                    replace_whitespace=False, drop_whitespace=False,
                                    subsequent_indent="    ") or [""])
    return "\n".join(output)


def flowables(element, inputs):
    kind = element["kind"]
    if kind in {"paragraph", "subhead"}:
        return [Paragraph(pdf_text(element["text"]), STYLES["body" if kind == "paragraph" else "subhead"])]
    if kind == "code":
        return [KeepTogether([
            Paragraph(pdf_text(element["label"]), STYLES["caption"]),
            Preformatted(wrapped_code(element["text"]), STYLES["code"]),
        ])]
    if kind == "table":
        rows = [[Paragraph(pdf_text(cell), STYLES["headcell" if number == 0 else "cell"])
                 for cell in row] for number, row in enumerate(element["rows"])]
        item = Table(rows, colWidths=element["widths"], repeatRows=1, hAlign="LEFT")
        item.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, TEAL),
        ]))
        return [item, Spacer(1, 12)]
    if kind == "figure":
        images = []
        available = min(element["max_width"], WIDTH)
        cell_width = (available - (len(element["paths"]) - 1) * 12) / len(element["paths"])
        for relative in element["paths"]:
            path = inputs.path(relative)
            with PILImage.open(path) as source:
                width, height = source.size
            scale = min(cell_width / width, element["max_height"] / height)
            images.append(Image(str(path), width=width * scale, height=height * scale))
        if len(images) == 1:
            image_table = images[0]
            image_table.hAlign = "CENTER"
        else:
            image_table = Table([images], colWidths=[WIDTH / len(images)] * len(images))
            image_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        return [KeepTogether([image_table, Spacer(1, 7), Paragraph(pdf_text(element["caption"]), STYLES["caption"])])]
    raise ValueError(f"Unknown report element {kind}")


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(1)
    canvas.line(40, A4[1] - 32, A4[0] - 40, A4[1] - 32)
    canvas.setFillColor(GRAY)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(40, A4[1] - 25, "DATA 260  |  Homework 3  |  Pragya Apurva")
    canvas.drawString(40, 24, "Rental Housing Listings  |  Homework 3")
    canvas.drawRightString(A4[0] - 40, 24, str(doc.page))
    canvas.restoreState()


def markdown(pages):
    sections = []
    for item in pages:
        lines = ["# " + item["title"], ""]
        for element in item["elements"]:
            kind = element["kind"]
            if kind == "paragraph":
                lines.extend([element["text"], ""])
            elif kind == "subhead":
                lines.extend(["## " + element["text"], ""])
            elif kind == "code":
                lines.extend([element["label"], "", "```", element["text"], "```", ""])
            elif kind == "table":
                rows = element["rows"]
                for i, row in enumerate(rows):
                    lines.append("| " + " | ".join(str(cell).replace("|", "\\|").replace("\n", " ") for cell in row) + " |")
                    if i == 0:
                        lines.append("| " + " | ".join("---" for _ in row) + " |")
                lines.append("")
            elif kind == "figure":
                for path in element["paths"]:
                    relative = Path(path).relative_to("reports/hw03").as_posix()
                    lines.extend([f"![{Path(path).name}]({relative})", ""])
                lines.extend([element["caption"], ""])
        sections.append("\n".join(lines))
    return "\n".join(sections).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-ref", required=True, help="Existing tested integrated commit hash (no tag is created)")
    parser.add_argument("--code-tag", help="Existing tag that resolves to --code-ref")
    parser.add_argument("--upload-copy", type=Path, help="Optional destination for the identical Apurva_HW3.pdf copy")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", args.code_ref):
        parser.error("--code-ref must be an existing commit hash, not a branch or tag")
    commit = subprocess.check_output(["git", "rev-parse", "--verify", args.code_ref + "^{commit}"], cwd=ROOT, text=True).strip()
    if args.code_tag:
        subprocess.run(["git", "check-ref-format", "refs/tags/" + args.code_tag], cwd=ROOT, check=True)
        tagged = subprocess.check_output(["git", "rev-parse", "--verify", "refs/tags/" + args.code_tag + "^{commit}"], cwd=ROOT, text=True).strip()
        if tagged != commit:
            parser.error("--code-tag must resolve to the tested commit supplied as --code-ref")
    inputs = Inputs()
    pages = build_pages(inputs, commit, args.code_tag)
    REPORT.mkdir(parents=True, exist_ok=True)
    output = REPORT / "report.pdf"
    # Platypus adds 6-point frame padding; these margins leave 40-point visible edges.
    doc = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=34, rightMargin=34,
                            topMargin=41, bottomMargin=38, title="DATA 260 Homework 3 - Rental Housing Listings",
                            author="Pragya Apurva", subject="Homework 3: authentication and retrieval comparison")
    story = []
    for index, item in enumerate(pages):
        if index:
            story.append(PageBreak())
        story.append(Paragraph(pdf_text(item["title"]), STYLES["title"]))
        for element in item["elements"]:
            story.extend(flowables(element, inputs))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    markdown_path = REPORT / "report.md"
    markdown_path.write_text(markdown(pages), encoding="utf-8")
    result = {
        "schema_version": 1,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "status": "built",
        "tested_code_commit": commit,
        "tested_code_tag": args.code_tag,
        "submission_tag": "hw3" if args.code_tag else None,
        "pdf_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "markdown_sha256": hashlib.sha256(markdown_path.read_bytes()).hexdigest(),
        "source_sha256": dict(sorted(inputs.hashes.items())),
        "page_count": len(PdfReader(output).pages),
        "planned_sections": len(pages),
        "command": f"python scripts/build_hw03_report.py --code-ref {commit}" + (f" --code-tag {args.code_tag}" if args.code_tag else ""),
        "upload_copy": None,
        "visual_review": "Required after generation; successful build alone does not establish visual quality.",
    }
    if args.upload_copy:
        destination = args.upload_copy.expanduser().resolve()
        if destination == output.resolve():
            parser.error("--upload-copy must differ from the canonical report path")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output, destination)
        result["upload_copy"] = {"path": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}
    (REPORT / "report-build.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Built {output} ({result['page_count']} pages); SHA-256 {result['pdf_sha256']}")
    print(f"Markdown: {markdown_path}")


if __name__ == "__main__":
    main()
