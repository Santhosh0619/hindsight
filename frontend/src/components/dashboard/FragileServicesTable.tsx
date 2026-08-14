import { Link } from "react-router-dom";

import type { FragileServiceOut } from "@/lib/types";

export function FragileServicesTable({
  services,
}: {
  services: FragileServiceOut[];
}): React.JSX.Element {
  if (services.length === 0) {
    return <p className="text-sm text-muted-foreground">No services to rank yet.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <th className="pb-2 font-medium">Service</th>
            <th className="pb-2 font-medium">Incidents</th>
            <th className="pb-2 font-medium">Blast radius</th>
            <th className="pb-2 font-medium">Fragility</th>
          </tr>
        </thead>
        <tbody>
          {services.map((entry) => (
            <tr key={entry.service.id} className="border-b border-border last:border-0">
              <td className="py-2">
                <Link to="/service-map" className="hover:underline">
                  {entry.service.name}
                </Link>
              </td>
              <td className="py-2 tabular-nums">{entry.incident_count}</td>
              <td className="py-2 tabular-nums">{entry.blast_radius_size}</td>
              <td className="py-2 tabular-nums font-medium">{entry.fragility_score}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
