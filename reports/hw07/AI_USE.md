# AI use — Part 1 checkpoint

Pragya Apurva · DATA 260 · SID4 6102

## 1. What AI helped with and what I supplied

I supplied the assignment, execution plan, personal configuration, existing HW6
baseline and this session's Part 1 scope. The AI assistant inspected the existing
application, implemented the migration and JWT roles, updated frontend/HW6
clients, wrote and ran tests, reviewed the changes, and organized this evidence.
The commands and visual inspections described here were performed by the agent.
This account does not claim that I manually performed those checks. Later parts
and the final report remain pending.

## 2. One unsuitable AI-produced choice

The agent tried adding optional MCP packages to the web environment for a broad
historical test run. Their dependency requirements upgraded Starlette and other
packages away from the existing FastAPI web pins. That was unsuitable for the
shared web application.

## 3. How the problem was detected

Package compatibility checks and the failed integrated startup exposed the
conflict. The genuine outputs and failed attempts remain in `RUN_LOG.txt`.
Separate checks also distinguished absent optional packages from application
bugs instead of treating every historical suite as one compatible runtime.

## 4. What changed and why it works now

The conflicting optional packages were removed from the web environment and the
pinned HW7/web requirements were restored. MCP regression tests ran in the
existing dedicated MCP environment. The final web dependency check found all
88 packages compatible; the web suite passed 971 tests and the separate MCP suite
passed 156. Real HTTPS, MySQL, MongoDB, Ollama and browser checks then passed on
the committed application. This verifies the corrected environment without
claiming that the initial install or failed runs were successful.
