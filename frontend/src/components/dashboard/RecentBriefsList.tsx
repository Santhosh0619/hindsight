import { Link } from "react-router-dom";

import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { Timestamp } from "@/components/ui/timestamp";
import type { RecentBriefOut } from "@/lib/types";

export function RecentBriefsList({ briefs }: { briefs: RecentBriefOut[] }): React.JSX.Element {
  if (briefs.length === 0) {
    return <p className="text-sm text-muted-foreground">No briefs generated yet.</p>;
  }

  return (
    <ul className="flex flex-col gap-2">
      {briefs.map((brief) => (
        <li key={brief.brief_id}>
          <Link
            to={`/incidents/${brief.incident_id}`}
            className="flex items-center justify-between gap-2 rounded-md border border-border p-2 hover:bg-muted"
          >
            <span className="truncate text-sm">{brief.incident_title}</span>
            <span className="flex shrink-0 items-center gap-2">
              {brief.overall_confidence !== null ? (
                <ConfidenceBadge confidence={brief.overall_confidence} />
              ) : null}
              {brief.generated_at ? <Timestamp value={brief.generated_at} /> : null}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
