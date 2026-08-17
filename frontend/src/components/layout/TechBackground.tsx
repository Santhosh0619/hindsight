// Decorative-only background for the public-facing marketing surface (Landing, Login,
// Signup, Onboarding) -- an animated node-graph/network: glowing nodes connected by
// thin edges, with light pulses traveling along a subset of them. Deliberately on-theme
// rather than generic "AI" decoration: Hindsight's actual product is a service-
// dependency graph and a multi-node agent pipeline, so a constellation of connected,
// pulsing nodes is the real shape of the thing, not just a mood.
//
// Pure CSS/SVG, no external image asset and no JS animation loop -- nothing to license,
// nothing to fetch, nothing that can 404, and every animation is a GPU-cheap CSS
// keyframe or native SVG attribute animation. Never used inside AppShell -- the app
// interior stays calm and dense per plan.md's "operations tool, not a marketing site"
// direction (see docs/decisions/0003-phase-3-frontend-foundation.md).
//
// Node/edge coordinates are hand-placed in a 1600x900 viewBox, not computed at runtime
// -- a static, art-directed constellation reads as more deliberate than a randomized
// one, and avoids any hydration/layout-shift risk from client-side randomness.

interface Node {
  id: string;
  x: number;
  y: number;
  r: number;
}

interface Edge {
  from: string;
  to: string;
  /** Edges with a pulse get a traveling light animation; others stay static. */
  pulse?: { duration: number; delay: number; color: "accent" | "accent-2" };
}

const NODES: Node[] = [
  { id: "a", x: 180, y: 160, r: 3.5 },
  { id: "b", x: 340, y: 90, r: 2.5 },
  { id: "c", x: 420, y: 260, r: 4 },
  { id: "d", x: 620, y: 140, r: 3 },
  { id: "e", x: 760, y: 260, r: 3.5 },
  { id: "f", x: 560, y: 340, r: 2.5 },
  { id: "g", x: 300, y: 380, r: 3 },
  { id: "h", x: 120, y: 330, r: 2.5 },
  { id: "i", x: 900, y: 120, r: 3 },
  { id: "j", x: 1040, y: 240, r: 4 },
  { id: "k", x: 980, y: 380, r: 2.5 },
  { id: "l", x: 1180, y: 160, r: 3 },
  { id: "m", x: 1320, y: 280, r: 3.5 },
  { id: "n", x: 1240, y: 400, r: 2.5 },
  { id: "o", x: 1420, y: 120, r: 2.5 },
  { id: "p", x: 60, y: 560, r: 2.5 },
  { id: "q", x: 220, y: 620, r: 3.5 },
  { id: "r", x: 400, y: 560, r: 2.5 },
  { id: "s", x: 540, y: 660, r: 3 },
  { id: "t", x: 700, y: 580, r: 4 },
  { id: "u", x: 860, y: 660, r: 2.5 },
  { id: "v", x: 1020, y: 580, r: 3 },
  { id: "w", x: 1180, y: 640, r: 2.5 },
  { id: "x", x: 1340, y: 560, r: 3.5 },
  { id: "y", x: 1480, y: 460, r: 2.5 },
  { id: "z", x: 780, y: 780, r: 3 },
  { id: "aa", x: 380, y: 780, r: 2.5 },
  { id: "bb", x: 1100, y: 800, r: 2.5 },
];

const EDGES: Edge[] = [
  { from: "a", to: "b" },
  { from: "b", to: "c" },
  { from: "a", to: "h" },
  { from: "c", to: "d", pulse: { duration: 7, delay: 0, color: "accent" } },
  { from: "d", to: "e" },
  { from: "c", to: "f" },
  { from: "f", to: "g" },
  { from: "g", to: "h" },
  { from: "g", to: "c" },
  { from: "e", to: "i", pulse: { duration: 6, delay: 1.5, color: "accent-2" } },
  { from: "i", to: "j" },
  { from: "j", to: "e" },
  { from: "j", to: "k" },
  { from: "j", to: "l", pulse: { duration: 8, delay: 0.6, color: "accent" } },
  { from: "l", to: "m" },
  { from: "m", to: "n" },
  { from: "k", to: "n" },
  { from: "l", to: "o" },
  { from: "m", to: "o" },
  { from: "f", to: "t", pulse: { duration: 9, delay: 2.2, color: "accent-2" } },
  { from: "t", to: "s" },
  { from: "s", to: "r" },
  { from: "r", to: "q" },
  { from: "q", to: "p" },
  { from: "r", to: "g" },
  { from: "s", to: "aa" },
  { from: "t", to: "z", pulse: { duration: 7, delay: 3, color: "accent" } },
  { from: "z", to: "u" },
  { from: "u", to: "t" },
  { from: "u", to: "v" },
  { from: "v", to: "w" },
  { from: "w", to: "bb" },
  { from: "v", to: "x", pulse: { duration: 6.5, delay: 1, color: "accent-2" } },
  { from: "x", to: "m" },
  { from: "x", to: "y" },
  { from: "y", to: "n" },
];

