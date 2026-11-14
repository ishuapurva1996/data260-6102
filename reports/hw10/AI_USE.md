# HW10 AI use

## 1. AI assistance and my work

I gave Codex the assignment and integration scope, supplied the exact milestone
commits, and personally assigned the helpfulness labels for all 20 Writer drafts
before seeing any judge scores. I also took the dashboard and code screenshots
in the report. Codex assisted with the tracing, evaluator,
dashboard, benchmark, evidence checks, integration, and report preparation.
The local Qwen model generated the agent responses and also served as the
G-Eval judge. The human labels were my own work.

## 2. One unsuitable AI-produced output

For case `hw10-05`, the judge gave the draft 2/5 and said it failed to answer
whether the listing had at least two units. The draft explicitly answered no
and stated the recorded count of one. The frozen human label was 4/5.

## 3. How the issue was detected

The evaluation audit joined the raw judge rows to the frozen labels by
case ID. It compared the judge's reason with the unchanged draft and
reference facts. The same 2/5 verdict appeared in all three passes.

## 4. What changed and why

The report uses the judge for diagnostic feedback alongside human review and
records the conflicting 2/5 and 4/5 ratings. Keeping both ratings makes the
difference auditable. A deployment gate would require independent human
ratings and a held-out set with serious factual errors, plus an estimate of
how often a proposed threshold lets those errors through.
