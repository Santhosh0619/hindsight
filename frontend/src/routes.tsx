import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { ProtectedRoute } from "@/lib/auth";
import { SCREENS } from "@/lib/screens";
import { Landing } from "@/pages/Landing";
import { Login } from "@/pages/Login";
import { Onboarding } from "@/pages/Onboarding";
import { Signup } from "@/pages/Signup";
import { StubRoute } from "@/pages/StubRoute";

export function AppRoutes(): React.JSX.Element {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/onboarding" element={<Onboarding />} />

        <Route element={<AppShell />}>
          {SCREENS.map((screen) => (
            <Route key={screen.path} path={screen.path} element={<StubRoute />} />
          ))}
        </Route>
      </Route>
    </Routes>
  );
}