function nodeById(id: string): Node {
  const node = NODES.find((n) => n.id === id);
  if (!node) throw new Error(`TechBackground: unknown node id "${id}"`);
  return node;
}

export function TechBackground(): React.JSX.Element {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-background">
      <div
        className="animate-drift absolute -left-40 -top-40 h-[36rem] w-[36rem] rounded-full opacity-25 blur-3xl"
        style={{
          background: "radial-gradient(circle, var(--color-accent) 0%, transparent 70%)",
        }}
      />
      <div
        className="animate-drift-slow absolute -right-32 top-1/3 h-[30rem] w-[30rem] rounded-full opacity-20 blur-3xl"
        style={{
          background: "radial-gradient(circle, var(--color-accent-2) 0%, transparent 70%)",
        }}
      />

      <svg
        viewBox="0 0 1600 900"
        preserveAspectRatio="xMidYMid slice"
        className="absolute inset-0 h-full w-full [mask-image:radial-gradient(ellipse_95%_85%_at_50%_40%,black,transparent)]"
        aria-hidden="true"
      >
        <defs>
          <filter id="node-glow" x="-200%" y="-200%" width="500%" height="500%">
            <feGaussianBlur stdDeviation="4" />
          </filter>
        </defs>

        <g stroke="var(--color-border)" strokeWidth="1" opacity="0.5">
          {EDGES.map((edge) => {
            const from = nodeById(edge.from);
            const to = nodeById(edge.to);
            return (
              <line key={`${edge.from}-${edge.to}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} />
            );
          })}
        </g>

        <g filter="url(#node-glow)">
          {EDGES.filter((e) => e.pulse).map((edge) => {
            const from = nodeById(edge.from);
            const to = nodeById(edge.to);
            const pulse = edge.pulse;
            if (!pulse) return null;
            const color =
              pulse.color === "accent" ? "var(--color-accent)" : "var(--color-accent-2)";
            return (
              <line
                key={`pulse-${edge.from}-${edge.to}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                pathLength={1}
                stroke={color}
                strokeWidth="3"
                strokeLinecap="round"
                strokeDasharray="0.1 1"
                className="animate-edge-pulse"
                style={{
                  animationDuration: `${pulse.duration}s`,
                  animationDelay: `${pulse.delay}s`,
                }}
              />
            );
          })}
        </g>
        <g>
          {EDGES.filter((e) => e.pulse).map((edge) => {
            const from = nodeById(edge.from);
            const to = nodeById(edge.to);
            const pulse = edge.pulse;
            if (!pulse) return null;
            const color =
              pulse.color === "accent" ? "var(--color-accent)" : "var(--color-accent-2)";
            return (
              <line
                key={`pulse-core-${edge.from}-${edge.to}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                pathLength={1}
                stroke={color}
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeDasharray="0.1 1"
                opacity="0.9"
                className="animate-edge-pulse"
                style={{
                  animationDuration: `${pulse.duration}s`,
                  animationDelay: `${pulse.delay}s`,
                }}
              />
            );
          })}
        </g>

        <g fill="var(--color-accent)" opacity="0.35" filter="url(#node-glow)">
          {NODES.map((node) => (
            <circle key={`${node.id}-glow`} cx={node.x} cy={node.y} r={node.r * 2} />
          ))}
        </g>
        <g fill="var(--color-accent)">
          {NODES.map((node) => (
            <circle key={node.id} cx={node.x} cy={node.y} r={node.r} opacity="0.85" />
          ))}
        </g>
      </svg>

      <div className="absolute inset-0 bg-[radial-gradient(ellipse_100%_60%_at_50%_100%,var(--color-background)_20%,transparent)]" />
    </div>
  );
}
