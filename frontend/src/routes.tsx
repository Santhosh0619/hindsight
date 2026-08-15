import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { ProtectedRoute } from "@/lib/auth";
import { SCREENS } from "@/lib/screens";
import { AgentRuns } from "@/pages/AgentRuns";
import { AuditLog } from "@/pages/AuditLog";
import { Dashboard } from "@/pages/Dashboard";
import { Evaluation } from "@/pages/Evaluation";
import { IncidentDetail } from "@/pages/IncidentDetail";
import { IncidentList } from "@/pages/IncidentList";
import { KnowledgeBase } from "@/pages/KnowledgeBase";
import { Landing } from "@/pages/Landing";
import { Login } from "@/pages/Login";
import { NewIncident } from "@/pages/NewIncident";
import { Onboarding } from "@/pages/Onboarding";
import { PostmortemDetail } from "@/pages/PostmortemDetail";
import { Search } from "@/pages/Search";
import { ServiceMap } from "@/pages/ServiceMap";
import { Settings } from "@/pages/Settings";
import { Signup } from "@/pages/Signup";
import { StubRoute } from "@/pages/StubRoute";

// Screens with a real page component this phase; every other SCREENS entry still
// renders StubRoute until its own phase builds it out.
const IMPLEMENTED_PAGES: Partial<Record<string, React.ComponentType>> = {
  "/search": Search,
  "/incidents/new": NewIncident,
  "/incidents": IncidentList,
  "/service-map": ServiceMap,
  "/knowledge-base": KnowledgeBase,
  "/dashboard": Dashboard,
  "/evaluation": Evaluation,
  "/agent-runs": AgentRuns,
  "/settings": Settings,
  "/audit-log": AuditLog,
};

export function AppRoutes(): React.JSX.Element {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/onboarding" element={<Onboarding />} />

        <Route element={<AppShell />}>
          {SCREENS.map((screen) => {
            const Page = IMPLEMENTED_PAGES[screen.path] ?? StubRoute;
            return <Route key={screen.path} path={screen.path} element={<Page />} />;
          })}
          {/* F6 Incident Detail -- contextual route reached from F7, not a sidebar
              entry (see lib/screens.ts's own comment on why it's absent from SCREENS). */}
          <Route path="/incidents/:id" element={<IncidentDetail />} />
          {/* Postmortem detail -- contextual route reached from F8's table, same
              pattern as Incident Detail above. */}
          <Route path="/knowledge-base/:id" element={<PostmortemDetail />} />
        </Route>
      </Route>
    </Routes>
  );
}
