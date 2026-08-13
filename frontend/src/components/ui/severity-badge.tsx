import { Badge } from "@/components/ui/badge";

export type Severity = "sev1" | "sev2" | "sev3" | "sev4";

const SEVERITY_VARIANT: Record<Severity, "destructive" | "warning" | "muted"> = {
  sev1: "destructive",
  sev2: "warning",
  sev3: "warning",
  sev4: "muted",
};

export function SeverityBadge({ severity }: { severity: Severity }): React.JSX.Element {
  return (
    <Badge variant={SEVERITY_VARIANT[severity]} className="font-mono uppercase">
      {severity}
    </Badge>
  );
}
