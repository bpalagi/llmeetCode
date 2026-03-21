# Add Problem Authoring Flow Implementation Plan

## Overview
Add a first-class, server-rendered problem authoring flow so a logged-in user can create a new LLMeetCode problem from the product UI instead of editing seed data or inserting rows manually. The flow should start from a prominent catalog entry point, guide the author through the required fields, validate invalid or incomplete input, persist the new problem in PostgreSQL, and make the new problem immediately available in the catalog and detail page.

## Current State Analysis
- The catalog route in `app/main.py` renders active `Problem` rows into `app/templates/index.html`, but there is no create route or authoring UI.
- `Problem` in `app/database.py` already stores `id`, `title`, `description`, `detail_summary`, `detail_overview`, `difficulty`, `language`, `template_repo`, and `is_active`, so the current schema covers much of the requested form.
- The schema does not currently store a problem-level domain specialization field, so that must be added if the authoring flow is going to persist it.
- The app already renders optional YouTube content on the detail page through related `ProblemSolutionSubmission` rows in `app/templates/problem.html`, but there is no productized flow for creating one during problem authoring.
- Codespace creation in `app/main.py` reads `Problem.template_repo` directly before calling the GitHub template-repo API, so missing or malformed template source data will break downstream provisioning.
- Authentication exists via GitHub OAuth and signed cookies, but there is no maintainer/admin model; for this implementation, authoring access will be granted to any logged-in user.
- The app has no existing HTML form workflow, no flash messaging system, and no inline validation-error template pattern, so the authoring page introduces a new server-rendered form pattern.
- Schema changes are handled by the manual `_run_migrations()` list in `app/database.py`, not by Alembic or a separate migrations directory.

## Desired End State
- Logged-in users can see and use an `Add a Problem` entry point from the catalog page.
- `GET /problems/new` renders a dedicated authoring page with clear guidance about each field and how template repos / optional YouTube content affect runtime behavior.
- `POST /problems/new` validates required data, rejects duplicate ids, rejects blank required fields, and returns actionable inline errors without silently failing.
- A successful submission creates a new `Problem` row and, when a YouTube URL is provided, creates an initial related `ProblemSolutionSubmission` row using the existing embed-normalization helper.
- The newly created problem appears in the catalog immediately and its detail page renders the authored summary, overview, domain specialization, and optional video content correctly.
- The flow remains aligned with the existing FastAPI + Jinja + PostgreSQL architecture and preserves current codespace, auth, and detail-page behavior.

## What We're NOT Doing
- Building a multi-step CMS, drafts workflow, review queue, or edit/delete management interface.
- Adding a separate maintainer/role system in this iteration; login alone is the gate for authoring.
- Supporting non-YouTube video hosting.
- Redesigning codespace provisioning away from the current `template_repo` model.
- Building bulk import or migration tools for large problem libraries.
- Reworking existing completion tracking or dashboard behavior beyond regression-safe adjustments.

## Implementation Approach
Introduce a classic server-rendered create flow with a dedicated GET page and POST handler, while reusing as much of the existing runtime model as possible. Keep `Problem` as the primary source of catalog/detail data, add only the missing persisted field for domain specialization, and map the optional YouTube field into the already-supported `ProblemSolutionSubmission` table instead of creating a second video concept. Implement validation in Python close to the route handler, re-render the form with submitted values and field-level errors on failure, and use redirect-after-success so refreshes do not resubmit the form. Keep migration logic consistent with the current manual SQL approach and add tests around both route behavior and persistence.

## Phase 1: Extend the Data Model for Authoring

### Overview
Add the minimum database support needed for the new authoring inputs while preserving the current catalog, detail page, and codespace flows.

### Changes Required:
#### 1. Add domain specialization to `Problem`
**File**: `app/database.py`
**Changes**:
- Add a nullable or required text column on `Problem` for the domain specialization / discipline description requested in the ticket.
- Name the field clearly enough that both server-side code and templates read as product language, for example `domain_specialization`.
- Keep existing problem fields unchanged so current catalog/detail rendering continues to work during rollout.

#### 2. Add schema migration support
**File**: `app/database.py`
**Changes**:
- Extend `_run_migrations()` with a new `ALTER TABLE problems ADD COLUMN ...` step for the new domain-specialization field.
- Preserve the current manual, idempotent migration style used for `detail_summary`, `detail_overview`, and `problem_solution_submissions`.

#### 3. Preserve optional video support through existing relational model
**File**: `app/database.py`
**Changes**:
- Reuse `ProblemSolutionSubmission` as the storage target for the optional author-supplied YouTube URL.
- Do not add a second video column to `Problem`; instead document and implement that the authoring flow can create a single initial submission row when a URL is supplied.
- Reuse `normalize_youtube_embed_url()` so problem detail pages keep using the same embed path as the existing `slow-api` example.

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `./run_tests.sh`
- [x] App startup completes with the new migration path: `python -m app.main`

