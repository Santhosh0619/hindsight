# ADR 0018: UI Design Pass — Replacing the Flat Grid with an On-Theme Network

## Context

Phase 3's public-facing background (a static circuit-grid pattern plus two slow drifting
glow blobs) was judged weak when reviewed later in the project — it read as generic
dark-SaaS decoration, not the "AI and tech" look actually wanted, and this was
deliberately deferred rather than iterated on incrementally (see the project's own
standing decision to do a real design pass late in the build, once there were real
screens to design around instead of three auth screens in isolation). With no
image-generation tool available, the constraint was to build the best achievable
version of that look in pure CSS/SVG.

## Decision

Replaced the flat grid with an animated node-graph/network: a hand-placed constellation
of glowing nodes connected by thin edges, with light pulses traveling along a subset of
edges. This wasn't picked as generic "AI" mood decoration — it's literally the shape of
what Hindsight actually is (a service-dependency graph, a multi-node agent pipeline), so
the background is on-theme rather than decorative for its own sake. The pulse animation
uses `pathLength={1}` plus a CSS `stroke-dashoffset` keyframe rather than SVG SMIL or a
JS animation loop, normalizing the sweep to each edge's own length regardless of its
actual on-screen size, and keeping every animation GPU-cheap and framework-free.

Added a small `Logomark` component (a three-node graph at brand scale) used everywhere
the "Hindsight" wordmark appears — Landing/Login/Signup header and the AppShell sidebar
— so the brand mark visually echoes the background instead of being an unrelated
wordmark sitting in front of it.

Scope was deliberately split, not applied everywhere uniformly: the full animated
background stays on the public marketing pages (Landing, Login, Signup, Onboarding)
only. The app interior (dashboard, incident detail, etc.) gets a lighter, restrained
touch — the Logomark in the sidebar header and a subtle glow on the active nav item —
without a second animated background. This preserves Phase 3's original "operations
tool, not a marketing site" reasoning for the interior: a responder reading an incident
brief at 2am shouldn't compete with a moving background for attention, even though the
marketing pages that a recruiter actually evaluates first can afford more visual
presence.

Verified visually before considering it done, not just by passing type/lint/build
checks — loaded the actual pages in a real browser and iterated twice on the pulse
visibility (the first pass's pulses were too subtle to read at normal viewing distance;
added a blurred glow layer under the sharp core stroke to fix it) before landing on the
final version. This is the same "don't guess blind on a subjective visual decision"
lesson the original Phase 3 miss taught — confirmed with the user directly before
merging, not assumed correct from the assistant's own judgment alone.
