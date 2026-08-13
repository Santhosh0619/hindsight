import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function MetricCard({
  label,
  value,
  description,
}: {
  label: string;
  value: string | number;
  description?: string;
}): React.JSX.Element {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-semibold tabular-nums">{value}</div>
        {description ? <p className="mt-1 text-xs text-muted-foreground">{description}</p> : null}
      </CardContent>
    </Card>
  );
}
