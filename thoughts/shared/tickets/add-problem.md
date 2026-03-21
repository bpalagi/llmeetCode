# [LLMEET-0002] Add problem authoring flow

## Problem Statement

The app currently assumes problems are created directly in code or seeded in the database. That works for bootstrapping a small catalog, but it makes adding a new exercise slow, error-prone, and dependent on developer knowledge of the schema and seed patterns.

We need a first-class way to start authoring a new problem from the product itself, beginning with a prominent "Add a Problem" entry point on the main page and clear guidance for all of the information required to make a problem usable in LLMeetCode.

## Desired Outcome

An authorized maintainer can click an "Add a Problem" button from the top of the problem catalog, open a dedicated authoring page, and create a new problem with all core metadata required by the app.

The authoring flow should explain what each field is for, especially the inputs that shape the problem page itself, including the problem's domain specialization, optional YouTube content for problem creation or walkthrough context, and the template source that a Codespace should open for that problem.

## Context & Background

### Current State

- The main catalog in `app/templates/index.html` only supports browsing existing problems.
- Problem records are currently modeled in `app/database.py` and rendered through `app/main.py`, but there is no UI for creating new ones.
- Codespace creation depends on each problem having a valid template source via `Problem.template_repo`.
- Rich problem-page content already exists for individual problems through fields like `detail_summary`, `detail_overview`, and related video records, but those values are still populated outside a productized authoring flow.

### Why This Matters

- Adding new exercises should not require a developer to manually edit seed logic or database rows for every problem.
- A guided authoring flow makes the catalog easier to expand and reduces the odds of incomplete or malformed problem data.
- Clear field guidance helps maintain consistent problem quality, especially for richer scenarios that need domain context, setup instructions, and embedded media.
- Making the template source explicit is critical because Codespace launch behavior depends on it being correct.

## Requirements

### Functional Requirements
- [ ] The main catalog page includes an "Add a Problem" button near the top of the page.
- [ ] Clicking the button opens a dedicated add-problem page instead of overloading the catalog view.
- [ ] The add-problem page includes clear instructions describing how a new problem should be configured for LLMeetCode.
- [ ] The authoring form captures the core problem metadata required by the existing catalog and detail page flows, including a stable problem id/slug, title, short description, difficulty, language, and active status.
- [ ] The form includes inputs for richer problem-page content, including a short summary and longer overview/body content.
- [ ] The form includes an input that describes the problem's domain specialization so authors can explain the real-world discipline or focus area for the exercise.
- [ ] The flow supports attaching an optional YouTube URL for problem-creation context, walkthrough content, or a starter embedded video on the problem page.
- [ ] The flow captures the template source that Codespaces should use for the problem, aligned with the app's current template-repository-based provisioning model.
- [ ] Submitted problems persist in the database and become available in the catalog and problem detail page without manual code edits.
- [ ] Validation prevents creation of incomplete or invalid problems, including duplicate ids and missing template source data.
- [ ] The UX makes it obvious whether the newly created problem was saved successfully.

### Out of Scope
- Building a multi-step CMS or full editorial workflow for problem management.
- Bulk imports or migrations of large problem libraries.
- Supporting non-YouTube video hosting in the first iteration.
- Redesigning Codespace provisioning away from the current template repository model.
- Creating a full permissions system beyond the minimum gate needed to keep end users from adding problems.

## Acceptance Criteria

### Automated Verification
- [ ] Tests pass: `./run_tests.sh`
- [ ] App startup smoke check completes: `python -m app.main`

### Manual Verification
- [ ] The home page shows an "Add a Problem" button near the top of the catalog.
- [ ] Clicking the button opens an add-problem page with clear setup instructions.
- [ ] The form includes fields for basic catalog content, rich problem-page content, domain specialization, template source, and optional YouTube media.
- [ ] Submitting a valid problem creates a new record that appears in the catalog.
- [ ] Opening the new problem's detail page shows the authored content correctly.
- [ ] Launching a Codespace from the new problem uses the configured template source.
- [ ] Invalid submissions show actionable validation errors instead of failing silently.
- [ ] The authoring page is usable on both desktop and mobile screen sizes.

## Technical Notes

### Affected Components
- `app/templates/index.html` - add the top-level "Add a Problem" entry point.
- `app/main.py` - add routes, validation, persistence, and post-create navigation for the authoring flow.
- `app/database.py` - extend the data model if new authoring fields are needed beyond the current `Problem` schema.
- `app/templates/problem.html` - ensure newly authored rich content and optional embedded media render correctly.
- `app/templates/add-problem.html` - add a dedicated server-rendered authoring template.
- `tests/test_main.py` - cover page access, form submission, validation, and successful creation.
- `tests/test_database.py` - cover any schema additions or persistence behavior introduced by the new fields.

### Implementation Notes
- Reuse the existing `Problem` and related video/content patterns where possible instead of introducing a parallel content model.
- Prefer field names and validation rules that map cleanly onto current runtime expectations, especially `problem.id` and `template_repo`.
- If the requested "directory containing the problem template" differs from the existing GitHub template repository model, document the mapping clearly in the UI and implementation so Codespace behavior stays predictable.
- Normalize any YouTube URL into an embeddable format consistent with the current detail-page video handling.
- Keep the flow aligned with the server-rendered FastAPI + Jinja patterns already used throughout the app.

---

## Meta

**Created**: 2026-03-21
**Priority**: High
**Estimated Effort**: M