#### Manual Verification:
- [ ] Existing databases gain the new problem field without manual SQL work.
- [ ] Existing seeded problems still load in the catalog and detail page.
- [ ] New problems can persist domain specialization data and optional video metadata without schema errors.

---

## Phase 2: Add Logged-In-Only Authoring Routes and Validation

### Overview
Create the backend flow for rendering the authoring page, validating submissions, persisting problems, and returning clear success or error states.

### Changes Required:
#### 1. Add route-level access control
**File**: `app/main.py`
**Changes**:
- Add `GET /problems/new` and `POST /problems/new` routes.
- Gate both routes to logged-in users using the existing session-cookie pattern from `dashboard()` and other authenticated endpoints.
- Redirect unauthenticated GET requests to `/auth/login` and reject or redirect unauthenticated POST requests consistently with the chosen UX.

#### 2. Add form parsing and validation helpers
**File**: `app/main.py`
**Changes**:
- Introduce a small helper or route-local validation block for authoring inputs.
- Validate required fields: problem id/slug, title, short description, difficulty, language, detail summary, detail overview, domain specialization, template repo, and active status input semantics.
- Validate problem id uniqueness against `Problem.id`.
- Validate that `template_repo` is present and non-blank because codespace creation depends on it.
- Validate the optional YouTube URL enough to reject blank/whitespace-only values and normalize supported YouTube formats through the existing helper.
- Normalize and trim text fields before persistence so duplicate ids and accidental whitespace do not produce inconsistent data.

#### 3. Add persistence flow
**File**: `app/main.py`
**Changes**:
- On valid submission, create a new `Problem` row using the authored data.
- If a YouTube URL is supplied, create one related `ProblemSolutionSubmission` row titled in a neutral, user-facing way such as `Problem walkthrough` or similar repository-consistent copy.
- Commit once for the full creation flow so the problem and optional video are created atomically.
- After success, redirect to the new problem detail page or back to the authoring page with a success signal; prefer redirecting to the detail page so the user can immediately inspect the result.

#### 4. Add form state rehydration and success messaging
**File**: `app/main.py`
**Changes**:
- Re-render `add-problem.html` with submitted values and field-specific errors when validation fails.
- Add a lightweight, route-scoped success message pattern for the new flow rather than introducing a global flash-message system unless it is clearly worth the extra scope.
- Ensure the template always receives the standard base context keys (`request`, `user`, `logged_in`) so the shared layout continues to work.

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `./run_tests.sh`
- [x] Route tests cover authenticated access, unauthenticated access, valid creation, duplicate ids, and invalid submissions

#### Manual Verification:
- [ ] Logged-in users can open the authoring page.
- [ ] Logged-out users are sent to login instead of seeing a broken or partial form.
- [ ] Invalid submissions show clear, inline guidance and preserve the user’s entered values.
- [ ] Valid submissions redirect to a clear success destination and do not create duplicate rows on refresh.

---

## Phase 3: Build the Dedicated Add-Problem Page

### Overview
Create a dedicated, responsive Jinja template that explains the required authoring inputs and supports inline validation feedback.

### Changes Required:
#### 1. Add a new template
**File**: `app/templates/add-problem.html`
**Changes**:
- Create a new server-rendered page extending `base.html`.
- Include a page title, introductory guidance, and grouped form sections for catalog metadata, detail-page content, codespace template source, and optional video content.
- Use a real HTML `<form method="post">` flow, which is new to this repo.

#### 2. Design the form fields around current runtime behavior
**File**: `app/templates/add-problem.html`
**Changes**:
- Include fields for:
  - problem id / slug
  - title
  - short description
  - difficulty
  - language
  - active status
  - detail summary
  - detail overview / body
  - domain specialization
  - template repo
  - optional YouTube URL
- Add explanatory helper text that makes it clear `template_repo` must point to a GitHub template repository with a `.devcontainer/devcontainer.json`.
- Add helper text that explains the optional YouTube link becomes embedded detail-page content.

#### 3. Support inline validation and mobile-friendly layout
**File**: `app/templates/add-problem.html`
**Changes**:
- Render field-level errors near the relevant inputs.
- Preserve submitted values after validation failures.
- Keep the layout usable on both desktop and mobile widths, consistent with the current Tailwind usage in the app.

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `./run_tests.sh`
- [x] Template tests confirm the authoring page renders expected guidance and form fields

#### Manual Verification:
- [ ] The page clearly explains each authoring field.
- [ ] The form is easy to use on desktop and mobile.
- [ ] Validation errors appear next to the right fields.
- [ ] The page makes template source and optional YouTube behavior obvious.

