// Single source of truth for the 14 screens in plan.md §6 — both AppShell's sidebar
// and routes.tsx's stub-route table read from this so the two never drift apart.
//
// F6 "Incident Detail" is deliberately absent: it's a contextual /incidents/:id
// page reached by clicking into a row on F7 (Incidents), not a top-level sidebar
// destination in its own right — plan.md doesn't list it as one either. It'll get
// its own route (not a sidebar entry) when Phase 9 builds it.

export interface ScreenDef {
  path: string;
  label: string;
  phase: number;
  /** Screens with a real page component this phase; everything else is a stub. */
  implemented?: boolean;
}

export const SCREENS: ScreenDef[] = [
  { path: "/dashboard", label: "Dashboard", phase: 10 },
  { path: "/incidents/new", label: "New Incident", phase: 9 },
  { path: "/incidents", label: "Incidents", phase: 9 },
  { path: "/knowledge-base", label: "Knowledge Base", phase: 10 },
  { path: "/service-map", label: "Service Map", phase: 10 },
  { path: "/search", label: "Search", phase: 7 },
  { path: "/evaluation", label: "Evaluation", phase: 12 },
  { path: "/agent-runs", label: "Agent Runs", phase: 13 },
  { path: "/settings", label: "Settings", phase: 13 },
  { path: "/audit-log", label: "Audit Log", phase: 13 },
];
