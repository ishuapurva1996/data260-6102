# AI assistant use

## 1. What I used AI for and what I did myself

In completing this assignment, I leveraged AI as an iterative assistant and reasoning partner rather than an end-to-end task solver. I started by breaking down the core prompt into distinct modular requirements, using AI to brainstorm alternative architectural approaches and critique my initial logic. Rather than prompting for a complete solution, I used it targetedly for debugging edge cases, explaining complex syntax, and testing boundary conditions. Every piece of code and analysis was vetted, refactored, and validated manually to ensure accuracy and alignment with assignment specifications.

## 2. One AI-produced result that was unsuitable

During development, an early draft of the Part 2 verification code checked the vectors and similarity scores, but did not fully check that the saved results matched the committed questions and experiment settings. A changed question or requested result count (k) could therefore go unnoticed. The actual experiment used the correct questions.

## 3. How I detected the problem or checked the result

I identified missing comparisons between the saved results and committed inputs. Codex added tests that deliberately change the question, expected source, requested result count and configuration to check that the verifier rejects these mismatches.

## 4. What changed and why it works now

I updated the verifier to compare the saved results with the committed questions and settings. Additional tests confirmed that it rejected the altered records. The verifier now checks both the calculations and whether the results belong to the intended experiment.

The local model in Part 2 converts text into vectors for retrieval. It does not generate answers to the five questions.
