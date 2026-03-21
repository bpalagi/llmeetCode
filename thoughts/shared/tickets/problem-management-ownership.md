# [LLMEET-0004] Restrict problem edit/delete access by ownership

## Problem Statement

The app now supports editing and deleting problems from the product UI, but any logged-in user can currently manage any problem. That is too permissive for destructive lifecycle actions and makes it easy for one user to change or remove problems authored by someone else.

## Desired Outcome

Problem management actions should be limited to:
- the GitHub account `bpalagi`, and
- the GitHub account of the user who originally created the problem.

To support that behavior, the system should persist problem creator ownership data when a problem is created and enforce that ownership consistently across edit and delete flows.

## Context & Background

### Current State
- Problem authoring is currently gated only by login.
- Problem edit and delete routes do not enforce per-problem ownership.
- The `Problem` model does not currently persist who created a problem.
- GitHub-authenticated users already exist in the database through the existing OAuth flow, so there is a stable app-level user record available to reference.

### Why This Matters
- Edit and delete are high-impact actions and should not be open to every authenticated user.
- Problem ownership should be explicit so lifecycle management is predictable and auditable.
- The special-case maintainer access for `bpalagi` provides a simple bootstrap admin model without introducing a full role/permissions system.
- Persisting creator ownership now creates a foundation for future problem-management authorization features.

## Requirements

### Functional Requirements
- [ ] When a new problem is created, the app persists the creating user as that problem’s owner/creator.
- [ ] Existing problems support ownership data in a backward-compatible way, including migration/backfill behavior where needed.
- [ ] `bpalagi` can edit and delete any problem.
- [ ] A non-`bpalagi` user can edit and delete only problems they created.
- [ ] A logged-in user who is neither `bpalagi` nor the recorded creator cannot access edit or delete actions for a problem.
- [ ] Unauthorized users are blocked consistently on both the page routes and the form/action POST routes.
- [ ] The UI hides or disables edit/delete controls for unauthorized users rather than showing actions that fail only after click.
- [ ] Existing create, detail, catalog, dashboard, and codespace flows continue to work.

### Out of Scope
- Building a generalized RBAC/ACL system.
- Adding teams, multiple maintainers, or delegated ownership transfer.
- Supporting collaborative/shared ownership for a single problem.
- Adding a full audit log or moderation workflow.
- Changing who can create problems in this ticket.

## Acceptance Criteria

### Automated Verification
- [ ] Tests pass: `./run_tests.sh`
- [ ] App startup smoke check completes: `python -m app.main`

### Manual Verification
- [ ] A problem created by `bpalagi` can still be edited and deleted by `bpalagi`.
- [ ] A problem created by another logged-in user can be edited and deleted by that same user.
- [ ] A different logged-in user cannot see or use edit/delete actions for a problem they do not own.
- [ ] Unauthorized direct requests to edit/delete routes are rejected consistently.
- [ ] Existing non-management flows still behave as before.

## Technical Notes

### Affected Components
- `app/database.py` - persist problem creator ownership and add any required migration/backfill support
- `app/main.py` - enforce ownership checks on edit/delete routes and shape UI context for management permissions
- `app/templates/problem.html` - show management controls only when the current user is allowed to manage the problem
- `app/templates/index.html` - ensure any management affordances for inactive problems respect ownership rules
- `tests/test_main.py` - add route/UI coverage for authorized vs unauthorized edit/delete behavior
- `tests/test_database.py` - add persistence coverage for problem creator ownership behavior

---

## Meta

**Created**: 2026-03-21
**Priority**: High
**Estimated Effort**: M
