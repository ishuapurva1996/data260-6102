---
title: "feat: HW4 Part 1 React rental client"
date: 2026-09-27
type: feat
artifact_contract: ce-unified-plan/v1
product_contract_source: course-assignment
execution: code
---

# HW4 Part 1: React rental client

## Goal Capsule

**Objective:** A logged-in user can view, create, update and delete rental listings through the required browser screens, with changes saved by the existing backend.

**Means:** React components and React Router, following the [shared contract](2026-09-27-1715-hw4-shared-contract.md).

**Authority:** User instructions and HW4 PDF → shared contract → this plan. Execute only Part 1 and its evidence. Part 2 owns the backend and final Parts 1–3 integration. Complete local commits and a handoff; do not publish, deploy or tag a submission.

---

## Product Contract

### Summary

Replace the active rental interface with React while preserving the rental domain and existing create validation. Connect it to Part 2's authenticated MySQL-backed API.

### Problem Frame

HW3 already had CRUD controls in HTML/Jinja and ordinary JavaScript. HW4 requires those interactions to be organized into React components, with navigation, props, hooks and email/password login.

### Requirements

| ID | Required result | Assignment source |
| --- | --- | --- |
| R1 | `Login.jsx` submits email/password and uses the backend's HTTP-only session cookie. | Part 1 introduction |
| R2 | `Home.jsx` displays records at `/`; signed-out users see Login required and cannot reach protected record screens. | Part 1 I/V |
| R3 | `CreateRecord.jsx` at `/create` receives a mutation prop, submits valid fields, uses the server-assigned ID, and returns home after success. | Part 1 II |
| R4 | `UpdateRecord.jsx` at `/update` edits the selected listing title/address through its mutation prop, persists through the API, and returns home. | Part 1 III |
| R5 | `DeleteRecord.jsx` at `/delete` identifies the selected record, invokes its mutation prop, deletes through the API and returns home. | Part 1 IV |
| R6 | Use `react-router-dom`, `useState` and `useEffect` where needed; support loading, empty, error and expired-session states. | Part 1 V and integration |
| R7 | Capture each required screen/action with relevant code and real output, recording actual AI assistance and independent checks. | Submission instructions |

### Scope Boundaries

Own the frontend and Part 1 checks/evidence. MySQL models, sessions, backend endpoints and benchmark logic belong to Parts 2 and 3. No RAG interface is included. Temporary mocks are development aids only; acceptance requires the real backend and MySQL.

---

## Planning Contract

### Key Technical Decisions

- KTD1. Use `frontend/` as a shared root-level frontend folder, not an HW4 application copy. Adapt the provided demo's component pattern to rentals and the shared API.
- KTD2. Preserve all six current create fields. The assignment's two domain fields remain prominent; update edits those two only. This avoids sending an invalid two-field body to the existing validated domain model.
- KTD3. Use `/update?id=N` and `/delete?id=N` so the page paths exactly match the assignment. A missing or invalid ID produces a useful state and no mutation.
- KTD4. Keep API calls and authentication state in shared frontend modules; mutation props connect page components to API operations. Reload data from the server after mutation before presenting the updated list.
- KTD5. Use the cookie through credentialed requests and recheck identity on refresh. Do not treat a local loggedIn flag as proof of authentication.

### Dependencies and ownership

Follow the shared contract's branch/foundation protocol. U1 and most of U2 can proceed immediately against clearly labeled mocks. U3 requires Part 2 foundation B. Final browser evidence requires real MySQL and coordinated port 8702 access. Part 2 serves the built assets; Part 1 supplies `frontend/dist` as a build output, not a separately deployed service.

The backend baseline uses special imports because `code` is a Python module name; this session must not reorganize it. Preserve the existing root Node test setup by using the frontend's own manifest and lockfile.

---

## Implementation Units

### U1. Create the React application and navigation

**Goal:** Required URLs render the correct components. **Requirements:** R2–R6. **Dependencies:** Shared contract only.

**Files:** `frontend/package.json`, `frontend/package-lock.json`, `frontend/index.html`, `frontend/vite.config.js`, `frontend/src/main.jsx`, `frontend/src/App.jsx`, `frontend/src/pages/*.jsx`, `frontend/src/components/`, `frontend/src/styles.css`, `tests/browser_hw04_part1.cjs`.

