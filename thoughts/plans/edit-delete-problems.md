# Edit and Delete Problems Implementation Plan

## Overview
Add a first-class management flow for existing problems so a logged-in authoring user can correct problem content, toggle visibility, and permanently delete a problem from the product UI without touching seed data or the database manually. The implementation should feel like a direct extension of the current add-problem flow, keep validation and templates consistent, and treat deletion as a data-integrity operation that fully removes dependent database records while explicitly avoiding GitHub-side cleanup.

## Current State Analysis
- The app already supports problem creation through `GET /problems/new` and `POST /problems/new` in `app/main.py`, with shared server-rendered validation and form rehydration.
- The existing authoring gate is only “logged in user”; there is no separate maintainer role or per-problem ownership model in `app/database.py`.
- The problem detail page at `GET /problems/{problem_id}` only loads active problems, so inactive problems cannot currently be viewed or used as an edit entry point.
- `app/templates/add-problem.html` already contains the full editable field set needed for an edit flow, including active status, template repo, and optional YouTube walkthrough input.
- `Problem.id` is the primary key and is referenced by `ProblemSolutionSubmission`, `UserRepo`, and `CodespaceToken`, while `CompletedProblem` stores `problem_id` as a plain string. Renaming the problem id would ripple across runtime flows and historical records.
- `Problem` deletion is not currently safe to do with a bare ORM delete because the schema does not define cascade delete behavior for problem-owned records.
- The detail page and catalog do not currently expose edit/delete controls, and the only destructive UX pattern in the app today is a JavaScript confirm dialog for codespace deletion on `app/templates/dashboard.html`.

## Desired End State
- Logged-in users who can currently author problems can open an edit flow for an existing problem from the UI.
- `GET /problems/{problem_id}/edit` renders a pre-populated authoring form that closely matches the add-problem experience.
- `POST /problems/{problem_id}/edit` validates the same managed fields as creation, preserves user-entered values on failure, and updates the existing problem on success.
- `Problem.id` is explicitly immutable in this first iteration, and the UI makes that constraint clear.
- Updating the optional walkthrough field keeps the single author-managed “Problem walkthrough” submission in sync instead of creating duplicates on every edit.
- The detail page and catalog reflect updated problem values immediately after save.
- Deleting a problem requires an explicit confirmation step and then hard-deletes the problem plus all known database references: `ProblemSolutionSubmission`, `UserRepo`, `CodespaceToken`, and `CompletedProblem` rows for that problem.
- Deleted problems disappear from the catalog, and their existing detail routes stop functioning as usable entry points.

## What We're NOT Doing
- Adding a new role model, moderation system, approval queue, or per-problem ACLs.
- Making `Problem.id` editable in this iteration.
- Preserving historical completion, repo, or token records after delete.
- Triggering destructive cleanup of user-owned GitHub repositories or Codespaces as part of problem deletion.
- Adding version history, undo, soft delete, drafts, or scheduled publishing.
- Building bulk edit or bulk delete workflows.

## Implementation Approach
Reuse the current add-problem architecture instead of introducing a separate management subsystem. Extract the existing validation and form-rendering patterns into mode-aware helpers that support both create and edit flows with minimal duplication. Keep problem ids immutable to avoid high-risk cross-table renames. For delete, prefer a dedicated server-rendered confirmation page or in-page confirmation form over a pure JavaScript confirm so the destructive path is explicit, testable, and consistent with the app’s server-rendered model. Perform hard delete as an ordered database cleanup operation inside one transaction so all related rows are removed together and no orphaned references remain.

## Phase 1: Shared Authoring and Management Foundations

### Overview
Refactor the existing authoring flow just enough to support editing existing problems without duplicating validation or template wiring, and formalize the key constraints for management behavior.

### Changes Required:
#### 1. Make authoring helpers mode-aware
**File**: `app/main.py`
**Changes**: Extract or extend the current `render_add_problem_template()` and `validate_problem_authoring_form()` helpers so they can support both create and edit routes. Allow validation to accept the current problem id when editing so uniqueness checks only reject collisions with other problems.

