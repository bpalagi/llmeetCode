# Problem Management Ownership Implementation Plan

## Overview
Restrict problem edit and delete actions so they are no longer available to every logged-in user. New problems should persist their creator, legacy problems should be backfilled to `bpalagi`, and all management surfaces should consistently allow access only to either the recorded creator or the maintainer account `bpalagi`.

## Current State Analysis
- Problem creation, edit, and delete routes in `app/main.py` are gated only by `session["user_id"]`, so any authenticated user can manage any problem.
- `Problem` in `app/database.py` has no ownership field, so the app cannot currently determine who authored a problem.
- The app already has stable app-level `User` records created from the GitHub OAuth flow in `auth_callback`, and the session cookie stores both `user_id` and GitHub `login`.
- Management UI in `app/templates/problem.html` and the inactive-problem panel in `app/templates/index.html` key off `logged_in`, not per-problem authorization.
- The repository uses inline, idempotent schema changes in `app/database.py:_run_migrations()` rather than a separate migrations framework.
- Existing tests in `tests/test_main.py` and `tests/test_database.py` cover auth-only management behavior, but not ownership persistence or unauthorized-owner denial.

## Desired End State
- Every newly created problem stores the creating app user as its owner.
- Existing problems gain ownership support through a backward-compatible migration plus idempotent backfill behavior.
- Legacy problems are backfilled to the `User` whose GitHub login is `bpalagi`.
- `bpalagi` can edit and delete any problem, regardless of recorded creator.
- Any other logged-in user can edit and delete only problems whose recorded owner matches their app user.
- Logged-in users who are neither `bpalagi` nor the owner receive consistent authorization failures on both page routes and POST actions.
- Unauthorized users do not see edit/delete affordances in the UI.
- Existing create, catalog, detail, dashboard, completion, and codespace flows continue to work.

## What We're NOT Doing
- Building a generalized RBAC, ACL, or role-management system.
- Changing who is allowed to create problems; creation remains available to logged-in users.
- Supporting shared ownership, delegated ownership transfer, or multiple maintainers.
- Adding audit logging, moderation flows, or soft delete.
- Cleaning up GitHub repositories or Codespaces as part of problem deletion.

## Implementation Approach
Extend `Problem` with a nullable owner foreign key to `users.id`, then centralize management authorization in a small helper layer that treats `bpalagi` as a hard-coded maintainer override and otherwise checks creator ownership. Keep rollout compatible with existing databases by adding a manual migration and an idempotent startup backfill that assigns unowned legacy problems to `bpalagi` once that user exists in the local database. Reuse the app's current server-rendered patterns by computing permission booleans in route context and using those booleans to both gate routes and hide management controls.

## Phase 1: Add Ownership Persistence and Legacy Backfill

### Overview
Introduce the database representation for problem ownership and make existing installations safe to upgrade without manual intervention.

### Changes Required:
#### 1. Add creator ownership to `Problem`
**File**: `app/database.py`
**Changes**: Add a nullable `creator_user_id` column on `Problem` that references `users.id`, plus an ORM relationship back to `User`. Keep it nullable during rollout so older rows remain readable before backfill runs.

#### 2. Extend inline migration support
**File**: `app/database.py`
**Changes**: Add a new `_run_migrations()` step that creates the `creator_user_id` column and foreign-key relationship in the repository's existing manual migration style. Make the check idempotent so repeated startups remain safe.

#### 3. Add legacy ownership backfill
**File**: `app/database.py`
**Changes**: Add an idempotent backfill step in startup/seed logic that looks up the `User` row whose `login` is `bpalagi` and assigns that user to all problems whose `creator_user_id` is null. If `bpalagi` does not exist yet, skip the backfill cleanly so a later startup can complete it after that user logs in.

#### 4. Preserve seed-data compatibility
**File**: `app/database.py`
**Changes**: Keep the `slow-api` seed path compatible with the new ownership model. Do not require `bpalagi` to exist in order for the app to start; rely on the separate backfill path to populate ownership when possible.

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `./run_tests.sh`
- [x] App startup smoke check completes: `python -m app.main`

#### Manual Verification:
- [ ] Existing databases gain the ownership column without manual SQL.
- [ ] A database with a `bpalagi` user backfills existing unowned problems to that user.
- [ ] A database without a `bpalagi` user still starts successfully and leaves legacy rows readable until backfill can run later.

---

## Phase 2: Persist Ownership on New Problem Creation

### Overview
Make new problems record their creator immediately so future management decisions do not rely on backfill behavior.

### Changes Required:
#### 1. Attach the creating user on create
**File**: `app/main.py`
**Changes**: In `POST /problems/new`, set `Problem.creator_user_id` from `session["user_id"]` when building the new `Problem` row. Keep the existing validation, walkthrough sync, and redirect behavior unchanged aside from persisting ownership.

#### 2. Keep creation flow behavior stable
**Files**: `app/main.py`, `tests/test_main.py`
**Changes**: Preserve the current login requirement, active/inactive redirect behavior, and optional managed walkthrough creation so ownership becomes an additive change rather than a broader authoring rewrite.

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `./run_tests.sh`
- [x] Route tests confirm newly created problems persist `creator_user_id`

#### Manual Verification:
- [ ] Creating a problem while logged in records that user as the owner.
- [ ] Existing create success/error flows still behave as before.

---

## Phase 3: Centralize Management Authorization Rules

### Overview
Implement one consistent definition of who can manage a problem and apply it across all edit/delete routes.

### Changes Required:
#### 1. Add ownership-aware session helpers
**File**: `app/main.py`
**Changes**: Add a small helper to load the current authenticated `User` from session and another helper such as `can_manage_problem(user, problem)` that returns true when the user's login is `bpalagi` or the user's id matches `problem.creator_user_id`.

