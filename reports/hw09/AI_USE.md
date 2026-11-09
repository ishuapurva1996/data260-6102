# HW9 AI-use disclosure

## 1. What you used an AI assistant for and what you did yourself.

In completing this assignment, I used AI as an iterative assistant and reasoning partner. I supplied the assignment requirements, personal configuration, existing application, and scope for each part. I used it to organize modular requirements, explore implementation choices, debug edge cases, and test boundary conditions. Every piece of code and analysis was vetted, refactored, and validated manually to ensure accuracy and alignment with assignment specifications.

## 2. One unsuitable AI-produced output

The keyword scorer AI helped build passed a cached answer to "What does a co-signer do on a rental lease?" The response explained what a lease is and mentioned tenant responsibilities. The co-signer’s role was missing.

## 3. How the problem was detected

The words "tenant" and "responsibilities" matched the keyword check. The rubric asked for the co-signer’s guarantee of rent or other obligations if the tenant fails to pay. Reading the full answer against that requirement exposed the gap.

## 4. What changed and why it works now

The audit recorded two corrected scores alongside the original results. At 0.80, recalculating the table raised the false-hit count from 16 to 17 out of 40 and added 300 seconds-equivalent to the estimated cost. The audit ties that change to the saved answer.
