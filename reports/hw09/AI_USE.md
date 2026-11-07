# AI-use disclosure

Pragya Apurva · DATA 260 Homework 9

1. **What did AI help with, and what work was done for this submission?**
   OpenAI Codex helped implement and integrate the Redis counter, semantic cache,
   experiment runners, two-agent workflow, verifier, setup instructions, and PDF.
   The work used the existing rental application and local Ollama adapter. The
   submission includes synthetic fixtures, actual service logs, frozen inputs,
   and measured results. AI also drafted the explanations and report layout.

2. **What output was unsuitable or required independent checking?**
   The automatic keyword scorer incorrectly accepted two Part 3 cached answers:
   mentioning wear and tear did not define it, and mentioning responsibilities
   did not explain a co-signer. High cosine scores also returned facts for the
   wrong listing. During integration, an initial verifier PUT lacked the title
   and address required by the existing API and correctly received HTTP 422.

3. **How was the work checked?**
   Saved answers were compared with the frozen rubrics and reference facts.
   The audited table was independently recomputed from all 200 requests. The
   integrated verifier checked the frozen YAML checksum, source ancestry, all
   four identical held-out inputs, and independently regraded 40 saved Part 4
   answers. Real authenticated HTTP, Redis, MySQL, Kafka offsets and model logs
   verified the counter, bypass, invalidation and two-attempt controls. Tests,
   lint, a frontend build, source review, and visual inspection of every PDF
   page supplied additional checks. These checks were executed with AI
   assistance; no unsupported claim of unaided manual execution is made.

4. **What changed, and why?**
   Two correctness decisions were corrected in separate audited records while
   preserving the original automatic results, all labels, and the frozen YAML.
   Integration added one prerequisite-aware setup path and a repeatable verifier.
   The verifier's PUT was corrected to satisfy the existing API, and its fixture
   lookup was changed to use the exact listing code so repeated runs work beyond
   the first 100 listings. Setup errors were sanitized, development hashes were bound to the freeze receipt, and live process revisions were bound to the checkout after independent code review. The measured semantic matching and Part 4 prompts,
   grader, lessons, test inputs and results were preserved. The report retains
   the observed 13/40 incorrect cached answers at threshold 0.85.
