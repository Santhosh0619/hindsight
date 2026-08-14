import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { ProtectedRoute } from "@/lib/auth";
import { SCREENS } from "@/lib/screens";
import { Landing } from "@/pages/Landing";
import { Login } from "@/pages/Login";
import { Onboarding } from "@/pages/Onboarding";
import { Search } from "@/pages/Search";
import { Signup } from "@/pages/Signup";
import { StubRoute } from "@/pages/StubRoute";

// Screens with a real page component this phase; every other SCREENS entry still
// renders StubRoute until its own phase builds it out.
const IMPLEMENTED_PAGES: Partial<Record<string, React.ComponentType>> = {
  "/search": Search,
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
        </Route>
      </Route>
    </Routes>
  );
}
