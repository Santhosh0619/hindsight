// Single source of truth for the 14 screens in plan.md §6 — both AppShell's sidebar
// and routes.tsx's stub-route table read from this so the two never drift apart.

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
