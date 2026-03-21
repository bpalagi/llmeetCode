# Dedicated Problem Detail Page Implementation Plan

## Overview
Add a dedicated problem detail page so users can open an individual exercise, read richer scenario context, watch solution-submission videos, and still use the same start/resume and completion actions they already have from the catalog. The first iteration centers on the `slow-api` problem and persists its richer content in PostgreSQL so the pattern can expand beyond hardcoded app data.

## Current State Analysis
- The catalog page in `app/main.py` renders all active problems from the `Problem` table into `app/templates/index.html`, but each item only exposes title, short description, difficulty, language, and action buttons.
- There is no server-rendered detail route for a single problem; `/problems/{problem_id}` is currently only used by completion APIs in `app/main.py`.
- `Problem` in `app/database.py` does not have fields for long-form overview content, and there is no related table for multiple solution submissions.
- The existing Codespace and completion flows already work and should be reused as-is from the new page.
- The shared `toggleComplete()` function in `app/templates/base.html` is coupled to the catalog-card DOM structure, so it will need to be generalized or wrapped for the detail page.
- `thoughts/shared/research/example-jira.md` contains the source scenario for `slow-api`, but nothing in the app surfaces that content today.

## Desired End State
- Users can click a problem from the catalog and land on `GET /problems/{problem_id}`.
- Every active problem has a detail page with basic metadata and the same primary actions available on the catalog.
- `slow-api` additionally shows DB-backed long-form overview content derived from `thoughts/shared/research/example-jira.md`.
- The detail page contains a solution submissions section backed by relational data so multiple videos can be added later without redesigning the schema.
- The provided YouTube URL is normalized into an embeddable URL and rendered in an iframe.
- Catalog and detail views both remain functional on desktop and mobile, and existing business logic for auth, Codespaces, and completion remains unchanged.

## What We're NOT Doing
- Redesigning GitHub auth, Codespace provisioning, or completion-state backend behavior.
- Building an admin UI for editing problem detail content or managing videos.
- Migrating every problem to rich content in this iteration.
- Adding user-submitted uploads or non-YouTube video hosting.
- Reworking the catalog beyond the minimum needed to support clickable navigation.

## Implementation Approach
Persist rich problem-page data in the database instead of app code. Extend `Problem` with nullable detail-content fields for long-form copy, and add a small related table for solution submission videos so the page can support multiple embeds cleanly. Keep the detail-page route and template thin by reusing the existing session-derived completion state and active Codespace lookup patterns from `home()` and `dashboard()`. Refactor the client-side completion UI hook just enough to support both the catalog card and the detail-page layout without changing the underlying completion endpoints.

## Phase 1: Extend the Data Model

### Overview
Add the database structure needed to store richer detail-page content and video submissions, then backfill the initial `slow-api` content.

### Changes Required:
#### 1. Problem content fields
**File**: `app/database.py`
**Changes**:
- Add nullable long-form content columns to `Problem` for detail-page rendering:
  - `detail_summary` (`Text`) for a short hero/intro summary on the detail page.
  - `detail_overview` (`Text`) for the main scenario context derived from the Jira-style research doc.
- Keep existing `description` unchanged so the catalog still uses its current short copy.

#### 2. Solution submission model
**File**: `app/database.py`
**Changes**:
- Add a new `ProblemSolutionSubmission` model/table with fields such as:
  - `id` primary key
  - `problem_id` foreign key to `problems.id`
  - `title`
  - `video_url`
  - `embed_url`
  - `sort_order`
  - `is_active`
  - `created_at`
- Add a relationship from `Problem` to `ProblemSolutionSubmission` ordered by `sort_order` then `id`.

#### 3. Lightweight migrations
**File**: `app/database.py`
**Changes**:
- Extend `_run_migrations()` to add the new `problems` columns when missing.
- Add migration logic to create the new solution-submissions table if it does not exist.
- Keep the migration style consistent with the existing lightweight, SQL-based migration approach.

