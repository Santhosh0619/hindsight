// Deterministic layered layout for the Service Map (F9) -- not a physics-based force
// simulation. See docs/modules/phase-10-service-map-kb-dashboard/FRD.md Gap #5 for why:
// a real force-directed layout is non-deterministic between renders, hard to keep
// smooth at 40 nodes without a real simulation library (explicitly out of scope), and
// hard to test. Each node's layer is the length of its longest acyclic path from a
// root; a cycle is broken by always making topological progress (removing one node
// per iteration), so this always terminates in exactly |nodes| steps regardless of
// how many cycles the catalog graph contains.

export interface LayoutService {
  id: string;
  name: string;
}

export interface LayoutEdge {
  from_service_id: string;
  to_service_id: string;
}

export interface ServiceMapLayoutNode {
  id: string;
  layer: number;
  x: number;
  y: number;
}

export const LAYER_SPACING = 220;
export const NODE_SPACING = 120;

export function layeredLayout(
  nodes: LayoutService[],
  edges: LayoutEdge[]
): Map<string, ServiceMapLayoutNode> {
  const ids = nodes.map((n) => n.id);
  const nameById = new Map(nodes.map((n) => [n.id, n.name]));
  const idSet = new Set(ids);

  const outgoing = new Map<string, string[]>(ids.map((id) => [id, []]));
  const incoming = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const edge of edges) {
    if (!idSet.has(edge.from_service_id) || !idSet.has(edge.to_service_id)) continue;
    outgoing.get(edge.from_service_id)?.push(edge.to_service_id);
    incoming.get(edge.to_service_id)?.push(edge.from_service_id);
  }

  const layer = new Map<string, number>();
  const remaining = new Set(ids);
  // How many of each node's real predecessors are still unplaced. Once this hits 0,
  // placing the node is a genuine topological step.
  const remainingInDegree = new Map(ids.map((id) => [id, incoming.get(id)?.length ?? 0]));

  while (remaining.size > 0) {
    // Prefer a node with zero unplaced predecessors. If none exists (every
    // remaining node sits inside a cycle), fall back to the one with the fewest --
    // its still-unplaced incoming edges are treated as back-edges and never
    // revisited, which is what guarantees termination on a cycle. Ties break by
    // name for a deterministic result given the same graph.
    let next: string | null = null;
    let bestDegree = Infinity;
    for (const id of remaining) {
      const degree = remainingInDegree.get(id) ?? 0;
      const isBetter =
        degree < bestDegree ||
        (degree === bestDegree &&
          next !== null &&
          (nameById.get(id) ?? "") < (nameById.get(next) ?? ""));
      if (next === null || isBetter) {
        next = id;
        bestDegree = degree;
      }
    }
    const id = next as string;
    remaining.delete(id);

    let maxPredLayer = -1;
    for (const pred of incoming.get(id) ?? []) {
      const predLayer = layer.get(pred);
      if (predLayer !== undefined) {
        maxPredLayer = Math.max(maxPredLayer, predLayer);
      }
    }
    layer.set(id, maxPredLayer + 1);

    for (const succ of outgoing.get(id) ?? []) {
      const current = remainingInDegree.get(succ);
      if (current !== undefined) {
        remainingInDegree.set(succ, Math.max(0, current - 1));
      }
    }
  }

  const byLayer = new Map<number, string[]>();
  for (const id of ids) {
    const l = layer.get(id) ?? 0;
    const bucket = byLayer.get(l);
    if (bucket) bucket.push(id);
    else byLayer.set(l, [id]);
  }

  const result = new Map<string, ServiceMapLayoutNode>();
  for (const [l, idsInLayer] of byLayer) {
    idsInLayer.sort((a, b) => (nameById.get(a) ?? "").localeCompare(nameById.get(b) ?? ""));
    idsInLayer.forEach((id, index) => {
      result.set(id, { id, layer: l, x: l * LAYER_SPACING, y: index * NODE_SPACING });
    });
  }

  return result;
}