#### 2. Formalize immutable problem-id behavior
**File**: `app/main.py`
**Changes**: Treat the route parameter problem id as the source of truth during edits. Either omit `problem_id` from editable POST handling or render it as a read-only/disabled field with explanatory copy so authors understand that the slug cannot be changed.

#### 3. Add management-oriented lookup helpers
**File**: `app/main.py`
**Changes**: Add a helper for loading a problem for edit/delete management that does not require `is_active == True`, because inactive problems still need to be editable and deletable by an authorized logged-in user.

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `./run_tests.sh`
- [x] Validation tests cover create vs edit uniqueness behavior

#### Manual Verification:
- [ ] The codebase has one coherent validation path for both create and edit flows.
- [ ] Authors cannot accidentally change a problem slug during edit.

---

## Phase 2: Implement the Edit Problem Flow

### Overview
Add server-rendered edit routes that reuse the existing authoring UX while supporting pre-populated fields, inline validation, and clear save outcomes.

### Changes Required:
#### 1. Add edit page route
**File**: `app/main.py`
**Changes**: Add `GET /problems/{problem_id}/edit`, require a logged-in session, load the target problem even if inactive, and render the authoring template with the current problem values pre-filled.

#### 2. Add update route
**File**: `app/main.py`
**Changes**: Add `POST /problems/{problem_id}/edit`, validate the submitted fields, update the existing `Problem` record, and redirect after success using query-param-based status messaging consistent with the current create flow.

#### 3. Keep walkthrough submission in sync
**Files**: `app/main.py`, `app/database.py`
**Changes**: Define deterministic behavior for the optional YouTube walkthrough field during edit:
- if a walkthrough URL is provided and the managed walkthrough row already exists, update it;
- if a walkthrough URL is provided and no managed walkthrough exists, create it;
- if the walkthrough field is cleared, remove the managed walkthrough row.
Keep this limited to the author-managed “Problem walkthrough” entry rather than attempting to manage arbitrary future submissions.

#### 4. Support inactive-save outcomes clearly
**Files**: `app/main.py`, `app/templates/problem.html`, `app/templates/add-problem.html`
**Changes**: If an edited problem remains active, redirect back to its detail page with an update-success banner. If it is saved inactive, redirect to the edit page with a clear message explaining that the problem is hidden from the catalog.

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `./run_tests.sh`
- [x] Route tests cover authenticated edit access, unauthenticated redirect, successful updates, invalid edits, inactive saves, and YouTube walkthrough updates/removal

#### Manual Verification:
- [ ] An existing problem opens in a pre-populated edit form.
- [ ] Invalid edits show inline errors and preserve the submitted values.
- [ ] Valid edits update the detail page and catalog immediately.
- [ ] Toggling active/inactive changes product visibility intentionally and predictably.

---

## Phase 3: Add Management UI to Problem Surfaces

### Overview
Expose edit and delete affordances in the existing server-rendered UI so problem lifecycle actions are discoverable but still clearly separate from candidate-facing actions.

### Changes Required:
#### 1. Add management controls to the detail page
**File**: `app/templates/problem.html`
**Changes**: Add edit and delete controls to the existing action panel for logged-in users, keeping them visually separate from Codespace and completion actions. Ensure the controls work cleanly on mobile and desktop widths.

#### 2. Add optional catalog management affordance only if needed
**Files**: `app/templates/index.html`, `app/main.py`
**Changes**: Keep the catalog focused on browsing unless research during implementation shows that inactive problems need an additional discoverability path. Prefer detail-page entry as the primary edit/delete surface unless a missing inactive-problem path forces a small catalog-level addition.

#### 3. Add success/error status messaging
**Files**: `app/main.py`, `app/templates/problem.html`, `app/templates/add-problem.html` or replacement shared template
**Changes**: Reuse the app’s existing top-of-page banner pattern for “updated successfully”, “saved as inactive”, and post-delete confirmation destinations where appropriate.

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `./run_tests.sh`
- [x] Template/route tests assert management controls are present for logged-in users where expected

#### Manual Verification:
- [ ] Logged-in authors can find edit and delete actions from an existing problem.
- [ ] The controls remain usable on mobile and desktop layouts.
- [ ] Success messages make the outcome of edit actions obvious.

---

## Phase 4: Implement Safe Hard Delete

