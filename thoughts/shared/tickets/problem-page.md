# [LLMEET-0001] Add dedicated problem detail page

## Problem Statement

The main problem catalog currently acts as the only place where users can discover a problem and take action on it. That makes each problem feel shallow: users can see the title and status, but they cannot click into a fuller brief that explains the scenario, expectations, or supporting material before starting work.

We need a dedicated problem page so each exercise can behave more like a realistic interview or debugging prompt rather than a single row in a list.

## Desired Outcome

Users can click a problem from the main page and land on a dedicated detail page for that problem. The detail page should provide richer context for the exercise, preserve the existing primary actions for starting or resuming work and marking completion, and support richer content such as an embedded example solution video.

For the first iteration, the new page should be built around the "Slow API Performance" problem and should include the problem overview derived from `thoughts/shared/research/example-jira.md`.

## Context & Background

### Current State

- The main page presents a list of available problems.
- Users can currently act on a problem directly from the list view.
- There is no dedicated route or template for viewing a single problem in more detail.
- Supporting context for the "Slow API Performance" scenario exists in `thoughts/shared/research/example-jira.md`, but it is not surfaced in the product UI.

### Why This Matters

- A detail page gives users enough context to understand what they are about to solve before launching a Codespace or marking work complete.
- It makes the exercise format feel more intentional and realistic, especially for scenario-based prompts like performance investigations.
- It creates a place to add richer instructional content over time, including videos, background docs, and problem-specific metadata.
- It reduces pressure on the index page to contain both catalog and detail responsibilities.

## Requirements

### Functional Requirements
- [ ] Each problem in the main catalog can be clicked to navigate to a dedicated problem detail page.
- [ ] The detail page displays core problem information, including title, summary, and problem context.
- [ ] The detail page preserves the existing problem actions available on the main page, including starting/resuming the problem and marking the problem complete.
- [ ] The action behavior on the detail page matches the current behavior from the main page so users do not lose functionality by navigating deeper.
- [ ] The first implemented example uses the "Slow API Performance" problem.
- [ ] The "Slow API Performance" page includes an overview based on the content in `thoughts/shared/research/example-jira.md`.
- [ ] The detail page includes a section for embedded YouTube-based "solution submissions."
- [ ] The first embedded example uses `https://youtube.com/live/dtjqMNyNPiw?feature=share`.
- [ ] The embedded video section is presented in a way that can be extended later to support multiple solution submissions.
- [ ] Navigation back to the broader problem list remains clear and intuitive.

### Out of Scope
- Authentication, Codespace provisioning, or completion-state business logic redesign.
- Building a full authoring system for managing problem content from the UI.
- User-submitted video upload flows.
- A broad redesign of the problem catalog beyond what is needed to support clickable entries and navigation.
- Multi-problem content migration beyond the initial "Slow API Performance" example.

## Acceptance Criteria

### Automated Verification
- [ ] Tests pass: `./run_tests.sh`
- [ ] App startup smoke check completes: `python -m app.main`

### Manual Verification
- [ ] From the main page, clicking the "Slow API Performance" problem opens a dedicated detail page.
- [ ] The detail page shows problem context that reflects the scenario described in `thoughts/shared/research/example-jira.md`.
- [ ] The page exposes the same relevant actions available on the main page for starting/resuming and marking completion.
- [ ] Starting or resuming from the detail page behaves consistently with the current list-page actions.
- [ ] Marking a problem complete from the detail page behaves consistently with the current list-page actions.
- [ ] The example YouTube solution submission is embedded and viewable on the detail page.
- [ ] Users can easily return from the detail page to the main problem list.
- [ ] The page layout works on both desktop and mobile screen sizes.

## Technical Notes

### Affected Components
- `app/main.py` - add or update the route and server-side data for rendering an individual problem page.
- `app/templates/index.html` - make problem entries clickable and point them to the new detail route.
- `app/templates/problem.html` - add a dedicated template for rendering problem details and embedded solution content.
- `app/templates/base.html` - reuse shared navigation/layout patterns as needed for the new page.
- `thoughts/shared/research/example-jira.md` - source material for the initial "Slow API Performance" problem overview.

### Implementation Notes
- Prefer a stable problem identifier in the route structure, such as a slug or problem id, so the pattern scales to additional problems.
- Reuse existing action handlers and state derivation where possible instead of duplicating start/complete logic.
- Structure the detail-page content model so richer sections like overview, metadata, and solution submissions can be added to more problems later.
- Normalize the provided YouTube URL into an embeddable format for iframe rendering.
- Keep the UX consistent with the existing server-rendered Jinja/Tailwind application patterns.

---

## Meta

**Created**: 2026-03-21
**Priority**: High
**Estimated Effort**: M
