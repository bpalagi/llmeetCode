# [ACME-1234] Investigate degraded API performance reported by customers

**Status:** In Progress
**Assignee:** You
**Priority:** High

---

## Description

Multiple enterprise customers have reported slow response times when loading the Recent Orders dashboard. The Customer Success team has escalated this as it's affecting our largest accounts.

From the support tickets:

> "The recent orders page takes forever to load. It used to be instant." — Foo Corp

> "Dashboard performance has degraded significantly. Sometimes it takes 3-4 seconds to show our orders." — GlobalTrade Ltd

> "We're seeing timeouts on the orders API when fetching recent orders. This is impacting our operations team." — MegaRetail Inc

## Acceptance Criteria

- [ ] Identify which endpoint(s) are experiencing performance issues
- [ ] Determine root cause of the slowdown
- [ ] Implement a fix that brings response times to acceptable levels (<100ms)
- [ ] Ensure existing tests continue to pass

## Getting Started

See [app/README.md](app/README.md) for setup instructions.

## Notes

_Add your investigation notes here as you debug._