#### 2. Reuse the shared permission check on edit/delete GET routes
**File**: `app/main.py`
**Changes**: After the existing authentication gate on `GET /problems/{problem_id}/edit` and `GET /problems/{problem_id}/delete`, enforce ownership authorization before rendering the page. Use `403 Forbidden` for authenticated-but-unauthorized users and keep the current login redirect for unauthenticated users.

#### 3. Reuse the shared permission check on edit/delete POST routes
**File**: `app/main.py`
**Changes**: Apply the same permission helper to `POST /problems/{problem_id}/edit` and `POST /problems/{problem_id}/delete` so direct form submissions are blocked consistently, not just the page routes.

#### 4. Keep inactive-problem management support intact for authorized users
**File**: `app/main.py`
**Changes**: Preserve the existing ability to manage inactive problems by continuing to use a management lookup that ignores `is_active`, but only after ownership checks succeed.

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `./run_tests.sh`
- [x] Route tests cover owner access, `bpalagi` override access, unauthenticated redirects, and authenticated unauthorized `403` responses

#### Manual Verification:
- [ ] `bpalagi` can edit and delete any problem.
- [ ] A non-`bpalagi` creator can edit and delete their own problem.
- [ ] A different logged-in user cannot access edit/delete pages or submit edit/delete actions for someone else's problem.

---

## Phase 4: Make UI Management Controls Ownership-Aware

### Overview
Align the rendered UI with the new backend rules so unauthorized users do not see actions they cannot use.

### Changes Required:
#### 1. Add per-problem management context on the detail page
**Files**: `app/main.py`, `app/templates/problem.html`
**Changes**: Extend the detail-page context builder to include a boolean such as `can_manage_problem`. Update the detail template so the edit/delete block renders only when that boolean is true, while keeping completion and Codespace controls driven by their existing logic.

#### 2. Filter inactive-problem management affordances on the catalog page
**Files**: `app/main.py`, `app/templates/index.html`
**Changes**: Change the inactive-problem list so it only includes problems the current user is allowed to manage. Keep the panel hidden when the filtered list is empty, even if other inactive problems exist.

#### 3. Preserve current create affordances
**File**: `app/templates/index.html`
**Changes**: Leave the `Add a Problem` CTA login-gated as it is today, because creation permissions are not changing in this ticket.

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `./run_tests.sh`
- [x] Template tests confirm unauthorized users do not see edit/delete controls or inactive-problem management links

#### Manual Verification:
- [ ] Problem detail pages show management controls only for authorized users.
- [ ] The inactive-problems panel only lists problems the current user can manage.
- [ ] Authorized users still have clear edit/delete entry points for both active and inactive problems.

---

## Phase 5: Add Ownership and Authorization Regression Coverage

### Overview
Protect the rollout with persistence, route, and UI tests that reflect the final product rules instead of the current auth-only behavior.

### Changes Required:
#### 1. Add database ownership tests
**File**: `tests/test_database.py`
**Changes**: Add coverage for the new `creator_user_id` field, owner relationship behavior, and legacy backfill logic that assigns unowned problems to `bpalagi` when that user exists.

#### 2. Expand route tests for authorized and unauthorized management
**File**: `tests/test_main.py`
**Changes**: Add tests that verify:
- newly created problems persist the authenticated creator
- creators can edit/delete their own problems
- `bpalagi` can edit/delete problems created by others
- unrelated logged-in users receive `403` on edit/delete GET and POST routes
- unauthenticated users still get redirected to login

#### 3. Expand UI visibility tests
**File**: `tests/test_main.py`
**Changes**: Replace the current "any logged-in user sees management controls" expectation with ownership-aware assertions for the problem detail page and inactive-problem panel.

#### 4. Extend fixtures for multi-user scenarios
**File**: `tests/conftest.py`
**Changes**: Add simple fixture helpers for creating authenticated clients tied to different user identities, including a `bpalagi` client, so owner/non-owner/admin-style coverage stays readable.

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `./run_tests.sh`
- [x] App startup smoke check completes: `python -m app.main`

#### Manual Verification:
- [ ] Owner, non-owner, and `bpalagi` flows all behave exactly as specified.
- [ ] Existing browse, detail, completion, dashboard, and codespace flows do not regress.

---

## Testing Strategy
- Use `tests/test_database.py` for schema-level and backfill validation around `creator_user_id`, user relationships, and idempotent legacy ownership assignment.
- Use `tests/test_main.py` for end-to-end route coverage of create-owner persistence, edit/delete authorization, forbidden direct requests, and ownership-aware UI rendering.
- Update `tests/conftest.py` with reusable authenticated clients for at least three identities: problem owner, unrelated logged-in user, and `bpalagi`.
- Run `./run_tests.sh` as the primary verification path because it matches repository conventions and exercises the PostgreSQL-backed test suite.
- Run `python -m app.main` as a smoke check to validate that the migration/backfill path does not break startup.
- Perform manual checks for:
  - a legacy problem backfilled to `bpalagi`
  - a newly created problem owned by a non-`bpalagi` user
  - owner edit/delete success
  - non-owner hidden controls and `403` direct access
  - `bpalagi` override access to both active and inactive problems

## References
- Original ticket: `thoughts/shared/tickets/problem-management-ownership.md`
- Related plan: `thoughts/plans/add-problem-authoring-flow.md`
- Related plan: `thoughts/plans/edit-delete-problems.md`
- Main app routes: `app/main.py`
- Database models and migrations: `app/database.py`
- Problem detail template: `app/templates/problem.html`
- Catalog template: `app/templates/index.html`
- Route and model tests: `tests/test_main.py`, `tests/test_database.py`, `tests/conftest.py`
