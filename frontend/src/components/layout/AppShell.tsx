import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { ErrorBoundary } from "@/components/layout/ErrorBoundary";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import { useAuth, useRequireRole } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { SCREENS } from "@/lib/screens";

export function AppShell(): React.JSX.Element {
  const { user, memberships, currentMembership, setCurrentWorkspace, logout } = useAuth();
  const navigate = useNavigate();
  // FR-07: Settings (F13) and New Incident (F5) are both write/admin surfaces --
  // Settings gates members & roles, API keys, LLM provider selection, workspace
  // deletion (plan.md §6); New Incident triggers a real LLM-costing brief generation
  // run. Both are hidden from viewers here, matching IncidentDetail's own
  // useRequireRole gate on its Generate/Regenerate brief button. Every other write
  // action described in FR-07 doesn't have UI yet and will be gated in the phase
  // that builds it.
  const canWrite = useRequireRole("owner", "responder");
  const GATED_PATHS = new Set(["/settings", "/incidents/new"]);
  const visibleScreens = SCREENS.filter((screen) => !GATED_PATHS.has(screen.path) || canWrite);

  const handleLogout = async (): Promise<void> => {
    await logout();
    navigate("/login");
  };

  const initials = (user?.full_name ?? "?")
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div className="flex h-screen bg-background text-foreground">
      <aside className="flex w-64 shrink-0 flex-col border-r border-border bg-card/40">
        <div className="p-4">
          <span className="text-lg font-semibold tracking-tight">
            Hind<span className="text-accent">sight</span>
          </span>
        </div>

        <div className="px-4 pb-2">
          <DropdownMenu>
            <DropdownMenuTrigger className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2 text-left text-sm hover:bg-muted">
              <span className="truncate">
                {currentMembership?.workspace_name ?? "Select workspace"}
              </span>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-56">
              <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {memberships.map((m) => (
                <DropdownMenuItem
                  key={m.workspace_id}
                  onSelect={() => setCurrentWorkspace(m.workspace_id)}
                >
                  {m.workspace_name}
                  <span className="ml-auto text-xs text-muted-foreground">{m.role}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <Separator />

        <nav className="flex-1 overflow-y-auto p-2">
          {visibleScreens.map((screen) => (
            <NavLink
              key={screen.path}
              to={screen.path}
              className={({ isActive }) =>
                cn(
                  "block rounded-md border-l-2 px-3 py-2 text-sm transition-colors hover:bg-muted hover:text-foreground",
                  isActive
                    ? "border-accent bg-muted font-medium text-foreground"
                    : "border-transparent text-muted-foreground"
                )
              }
            >
              {screen.label}
            </NavLink>
          ))}
        </nav>

        <Separator />

        <div className="p-2">
          <DropdownMenu>
            <DropdownMenuTrigger className="flex w-full items-center gap-2 rounded-md p-2 text-left hover:bg-muted">
              <Avatar className="h-8 w-8">
                <AvatarFallback>{initials}</AvatarFallback>
              </Avatar>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{user?.full_name}</p>
                <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
              </div>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-56">
              <DropdownMenuItem onSelect={() => void handleLogout()}>Log out</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto p-8">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  );
}