#### 4. Seed and backfill initial detail data
**File**: `app/database.py`
**Changes**:
- Update `_seed_initial_data()` so fresh databases seed `slow-api` with `detail_summary` and `detail_overview` content based on `thoughts/shared/research/example-jira.md`.
- Add a seeded `ProblemSolutionSubmission` row for `slow-api` using the provided YouTube link and a normalized embed URL.
- Make the seeding idempotent so existing DBs get backfilled once without creating duplicates.

### Success Criteria:

#### Automated Verification:
- [ ] Tests pass: `./run_tests.sh`
- [x] App startup runs migrations cleanly: `python -m app.main`

#### Manual Verification:
- [ ] Existing databases gain the new fields/table without manual SQL steps.
- [ ] Fresh databases seed `slow-api` with detail content and one solution submission.
- [ ] Re-running startup does not duplicate the seeded video row.

---

## Phase 2: Add Problem Detail Route and View Model

### Overview
Create a dedicated server-rendered page for one problem while reusing current auth, completion, and Codespace-state derivation.

### Changes Required:
#### 1. Shared problem page context assembly
**File**: `app/main.py`
**Changes**:
- Add a small helper that builds per-user problem UI state for a single problem:
  - `is_completed`
  - `active_codespace_url`
  - `logged_in`
  - `user`
- Reuse existing session parsing and `list_user_codespaces()` behavior rather than duplicating business rules.

#### 2. Dedicated detail route
**File**: `app/main.py`
**Changes**:
- Add `GET /problems/{problem_id}` with `response_class=HTMLResponse`.
- Query only active problems and return 404 for unknown or inactive IDs.
- Load the related solution submissions for the page.
- Shape template data so the page can render generic fallback content for problems that do not yet have rich detail fields.
- Pass preprocessed overview paragraphs or sections into the template instead of forcing template-level text parsing.

#### 3. YouTube normalization helper
**File**: `app/main.py` or `app/database.py`
**Changes**:
- Add a helper that converts the provided live/share YouTube URL into a stable embed URL before persistence or render.
- Keep this helper narrow and deterministic so tests can assert the expected embed format.

### Success Criteria:

#### Automated Verification:
- [x] Route tests pass for known and unknown problem IDs
- [ ] Tests pass: `./run_tests.sh`

#### Manual Verification:
- [ ] Visiting `/problems/slow-api` renders successfully.
- [ ] Visiting an unknown problem ID returns a 404 page/response.
- [ ] Logged-in users see completion and Codespace state reflected correctly on the detail page.

---

## Phase 3: Make the Catalog Navigate to Detail Pages

### Overview
Turn the catalog into an entry point for individual problem pages without losing its current summary/action role.

### Changes Required:
#### 1. Clickable problem entries
**File**: `app/templates/index.html`
**Changes**:
- Convert the problem title into a link to `/problems/{{ problem.id }}`.
- Optionally make the description area or a dedicated “View details” affordance clickable as well, while keeping action buttons independent.
- Preserve the current action button behavior so opening/resuming Codespaces and marking completion still work directly from the catalog.

#### 2. Navigation clarity
**File**: `app/templates/index.html`
**Changes**:
- Add a clear visual hint that the card is now navigable to a detail page.
- Keep the current card layout intact enough that completion toggling and hide-completed behavior continue to work.

### Success Criteria:

#### Automated Verification:
- [x] Template-rendering tests assert the catalog contains `/problems/slow-api`
- [ ] Tests pass: `./run_tests.sh`

#### Manual Verification:
- [ ] Clicking `Slow API Performance` from `/` opens the detail page.
- [ ] Catalog action buttons still work without forcing a page navigation.

---

## Phase 4: Build the Detail Page Template

### Overview
Create a dedicated problem page that feels richer than the catalog, surfaces scenario context, and preserves existing primary actions.

