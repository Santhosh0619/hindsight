import { describe, expect, it } from "vitest";

import { layeredLayout } from "@/lib/graph-layout";

describe("layeredLayout", () => {
  it("places a chain in strictly increasing layers", () => {
    const nodes = [
      { id: "a", name: "a" },
      { id: "b", name: "b" },
      { id: "c", name: "c" },
    ];
    const edges = [
      { from_service_id: "a", to_service_id: "b" },
      { from_service_id: "b", to_service_id: "c" },
    ];

    const layout = layeredLayout(nodes, edges);

    expect(layout.get("a")?.layer).toBe(0);
    expect(layout.get("b")?.layer).toBe(1);
    expect(layout.get("c")?.layer).toBe(2);
  });

  it("places both branches of a diamond in the same layer, ahead of their shared join", () => {
    const nodes = [
      { id: "root", name: "root" },
      { id: "left", name: "left" },
      { id: "right", name: "right" },
      { id: "join", name: "join" },
    ];
    const edges = [
      { from_service_id: "root", to_service_id: "left" },
      { from_service_id: "root", to_service_id: "right" },
      { from_service_id: "left", to_service_id: "join" },
      { from_service_id: "right", to_service_id: "join" },
    ];

    const layout = layeredLayout(nodes, edges);

    expect(layout.get("root")?.layer).toBe(0);
    expect(layout.get("left")?.layer).toBe(1);
    expect(layout.get("right")?.layer).toBe(1);
    expect(layout.get("join")?.layer).toBe(2);
    // Nodes sharing a layer get distinct y positions, not stacked on top of
    // each other.
    expect(layout.get("left")?.y).not.toBe(layout.get("right")?.y);
  });

  it("terminates and assigns every node a finite layer on a cycle", () => {
    const nodes = [
      { id: "a", name: "a" },
      { id: "b", name: "b" },
      { id: "c", name: "c" },
    ];
    const edges = [
      { from_service_id: "a", to_service_id: "b" },
      { from_service_id: "b", to_service_id: "c" },
      { from_service_id: "c", to_service_id: "a" },
    ];

    const layout = layeredLayout(nodes, edges);

    expect(layout.size).toBe(3);
    for (const node of ["a", "b", "c"]) {
      const placed = layout.get(node);
      expect(placed).toBeDefined();
      expect(Number.isFinite(placed?.layer)).toBe(true);
    }
  });

  it("is deterministic across repeated calls on the same graph", () => {
    const nodes = [
      { id: "svc-3", name: "checkout" },
      { id: "svc-1", name: "auth" },
      { id: "svc-2", name: "billing" },
    ];
    const edges = [
      { from_service_id: "svc-1", to_service_id: "svc-3" },
      { from_service_id: "svc-2", to_service_id: "svc-3" },
    ];

    const first = layeredLayout(nodes, edges);
    const second = layeredLayout(nodes, edges);

    for (const node of nodes) {
      expect(first.get(node.id)).toEqual(second.get(node.id));
    }
  });

  it("ignores an edge referencing a service that isn't in the node list", () => {
    const nodes = [{ id: "a", name: "a" }];
    const edges = [{ from_service_id: "a", to_service_id: "ghost" }];

    const layout = layeredLayout(nodes, edges);

    expect(layout.size).toBe(1);
    expect(layout.get("a")?.layer).toBe(0);
  });

  it("places an isolated node with no edges at layer 0", () => {
    const nodes = [{ id: "lonely", name: "lonely" }];
    const layout = layeredLayout(nodes, []);

    expect(layout.get("lonely")?.layer).toBe(0);
  });

  it("completes and places every node at Phase 11's target scale (40 nodes, 60 edges)", () => {
    const nodeCount = 40;
    const nodes = Array.from({ length: nodeCount }, (_, i) => ({
      id: `svc-${i}`,
      name: `service-${i.toString().padStart(2, "0")}`,
    }));
    // A deterministic, reproducible edge set -- not random -- covering a mix of
    // short/long hops and a handful of back-edges so the fixture isn't just a
    // trivial chain the way the smaller tests above already are.
    const edges: { from_service_id: string; to_service_id: string }[] = [];
    for (let i = 0; i < nodeCount - 1; i++) {
      edges.push({ from_service_id: `svc-${i}`, to_service_id: `svc-${i + 1}` });
    }
    for (let i = 0; edges.length < 60; i++) {
      const from = i % nodeCount;
      const to = (i * 7 + 3) % nodeCount;
      if (from !== to) edges.push({ from_service_id: `svc-${from}`, to_service_id: `svc-${to}` });
    }

    const layout = layeredLayout(nodes, edges);

    expect(layout.size).toBe(nodeCount);
    for (const node of nodes) {
      const placed = layout.get(node.id);
      expect(placed).toBeDefined();
      expect(Number.isFinite(placed?.layer)).toBe(true);
      expect(Number.isFinite(placed?.x)).toBe(true);
      expect(Number.isFinite(placed?.y)).toBe(true);
    }
  });
});
