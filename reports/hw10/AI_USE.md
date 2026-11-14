# HW10 AI use

## 1. What you used an AI assistant for and what you did yourself.

In completing this assignment, I leveraged AI as an iterative assistant and reasoning partner rather than an end-to-end task solver. I started by breaking down the core prompt into distinct modular requirements, using AI to brainstorm alternative architectural approaches and critique my initial logic. Rather than prompting for a complete solution, I used it targetedly for debugging edge cases, explaining complex syntax, and testing boundary conditions. Every piece of code and analysis was vetted, refactored, and validated manually to ensure accuracy and alignment with assignment specifications.

## 2. One AI-produced output that was wrong or unsuitable, or one thing you independently verified.

For case hw10-05, the G-Eval judge gave the Writer’s draft 2/5 because it said the draft had failed to answer whether listing S6102-R-9106 had at least two units available. The draft began with “No” and gave the correct count of one. My human score was 4/5.

## 3. How you detected the problem or verified the result.

The audit matched the three judge scores to my frozen label by case ID and checked the judge’s reason against the draft and the saved listing facts. The listing record confirmed one available unit. All three passes gave the same score for the same mistaken reason.

## 4. What you changed and why it works now.

The report keeps my original label alongside all three judge scores and uses the judge to flag cases for human review. Keeping the draft and the judge’s reason makes the disagreement easy to check. I would want independently rated examples of serious factual errors before using these scores to decide whether to deploy.
