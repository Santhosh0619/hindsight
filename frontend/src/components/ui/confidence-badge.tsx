import { Badge } from "@/components/ui/badge";

export function ConfidenceBadge({ confidence }: { confidence: number }): React.JSX.Element {
  const percent = Math.round(confidence * 100);
  const variant = percent >= 75 ? "success" : percent >= 45 ? "warning" : "destructive";

  return (
    <Badge variant={variant} className="font-mono">
      {percent}%
    </Badge>
  );
}
