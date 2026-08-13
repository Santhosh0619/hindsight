import { useLocation } from "react-router-dom";

import { EmptyState } from "@/components/layout/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { SCREENS } from "@/lib/screens";

export function StubRoute(): React.JSX.Element {
  const location = useLocation();
  const screen = SCREENS.find((s) => location.pathname.startsWith(s.path));

  return (
    <>
      <PageHeader title={screen?.label ?? "Coming soon"} />
      <EmptyState
        title={screen ? `${screen.label} isn't built yet` : "This screen isn't built yet"}
        description={
          screen
            ? `This screen is built in Phase ${screen.phase} of Hindsight's build plan.`
            : "Check back in a later phase."
        }
      />
    </>
  );
}
