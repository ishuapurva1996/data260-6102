# AI assistant use

## 1. What I used AI for and what I did myself

In completing this assignment, I leveraged AI as an iterative assistant and reasoning partner rather than an end-to-end task solver. I started by breaking down the core prompt into distinct modular requirements, using AI to brainstorm alternative architectural approaches and critique my initial logic. Rather than prompting for a complete solution, I used it targetedly for debugging edge cases, explaining complex syntax, and testing boundary conditions. Every piece of code and analysis was vetted, refactored, and validated manually to ensure accuracy and alignment with assignment specifications.

## 2. One AI-produced result that was unsuitable

One unsuitable result was the AI-generated JavaScript browser test for deleting a rental listing in tests/browser_hw04_part1.cjs. The test called response.text() after the application had navigated back to the home page. The delete operation returns 204 No Content, so there was no response body needed to confirm success. Trying to read it after navigation caused the test to fail, even though the rental had been deleted.

## 3. How I detected the problem or checked the result

The problem appeared when Codex ran the Playwright browser test. The saved failure log reported that the response body was unavailable after navigation. This pointed to the test's attempt to read the response, rather than a failed delete operation. The failure cleanup also recorded 404 for the deleted rental. The failed run was kept, so the error could be compared with the corrected test and its saved results.

## 4. What changed and why it works now

The test was changed to check the 204 status and confirm that Content-Length was absent or zero. Further checked that the listing disappeared from the page and that requesting the same rental ID returned 404 Not Found. The saved results after the correction show this check passing. These checks confirm both the API response and the removal of the record without trying to read an unavailable response body.