---

## Phase 4: Add the Catalog Entry Point and Detail-Page Rendering Updates

### Overview
Expose the new authoring flow from the main catalog and make sure newly authored fields show up correctly where users consume problems.

### Changes Required:
#### 1. Add an `Add a Problem` entry point to the catalog
**File**: `app/templates/index.html`
**Changes**:
- Add a visible `Add a Problem` button near the top of the catalog page.
- Only render the button for logged-in users because authoring is login-gated in this implementation.
- Place the button near the existing catalog header/filter area so it feels like part of the primary browsing experience rather than a hidden admin affordance.

#### 2. Pass any needed authoring CTA context from the home route
**File**: `app/main.py`
**Changes**:
- Reuse existing `logged_in` state already passed to `index.html`.
- Add any additional context only if needed for CTA copy or URL generation; avoid unnecessary new page-model complexity.

#### 3. Render newly authored fields on the detail page
**File**: `app/templates/problem.html`
**Changes**:
- Add a visible location for domain specialization so the authored discipline/focus area appears on the problem page.
- Preserve the current use of `detail_summary`, `detail_overview`, and solution submissions.
- Ensure newly created optional YouTube content appears automatically through the reused `ProblemSolutionSubmission` path.
- Avoid redesigning the whole page; extend the existing structure with the new metadata cleanly.

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `./run_tests.sh`
- [x] Endpoint/template tests confirm the home page includes the add-problem CTA for logged-in users

#### Manual Verification:
- [ ] The home page shows an `Add a Problem` button near the top for logged-in users.
- [ ] Clicking the button opens the dedicated add-problem page.
- [ ] After creation, the new problem appears in the catalog.
- [ ] The new problem’s detail page shows the authored summary, overview, domain specialization, and optional video content.

---

## Phase 5: Add Regression Coverage for Authoring and Persistence

### Overview
Protect the new authoring flow with focused test coverage across route behavior, validation, and database persistence.

### Changes Required:
#### 1. Add route and template tests
**File**: `tests/test_main.py`
**Changes**:
- Add tests for `GET /problems/new` when authenticated and unauthenticated.
- Add tests for successful `POST /problems/new` creation.
- Add tests for duplicate ids, missing required fields, blank template repo, and invalid/empty optional YouTube input behavior.
- Assert that successful creation makes the new problem reachable from `/` and `/problems/{problem_id}`.
- Assert that optional video creation results in embedded content on the detail page.

#### 2. Add database tests for new persistence rules
**File**: `tests/test_database.py`
**Changes**:
- Add coverage for the new `Problem` field.
- Add coverage that creating a problem with optional YouTube data produces a normalized embed URL in the related `ProblemSolutionSubmission` row.
- Add any needed integrity or persistence tests around duplicate ids and problem-to-video relationships.

#### 3. Update test fixtures if needed
**File**: `tests/conftest.py`
**Changes**:
- Keep the existing seeded problems working after the schema addition.
- Add fixture helpers only if they meaningfully reduce repetition in the new authoring tests.
- Avoid over-coupling tests to implementation details beyond the persisted fields and expected rendered output.

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `./run_tests.sh`
- [x] No regressions in existing catalog, detail, completion, dashboard, or codespace tests

#### Manual Verification:
- [ ] The new authoring flow works for both happy-path and validation-failure scenarios.
- [ ] Existing non-authoring flows still behave as before.

---

## Testing Strategy
- Use `tests/test_main.py` for end-to-end route coverage of the authoring page, access control, validation errors, successful creation, catalog visibility, and detail-page rendering.
- Use `tests/test_database.py` for persistence coverage of the new problem field and the optional YouTube-to-submission mapping.
- Use `./run_tests.sh` as the primary automated verification command because it exercises the PostgreSQL-backed test environment defined in `tests/conftest.py`.
- Run `python -m app.main` as a startup smoke check to verify the new migration path and template wiring do not break app boot.
- Perform manual checks for:
  - logged-in access to `/problems/new`
  - home-page CTA visibility
  - duplicate-id validation
  - missing-template-repo validation
  - creation with and without optional YouTube input
  - new problem appearance in the catalog and detail page
  - responsive behavior on desktop and mobile

## References
- Original ticket: `thoughts/shared/tickets/add-problem.md`
- Related ticket: `thoughts/shared/tickets/problem-page.md`
- Existing detail-page plan: `thoughts/plans/dedicated-problem-detail-page.md`
- Main app routes: `app/main.py`
- Database models and migrations: `app/database.py`
- Catalog template: `app/templates/index.html`
- Detail template: `app/templates/problem.html`
- Shared layout and JS actions: `app/templates/base.html`
