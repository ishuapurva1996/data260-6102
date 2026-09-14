# AI assistant use

## 1. What I used AI for and what I did myself

I used Codex to help interpret the assignment, compare the helper code with my existing application, implement and revise the web app and agent graph, run automated checks and local-model experiments, organize evidence, and prepare this report. Codex also helped capture screenshots and check the recorded results.

I supplied the assignment and project context, reviewed the plans, questioned design choices, and directed revisions. I also performed extensive UI validations and logic checks. For example, I questioned why the first interface only allowed updating listing ID 1 when the application should let a user edit other listings too.

## 2. One AI-produced result that was unsuitable

The initial Part 2 interface exposed an update form only for ID 1. That demonstrated the teacher's specific update example, but it was too restrictive for the general rental-listing interface. The backend already accepted other existing IDs.

## 3. How I detected the problem or checked the result

While reviewing the interface and its logic, I asked why editing was limited to ID 1. The distinction between the assignment's required example and the application's broader editing behavior showed that the interface could be improved. Codex inspected the route and frontend handler, then added automated tests for updating both ID 1 and ID 2, preserving other fields, cancelling, and retaining drafts after failed requests.

## 4. What changed and why it works now

At my direction, Codex added an Edit button to every listing. The editor identifies the selected record and prefills its title and address. Save sends the selected ID to the existing update endpoint; Cancel closes the editor without saving. This supports ordinary editing while still allowing the report to demonstrate the required ID-1 update. The final automated browser checks confirmed the selected-record behavior, including editing ID 2 after ID 1 was deleted.

The personal contribution statement above reflects the student's description supplied on September 14, 2026. Automated checks and model executions are attributed to the assistant-assisted workflow rather than presented as manual student actions.
