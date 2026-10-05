# AIUSE

Pragya Apurva

## 1. What you used an AI assistant for and what you did yourself.

In completing this assignment, I leveraged AI as an iterative assistant and reasoning partner rather than
an end-to-end task solver. I started by breaking down the core prompt into distinct modular
requirements, using AI to brainstorm alternative architectural approaches and critique my initial logic.
Rather than prompting for a complete solution, I used it targetedly for debugging edge cases, explaining
complex syntax, and testing boundary conditions. Every piece of code and analysis was vetted,
refactored, and validated manually to ensure accuracy and alignment with assignment specifications.

## 2. One AI-produced output that was wrong/unsuitable, or one thing you independently verified.

One result I checked directly was how search_rentals handles whitespace-only input. MCP Inspector displayed a green “Success” label, but the returned object contained ok: false, data: null, and a validation error. The Inspector had successfully received a response, while the application had rejected the request. A screenshot of the green label alone would have been misleading.

## 3. How you detected the problem or verified the result.

I entered a whitespace-only query with a limit of 5 and ran the tool in MCP Inspector. I inspected the full response and compared it with the successful “Sunny Downtown Apartment” search. I captured both outputs from my local session. AI guidance helped me choose and interpret these checks; the screenshots record the results I observed.

## 4. What you changed and why it works now.

The revised report distinguishes a successful MCP exchange from a successful application operation. I also supplied my own VS Code captures to replace typed code excerpts and retained the actual outputs with their explanations. AI contributed implementation, test, and report drafts; my direct work included running the guided local checks, capturing evidence, and reviewing presentation choices. Clearer captions now explain why rejecting an invalid query is expected behavior.
