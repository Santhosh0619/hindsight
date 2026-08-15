import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { LoadingSkeleton } from "@/components/layout/LoadingSkeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { changeMemberRole, listMembers, removeMember, rotateInviteCode } from "@/lib/api";
import type { WorkspaceRole } from "@/lib/types";

const ROLES: WorkspaceRole[] = ["owner", "responder", "viewer"];

export function MembersPanel({
  workspaceId,
  canManage,
}: {
  workspaceId: string;
  canManage: boolean;
}): React.JSX.Element {
  const queryClient = useQueryClient();
  const [inviteCode, setInviteCode] = React.useState<string | null>(null);
  const [rotating, setRotating] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const membersQuery = useQuery({
    queryKey: ["members", workspaceId],
    queryFn: () => listMembers(workspaceId),
  });

  const invalidate = (): void => {
    void queryClient.invalidateQueries({ queryKey: ["members", workspaceId] });
  };

  const handleRotate = async (): Promise<void> => {
    setRotating(true);
    setErrorMessage(null);
    try {
      const result = await rotateInviteCode(workspaceId);
      setInviteCode(result.code);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setRotating(false);
    }
  };

  const handleRoleChange = async (userId: string, role: WorkspaceRole): Promise<void> => {
    setErrorMessage(null);
    try {
      await changeMemberRole(workspaceId, userId, role);
      invalidate();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  const handleRemove = async (userId: string): Promise<void> => {
    setErrorMessage(null);
    try {
      await removeMember(workspaceId, userId);
      invalidate();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Members</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {canManage ? (
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              disabled={rotating}
              onClick={() => void handleRotate()}
            >
              {rotating ? "Rotating…" : "Rotate invite code"}
            </Button>
            {inviteCode ? (
              <code className="rounded bg-muted px-2 py-1 text-sm">{inviteCode}</code>
            ) : null}
          </div>
        ) : null}

        {errorMessage ? <p className="text-sm text-destructive">{errorMessage}</p> : null}

        {membersQuery.isLoading ? (
          <LoadingSkeleton lines={3} />
        ) : membersQuery.isError ? (
          <p className="text-sm text-destructive">Couldn't load members.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {(membersQuery.data ?? []).map((member) => (
              <div
                key={member.user_id}
                className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{member.full_name}</p>
                  <p className="truncate text-xs text-muted-foreground">{member.email}</p>
                </div>
                {canManage ? (
                  <div className="flex items-center gap-2">
                    <select
                      value={member.role}
                      aria-label={`Role for ${member.full_name}`}
                      onChange={(e) =>
                        void handleRoleChange(member.user_id, e.target.value as WorkspaceRole)
                      }
                      className="rounded-md border border-input bg-transparent px-2 py-1 text-xs"
                    >
                      {ROLES.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void handleRemove(member.user_id)}
                    >
                      Remove
                    </Button>
                  </div>
                ) : (
                  <Badge variant="muted">{member.role}</Badge>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