### Overview
Add an explicit, irreversible delete flow that removes a problem and all related database references without touching external GitHub resources.

### Changes Required:
#### 1. Add explicit confirmation flow
**Files**: `app/main.py`, `app/templates/problem.html`, `app/templates/add-problem.html` or new delete-confirmation template
**Changes**: Add a dedicated confirmation step for delete, preferably as a server-rendered page or confirmation form rather than only a JavaScript prompt. The confirmation UI should state clearly that the delete is permanent and that GitHub repos/codespaces are not being cleaned up.

#### 2. Add ordered database cleanup logic
**Files**: `app/main.py`, `app/database.py`
**Changes**: Before deleting the `Problem` row, explicitly remove all known problem-linked records:
- `ProblemSolutionSubmission`
- `UserRepo`
- `CodespaceToken`
- `CompletedProblem`
Then delete the `Problem` row and commit once so the delete is atomic from the app’s perspective.

#### 3. Preserve runtime safety after delete
**File**: `app/main.py`
**Changes**: Ensure deleted problems no longer render in the catalog or detail route. Keep dashboard and other views resilient when historical data disappears because the cleanup removes all known references up front.

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `./run_tests.sh`
- [x] Route and database tests cover confirmation requirements, successful delete, dependent-row cleanup, and deleted-route behavior

#### Manual Verification:
- [ ] Starting delete requires an explicit confirmation step.
- [ ] Confirming delete removes the problem from the catalog.
- [ ] Visiting the deleted problem route no longer shows a usable problem page.
- [ ] Dashboard and related pages continue to load without orphaned-data issues.

---

## Phase 5: Add Regression Coverage

### Overview
Protect the new lifecycle flows with focused coverage for server-rendered UX, validation, and hard-delete integrity.

### Changes Required:
#### 1. Extend route and UI tests
**File**: `tests/test_main.py`
**Changes**: Add tests for edit-page auth, pre-populated form rendering, successful updates, validation failures, inactive edit behavior, management controls on the detail page, delete confirmation, successful delete, and 404 behavior after deletion.

#### 2. Add persistence and cleanup tests
**File**: `tests/test_database.py`
**Changes**: Add coverage for edit persistence, walkthrough row update/removal behavior, and hard-delete cleanup across all affected tables.

#### 3. Adjust fixtures only where necessary
**File**: `tests/conftest.py`
**Changes**: Add any minimal fixture data needed to exercise dependent records such as completions, codespace tokens, or user repos tied to a deletable problem, while keeping the test setup readable and isolated.

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `./run_tests.sh`
- [x] App startup smoke check completes: `python -m app.main`

#### Manual Verification:
- [ ] The full create, edit, inactive, and delete lifecycle works end to end.
- [ ] Existing browse, detail, completion, dashboard, and codespace flows do not regress.

---

## Testing Strategy
- Use `tests/test_main.py` for end-to-end route coverage of edit access, form prefill, validation errors, successful updates, inactive save behavior, delete confirmation, and deleted-route behavior.
- Use `tests/test_database.py` for direct persistence checks around walkthrough synchronization and hard-delete cleanup of related rows.
- Use `./run_tests.sh` as the primary verification command because the repo’s preferred path exercises the PostgreSQL-backed test setup.
- Run `python -m app.main` as a smoke check to validate route wiring and any migration-safe database changes.
- Perform manual checks for:
  - editing an active problem
  - editing an inactive problem
  - clearing and replacing the optional walkthrough URL
  - hiding a problem by setting it inactive
  - permanently deleting a problem with related records present
  - confirming the controls work on mobile and desktop layouts

## References
- Original ticket: `thoughts/shared/tickets/edit-delete-problem.md`
- Related plan: `thoughts/plans/add-problem-authoring-flow.md`
- Related plan: `thoughts/plans/dedicated-problem-detail-page.md`
- Main app routes: `app/main.py`
- Database models and lightweight migrations: `app/database.py`
- Authoring template: `app/templates/add-problem.html`
- Problem detail template: `app/templates/problem.html`
- Catalog template: `app/templates/index.html`
- Existing route and model tests: `tests/test_main.py`, `tests/test_database.py`
