import { useAuth } from "@/lib/auth";

export function DemoBanner(): React.JSX.Element | null {
  const { user, currentMembership } = useAuth();

  // Scoped to both the account and the workspace currently being viewed -- a demo
  // guest who joins a real workspace via invite code must not see this workspace's
  // real data mislabeled as synthetic.
  if (!user?.is_demo || !currentMembership?.workspace_is_demo) {
    return null;
  }

  return (
    <div className="border-b border-accent/30 bg-accent/10 px-4 py-1.5 text-center text-xs font-medium text-accent">
      Demo workspace — synthetic data, read-only.
    </div>
  );
}