### Changes Required:
#### 1. New problem detail template
**File**: `app/templates/problem.html`
**Changes**:
- Create a new template extending `base.html`.
- Add a back link to `/` near the top of the page.
- Render core metadata: title, difficulty, language, short summary, and short catalog description.
- Render the long-form overview in readable sections/paragraphs.
- Add a solution submissions section that loops over related video records and embeds each one with responsive iframe markup.
- Include a clear empty state when a problem has no submissions yet.

#### 2. Action block reuse
**File**: `app/templates/problem.html`
**Changes**:
- Render the same primary actions the catalog exposes:
  - Resume Codespace if one exists
  - Otherwise open in Codespaces
  - Mark complete / completed toggle when logged in
- Keep guest behavior consistent with the catalog by redirecting unauthenticated users to login when starting work.

#### 3. Completion UI compatibility
**File**: `app/templates/base.html`
**Changes**:
- Refactor `toggleComplete()` so it can update both:
  - the existing catalog-card markup, and
  - a single-problem detail-page action state
- Prefer a small data-attribute-based target lookup over the current hardcoded catalog selectors.
- Preserve hide-completed behavior on the catalog while avoiding detail-page-specific regressions.

### Success Criteria:

#### Automated Verification:
- [x] Response text/context tests cover overview content and embed rendering
- [ ] Tests pass: `./run_tests.sh`

#### Manual Verification:
- [ ] `/problems/slow-api` shows the richer Jira-derived context.
- [ ] The provided YouTube example is embedded and viewable.
- [ ] The page layout works on desktop and mobile.
- [ ] Users can navigate back to the catalog easily.

---

## Phase 5: Test Coverage and Regression Protection

### Overview
Add focused tests around the new route, schema-backed content, and cross-page action behavior.

### Changes Required:
#### 1. Endpoint and template tests
**File**: `tests/test_main.py`
**Changes**:
- Add tests for `GET /problems/{problem_id}`:
  - success for `slow-api`
  - 404 for unknown problem
  - correct context for completion state
  - correct rendering of embed URL or iframe markup
- Add tests that the catalog includes detail-page links.
- Add tests that problems without rich detail content still render a usable detail page.

#### 2. Test fixtures and seed expectations
**File**: `tests/conftest.py`
**Changes**:
- Extend seeded test problems with detail-page fields where needed.
- Seed at least one `ProblemSolutionSubmission` for `slow-api` in test setup, or rely on app seeding consistently.

#### 3. Database model tests
**File**: `tests/test_database.py`
**Changes**:
- Add coverage for the new `ProblemSolutionSubmission` relationship.
- Add tests that detail content fields persist correctly.
- Add an idempotency test for whichever helper is responsible for seeding/backfilling video rows.

### Success Criteria:

#### Automated Verification:
- [ ] Tests pass: `./run_tests.sh`
- [x] No existing tests regress around dashboard, completion, or Codespace flows

#### Manual Verification:
- [ ] The feature works for both authenticated and unauthenticated users in expected ways.
- [ ] Existing dashboard and catalog flows still behave as before.

---

## Testing Strategy
- Use endpoint tests in `tests/test_main.py` to verify the new detail route, 404 handling, template context, and catalog-to-detail linking.
- Use database tests in `tests/test_database.py` to verify the new schema, relationships, and idempotent seed/backfill logic.
- Keep `./run_tests.sh` as the primary automated verification path because it exercises the real PostgreSQL-backed test setup.
- Run `python -m app.main` as a startup smoke test to validate migration execution against the current lightweight migration system.
- Perform manual checks for:
  - clicking from catalog to detail page
  - starting/resuming Codespaces from the detail page
  - toggling completion from the detail page
  - embedded video visibility
  - responsive layout on mobile and desktop widths

## References
- Original ticket: `thoughts/shared/tickets/problem-page.md`
- Source research: `thoughts/shared/research/example-jira.md`
- Routing and current catalog flow: `app/main.py`
- Existing catalog template: `app/templates/index.html`
- Shared client-side actions: `app/templates/base.html`
- Existing dashboard page model: `app/templates/dashboard.html`
