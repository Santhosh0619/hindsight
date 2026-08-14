import * as React from "react";

import { LAYER_SPACING, layeredLayout } from "@/lib/graph-layout";
import type { EdgeOut, ServiceOut, TeamOut } from "@/lib/types";

const TIER_RADIUS: Record<number, number> = { 1: 26, 2: 20, 3: 15 };
const TEAM_COLORS = [
  "#6366f1",
  "#22c55e",
  "#f59e0b",
  "#ec4899",
  "#06b6d4",
  "#a855f7",
  "#f97316",
  "#14b8a6",
];
const UNASSIGNED_COLOR = "#64748b";
const HIGHLIGHT_COLOR = "#ef4444";
const SELECTED_COLOR = "#e2e8f0";
const EDGE_COLOR = "#475569";

const MIN_SCALE = 0.3;
const MAX_SCALE = 3;
const PADDING = 60;

function colorForTeam(teamId: string | null, teamIds: string[]): string {
  if (teamId === null) return UNASSIGNED_COLOR;
  const index = teamIds.indexOf(teamId);
  return TEAM_COLORS[index % TEAM_COLORS.length] ?? UNASSIGNED_COLOR;
}

export interface ServiceMapCanvasProps {
  nodes: ServiceOut[];
  edges: EdgeOut[];
  teams: TeamOut[];
  selectedServiceId: string | null;
  highlightedServiceIds: Set<string>;
  onSelectService: (serviceId: string) => void;
}

export function ServiceMapCanvas({
  nodes,
  edges,
  teams,
  selectedServiceId,
  highlightedServiceIds,
  onSelectService,
}: ServiceMapCanvasProps): React.JSX.Element {
  const layout = React.useMemo(() => layeredLayout(nodes, edges), [nodes, edges]);
  const teamIds = React.useMemo(() => teams.map((t) => t.id), [teams]);

  const [transform, setTransform] = React.useState({ scale: 1, x: PADDING, y: PADDING });
  const dragRef = React.useRef<{
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);

  const handleWheel = (event: React.WheelEvent<SVGSVGElement>): void => {
    event.preventDefault();
    const factor = event.deltaY > 0 ? 0.9 : 1.1;
    setTransform((t) => ({
      ...t,
      scale: Math.min(MAX_SCALE, Math.max(MIN_SCALE, t.scale * factor)),
    }));
  };

  const handlePointerDown = (event: React.PointerEvent<SVGSVGElement>): void => {
    dragRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      originX: transform.x,
      originY: transform.y,
    };
  };

  const handlePointerMove = (event: React.PointerEvent<SVGSVGElement>): void => {
    const drag = dragRef.current;
    if (!drag) return;
    setTransform((t) => ({
      ...t,
      x: drag.originX + (event.clientX - drag.startX),
      y: drag.originY + (event.clientY - drag.startY),
    }));
  };

  const endDrag = (): void => {
    dragRef.current = null;
  };

  const maxLayer = Math.max(0, ...nodes.map((n) => layout.get(n.id)?.layer ?? 0));
  const width = (maxLayer + 1) * LAYER_SPACING + PADDING * 2;

  return (
    <div className="relative h-[600px] w-full overflow-hidden rounded-lg border border-border bg-card/20">
      <svg
        role="img"
        aria-label="Service dependency map"
        className="h-full w-full cursor-grab touch-none active:cursor-grabbing"
        viewBox={`0 0 ${width} 600`}
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
      >
        <g transform={`translate(${transform.x}, ${transform.y}) scale(${transform.scale})`}>
          {edges.map((edge) => {
            const from = layout.get(edge.from_service_id);
            const to = layout.get(edge.to_service_id);
            if (!from || !to) return null;
            const onBlastPath =
              highlightedServiceIds.has(edge.from_service_id) &&
              highlightedServiceIds.has(edge.to_service_id);
            return (
              <line
                key={edge.id}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke={onBlastPath ? HIGHLIGHT_COLOR : EDGE_COLOR}
                strokeWidth={onBlastPath ? 2 : 1}
                strokeDasharray={edge.criticality === "soft" ? "4 3" : undefined}
              />
            );
          })}
          {nodes.map((node) => {
            const pos = layout.get(node.id);
            if (!pos) return null;
            const radius = TIER_RADIUS[node.tier] ?? 18;
            const highlighted = highlightedServiceIds.has(node.id);
            const selected = node.id === selectedServiceId;
            return (
              <g
                key={node.id}
                role="button"
                tabIndex={0}
                aria-label={node.name}
                data-testid={`service-node-${node.id}`}
                transform={`translate(${pos.x}, ${pos.y})`}
                className="cursor-pointer outline-none"
                onClick={() => onSelectService(node.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") onSelectService(node.id);
                }}
              >
                <circle
                  r={radius}
                  fill={colorForTeam(node.team_id, teamIds)}
                  stroke={highlighted ? HIGHLIGHT_COLOR : selected ? SELECTED_COLOR : "transparent"}
                  strokeWidth={highlighted || selected ? 3 : 0}
                  opacity={0.92}
                />
                <text
                  y={radius + 14}
                  textAnchor="middle"
                  className="fill-foreground text-[11px] font-medium"
                >
                  {node.name}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