**Approach:** Build the route/component structure and domain navigation. Use accessible labels, sensible focus behavior and responsive forms. Follow the starter's React patterns without copying its user-management labels, user-ID login, node_modules or virtual environments. Preserve useful existing search and delete-highest behavior after required screens work.

**Test scenarios:**
- Each specified URL renders the intended screen; update/delete retain the selected ID after refresh.
- Signed-out navigation and direct visits display Login required and hide protected data.
- Missing IDs, an empty list and a narrow viewport remain usable.

**Verification:** Frontend builds and browser checks verify route and screen behavior. Mock-based checks are labeled as such.

### U2. Implement forms, state and API callbacks

**Goal:** User actions follow the agreed request contract. **Requirements:** R1, R3–R6. **Dependencies:** U1.

**Files:** `frontend/src/api/`, `frontend/src/auth/`, required page components, `frontend/src/App.jsx`, `tests/browser_hw04_part1.cjs`.

**Approach:** Centralize request/error handling. Pass create/update/delete callbacks as props. Prevent duplicate submissions, retain values on errors and navigate home only after success. Display a deliberate delete confirmation with record title/address. Handle 204 without attempting to parse JSON. Abort or ignore stale loads when routes change.

**Test scenarios:**
- The create request carries all six fields; update changes only title/address; delete targets the selected ID.
- A 422 error preserves inputs and explains the invalid fields; network failure does not show success.
- A repeated submit while waiting sends no duplicate mutation.
- A 401 removes stale protected content and requires login; refreshing rechecks identity.

**Verification:** Browser checks inspect outgoing requests and resulting UI states, with a clear distinction between mocks and real API calls.

### U3. Connect to the real backend and capture evidence

**Goal:** Prove the browser workflow reaches MySQL. **Requirements:** R1–R7. **Dependencies:** U2 and Part 2 foundation B.

**Files:** Frontend integration adjustments, `tests/browser_hw04_part1.cjs`, `reports/hw04/part1/REPORT_SECTION.md`, `RUN_LOG.txt`, `AI_USE.md`, `HANDOFF.md` in the same part directory, plus `reports/hw04/raw/part1/` and `reports/hw04/screenshots/part1/`.

**Approach:** Merge the foundation commit, build the frontend, and coordinate a real backend/database run. Exercise login, create, read, update, delete, logout and expiry through the browser. Confirm the ID comes from MySQL. Verify a stored change after browser refresh and backend restart using the documented session lifetime. Supply Part 2 with the build and evidence commands and actual results.

**Test scenarios:**
- Valid login allows CRUD; invalid login and direct unauthenticated API requests do not.
- A created/edited listing survives backend restart; a deleted listing stays absent.
- Fresh direct navigation to every frontend route works on the final port; an unknown API URL returns an API error rather than the React HTML.
- The browser receives an HTTP-only cookie but cannot read its value through JavaScript.

**Verification:** Record real end-to-end outcomes and screenshots for login, signed-out state, home, and each mutation with its updated home result. Pair screenshots with relevant code. Mark missing manual captures explicitly.

---

## Verification Contract

Verify the frontend production build, route/form tests, and the real HTTPS browser-to-FastAPI-to-MySQL flow. Use the repository's Playwright approach with a dedicated HW4 runner. Do not run old report-refresh scripts or overwrite older homework evidence. Existing HW2/HW3 browser selectors may need replacement because the active interface intentionally changes.

The handoff distinguishes checks passed with mocks from checks passed against MySQL, lists exact reproducible commands established during execution, and records any final port-8702 evidence still needed. A build alone does not prove Part 1 complete.

## Definition of Done

All R1–R7 are satisfied or any externally blocked capture is clearly listed. Required components, props, hooks and route behavior are visible in code. No mock data silently remains in the normal runtime. Own changes are committed on the assigned branch; generated dependencies and secrets are excluded. Publish the shared handoff with commit hash, imported foundation hash, changed files, passed checks, artifact locations and any pending integration. Remove abandoned experimental frontend code.
