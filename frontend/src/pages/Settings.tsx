import * as React from "react";

import { ApiKeysPanel } from "@/components/settings/ApiKeysPanel";
import { DangerZonePanel } from "@/components/settings/DangerZonePanel";
import { LlmProviderPanel } from "@/components/settings/LlmProviderPanel";
import { MembersPanel } from "@/components/settings/MembersPanel";
import { EmptyState } from "@/components/layout/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { updateWorkspace } from "@/lib/api";
import { useAuth, useRequireRole } from "@/lib/auth";

function GeneralPanel({
  workspaceId,
  initialName,
  initialSlug,
}: {
  workspaceId: string;
  initialName: string;
  initialSlug: string;
}): React.JSX.Element {
  const [name, setName] = React.useState(initialName);
  const [slug, setSlug] = React.useState(initialSlug);
  const [saving, setSaving] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const dirty = name.trim() !== initialName || slug.trim() !== initialSlug;

  const handleSave = async (): Promise<void> => {
    if (!dirty || !name.trim() || !slug.trim()) return;
    setSaving(true);
    setErrorMessage(null);
    try {
      await updateWorkspace(workspaceId, { name: name.trim(), slug: slug.trim() });
      window.location.reload();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">General</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ws-name">Workspace name</Label>
          <Input id="ws-name" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ws-slug">Slug</Label>
          <Input id="ws-slug" value={slug} onChange={(e) => setSlug(e.target.value)} />
        </div>
        {errorMessage ? <p className="text-sm text-destructive">{errorMessage}</p> : null}
        <div>
          <Button disabled={!dirty || saving} onClick={() => void handleSave()}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function Settings(): React.JSX.Element {
  const { currentMembership } = useAuth();
  const isOwner = useRequireRole("owner");

  if (!currentMembership) {
    return (
      <>
        <PageHeader title="Settings" />
        <EmptyState title="No workspace selected" />
      </>
    );
  }

  const {
    workspace_id: workspaceId,
    workspace_name: workspaceName,
    workspace_slug: workspaceSlug,
  } = currentMembership;

  return (
    <>
      <PageHeader
        title="Settings"
        description="Members, API keys, LLM connectivity, and workspace administration."
      />
      <div className="flex flex-col gap-4">
        <MembersPanel workspaceId={workspaceId} canManage={isOwner} />

        {isOwner ? (
          <>
            <GeneralPanel
              workspaceId={workspaceId}
              initialName={workspaceName}
              initialSlug={workspaceSlug}
            />
            <ApiKeysPanel workspaceId={workspaceId} />
            <LlmProviderPanel workspaceId={workspaceId} />
            <DangerZonePanel workspaceId={workspaceId} workspaceName={workspaceName} />
          </>
        ) : (
          <Card>
            <CardContent className="pt-6 text-sm text-muted-foreground">
              API keys, LLM provider connectivity, and workspace administration are managed by an
              owner.
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
}
