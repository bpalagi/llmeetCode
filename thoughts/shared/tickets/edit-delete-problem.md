# [LLMEET-0003] Enable editing and deleting problems

## Problem Statement

The app now has a first-class flow for creating problems from the product UI, but once a problem is created there is no way to correct mistakes, refine the content, deactivate outdated material, or remove a bad entry without going back to the database or seed logic by hand.

That leaves the new authoring flow incomplete. A typo in the title, a broken template repository, stale overview copy, or an accidental duplicate problem still requires developer intervention instead of a normal product workflow.

## Desired Outcome

An authorized problem author can open an existing problem, edit its managed content from the app, and delete a problem when it should no longer exist.

The editing flow should feel like a natural extension of the current add-problem experience: pre-filled form data, clear validation, and a success path that makes it obvious what changed. The delete flow should be explicit and safe, with confirmation that prevents accidental destructive actions.

## Context & Background

### Current State

- The app supports creating problems through the add-problem flow, but there is no corresponding edit or delete UI.
- Problem content is persisted through `Problem` and related `ProblemSolutionSubmission` rows in `app/database.py`.
- Problem detail pages are rendered from `app/main.py` and `app/templates/problem.html`, but they do not expose management actions.
- The catalog in `app/templates/index.html` only supports browsing and launching problems.
- Codespace provisioning depends on `Problem.template_repo`, so incorrect problem data can break downstream workflows.

### Why This Matters

- Content quality depends on being able to fix mistakes after a problem is created.
- Problem libraries change over time; outdated or broken exercises should be removable from the product experience.
- A complete authoring system should support the full lifecycle of a problem, not just initial creation.
- Safe delete behavior matters because problems are referenced by other app data and should not leave the system in a broken state.

## Requirements

### Functional Requirements
- [ ] Logged-in users who are allowed to author problems can see clear management actions for existing problems.
- [ ] A user can open an edit flow for an existing problem from the product UI.
- [ ] The edit page reuses or closely matches the add-problem experience, with all existing values pre-populated.
- [ ] The edit flow supports updating the same managed problem fields introduced by the add-problem feature, including title, short description, difficulty, language, active status, detail summary, detail overview, domain specialization, template repository, and optional YouTube walkthrough content.
- [ ] Validation prevents invalid edits, including blank required fields and invalid template repository or YouTube input.
- [ ] If the problem id remains editable, validation prevents collisions with other existing problems; if it is intentionally immutable, the UI makes that obvious.
- [ ] Saving edits updates the persisted problem and the detail page/catalog reflect the new values immediately.
- [ ] A user can start a delete flow for an existing problem from the product UI.
- [ ] The delete flow requires explicit confirmation so a problem cannot be removed accidentally.
- [ ] Deleting a problem removes it from the catalog and prevents the detail page from being used as an active entry point.
- [ ] Deleting a problem also handles related app data safely, including any associated solution-submission records and any other database references that would otherwise become orphaned or break existing views.
- [ ] The delete flow does not attempt destructive cleanup of user-owned GitHub repositories or Codespaces as part of this ticket.
- [ ] The UX makes it obvious whether an edit or delete action succeeded.

### Out of Scope
- Building a full moderation system, approval queue, or role model beyond the current authoring gate.
- Version history, undo, drafts, or scheduled publishing.
- Bulk editing or bulk deletion of multiple problems at once.
- Redesigning problem ownership or adding per-problem ACLs.
- Deleting user-owned GitHub repositories or externally managed Codespaces.

## Acceptance Criteria

### Automated Verification
- [ ] Tests pass: `./run_tests.sh`
- [ ] App startup smoke check completes: `python -m app.main`

### Manual Verification
- [ ] From an existing problem, a logged-in author can open an edit page or edit mode.
- [ ] The edit form is pre-populated with the problem's current values.
- [ ] Submitting valid edits updates the problem in the catalog and detail page.
- [ ] Invalid edits show actionable validation errors and preserve entered values.
- [ ] The active/inactive state can be updated intentionally and the result is reflected in the product UI.
- [ ] Starting a delete action shows a clear confirmation step.
- [ ] Confirming delete removes the problem from the catalog.
- [ ] Opening the deleted problem's detail route no longer shows the problem as a usable entry point.
- [ ] Deleting a problem does not break pages that load related app data.
- [ ] The edit and delete controls are usable on both desktop and mobile screen sizes.

## Technical Notes

### Affected Components
- `app/main.py` - add edit/update/delete routes, validation updates, and success/error handling.
- `app/database.py` - support any relationship cleanup or persistence changes needed for safe delete behavior.
- `app/templates/problem.html` - surface edit/delete controls from the problem page.
- `app/templates/add-problem.html` or a new edit template - reuse the authoring form for editing existing problems.
- `app/templates/index.html` - add management affordances only if the catalog needs them.
- `tests/test_main.py` - cover edit access, validation, successful updates, delete confirmation, and removal behavior.
- `tests/test_database.py` - cover persistence updates, relationship cleanup, and delete safety.

### Implementation Notes
- Prefer reusing the existing authoring form structure and validation rules instead of creating a separate content model.
- Be explicit about whether `Problem.id` is editable; keeping it immutable may be the safest first iteration because other app records reference it.
- Treat delete as a data-integrity problem, not just a UI action; related records should be cleaned up or otherwise handled safely.
- Avoid workflows that trigger destructive GitHub-side cleanup of repos or codespaces.
- Keep the feature aligned with the current FastAPI + Jinja + PostgreSQL architecture and server-rendered UX.

---

## Meta

**Created**: 2026-03-21
**Priority**: High
**Estimated Effort**: M
