# HW8 AI-use disclosure

## 1. What you used an AI assistant for and what you did yourself.

In completing this assignment, I used AI as an iterative assistant and reasoning partner. I supplied the assignment requirements, personal configuration, existing application, and scope for each part. I used it to organize modular requirements, explore implementation choices, debug edge cases, and test boundary conditions. Every piece of code and analysis was vetted, refactored, and validated manually to ensure accuracy and alignment with assignment specifications.

## 2. One unsuitable AI-produced output

An early AI-generated recovery test stopped as soon as the Writer produced an output. That left the commit order unverified. Publishing an output and committing the input offset are separate actions, so a crash between them can cause the same message to be delivered again.

## 3. How the problem was detected

I compared the publication and commit events for the same message. The first capture showed output_published but no offset_committed event. The response looked successful, but I checked whether the logs actually proved that processing happened before the commit. The missing event showed that the test had stopped too early to support that claim.

## 4. What changed and why it works now

The test now waits for the commit before stopping the Writer. I verified the rerun by following task offset 32 through the restart, then checking that output publication came before commit 33, the next offset to read. The replay test separately confirmed one final logical output. This checks recovery and duplicates, since committing after processing can still allow replay.
