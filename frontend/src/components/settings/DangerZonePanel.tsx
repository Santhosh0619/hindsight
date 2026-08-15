import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { deleteWorkspace } from "@/lib/api";

export function DangerZonePanel({
  workspaceId,
  workspaceName,
}: {
  workspaceId: string;
  workspaceName: string;
}): React.JSX.Element {
  const [confirmText, setConfirmText] = React.useState("");
  const [deleting, setDeleting] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const canDelete = confirmText.trim() === workspaceName;

  const handleDelete = async (): Promise<void> => {
    if (!canDelete) return;
    setDeleting(true);
    setErrorMessage(null);
    try {
      await deleteWorkspace(workspaceId);
      window.location.assign("/dashboard");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
      setDeleting(false);
    }
  };

  return (
    <Card className="border-destructive/40">
      <CardHeader>
        <CardTitle className="text-base text-destructive">Danger zone</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">
          Deleting <strong>{workspaceName}</strong> is permanent — every postmortem, incident, and
          brief in it is gone. Type the workspace name below to confirm.
        </p>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="confirm-delete">Workspace name</Label>
          <Input
            id="confirm-delete"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder={workspaceName}
          />
        </div>
        {errorMessage ? <p className="text-sm text-destructive">{errorMessage}</p> : null}
        <div>
          <Button
            variant="destructive"
            disabled={!canDelete || deleting}
            onClick={() => void handleDelete()}
          >
            {deleting ? "Deleting…" : "Delete workspace"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
