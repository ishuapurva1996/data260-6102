# AI Assistant Use

## 1. What I used an AI assistant for, and what I did myself

I used an AI assistant to audit the repository against the assignment, suggest targeted fixes and tests, and help organize the report. I supplied the configuration and run evidence, checked suggestions against the rubric, and decided what to submit.

## 2. One item I independently verified

The audit flagged `box-sizing: box-block` in the CSS. I verified that it is invalid, so browsers ignored it and form controls could overflow on narrow screens.

## 3. How I detected or verified the problem

I inspected the source and loaded the page at 1280 px and 390 px widths. I then reran Node syntax validation and all 46 automated tests.

## 4. What I changed and why it works now

I changed it to `border-box` and added responsive `width` and `max-width` rules. Controls now remain inside the form, which stays centered on desktop and fits mobile without horizontal overflow.
