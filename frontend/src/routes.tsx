import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { ProtectedRoute } from "@/lib/auth";
import { SCREENS } from "@/lib/screens";
import { IncidentDetail } from "@/pages/IncidentDetail";
import { IncidentList } from "@/pages/IncidentList";
import { Landing } from "@/pages/Landing";
import { Login } from "@/pages/Login";
import { NewIncident } from "@/pages/NewIncident";
import { Onboarding } from "@/pages/Onboarding";
import { Search } from "@/pages/Search";
import { Signup } from "@/pages/Signup";
import { StubRoute } from "@/pages/StubRoute";

// Screens with a real page component this phase; every other SCREENS entry still
// renders StubRoute until its own phase builds it out.
const IMPLEMENTED_PAGES: Partial<Record<string, React.ComponentType>> = {
  "/search": Search,
  "/incidents/new": NewIncident,
  "/incidents": IncidentList,
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
        </Route>
      </Route>
    </Routes>
  );
}
