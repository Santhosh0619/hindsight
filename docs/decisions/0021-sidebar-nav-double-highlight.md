# ADR 0021: Sidebar Double-Highlight on /incidents/new

## Context

Preparing demo material surfaced a visible sidebar bug: opening New Incident
(`/incidents/new`) highlighted both "New Incident" and "Incidents" at once.
`AppShell.tsx`'s sidebar renders each screen from `SCREENS` as a `NavLink` without
the `end` prop, so React Router falls back to its default prefix matching. Every
sidebar destination is a flat, absolute route (`routes.tsx` never nests them), so
`/incidents/new` correctly matches its own exact-path link but also matches
`/incidents` as a prefix, lighting up both.

## Decision

Added `end` to the sidebar `NavLink`, restricting each entry to an exact-path
match. This is the pattern React Router itself recommends for sibling routes that
share a URL prefix but aren't meant to highlight each other. The trade-off:
contextual detail routes reached by clicking into a list (`/incidents/:id`,
`/knowledge-base/:id`) no longer highlight their parent list's nav entry either —
previously true only as a side effect of the same prefix-matching bug, never a
documented or tested behavior. Added a regression test asserting `/incidents/new`
sets `aria-current="page"` on "New Incident" only, not "Incidents".
