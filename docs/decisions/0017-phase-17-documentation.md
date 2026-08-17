# ADR 0017: Documentation — Two Scope Conflicts, Resolved Before Writing Anything

## 1. Master-Prompt.md's Phase 17 spec conflicts with two standing project decisions

**Context.** Master-Prompt.md's Phase 17 README order calls for a hero screenshot
above the fold and one screenshot per feature bullet, plus a `docs/screenshots/`
folder — and separately, for consolidating plan.md §17's 12 technical defense
questions into a committed `docs/interview-prep.md`. Both directly conflict with
decisions already made earlier in this project: screenshots and recordings are
captured once, in a dedicated session after Phase 18, not per-phase (a standing
preference from Phase 3); and the file Master-Prompt.md calls `docs/interview-prep.md`
was already renamed to `docs/design-notes.md` and made local-only/gitignored, because
the public repo carrying visible evidence of interview preparation was judged bad for
how a recruiter would read the project (the repo privacy cleanup, done mid-project).

**Decision.** Asked the user directly rather than picking a default and writing
around it. Confirmed: no images or video this phase at all — not even placeholders —
ship text-only and do the capture pass separately later. And confirmed: the local,
gitignored `docs/design-notes.md` already satisfies the *private* half of the
Phase-17 checklist item; this phase's job for the *public* half is folding the same
technical substance (one-database rationale, RRF, the corrective loop, the honest
tied-ablation result, the system's real weaknesses) into `README.md` and
`docs/architecture.md` as ordinary prose, with zero Q&A or interview framing anywhere
in the committed diff. Both are the same underlying policy applied consistently: the
substance of good engineering documentation is worth keeping, the "this person is
job-hunting" framing is not, regardless of which specific file it would have lived in.

## 2. Every number in the new docs was independently re-verified, not carried over

**Context.** This project has 16 ADRs' worth of "verify empirically, don't assume" as
an established discipline (Phase 14's FastAPI route traversal, Phase 15's dependency-
resolution order, Phase 16's live workflow_dispatch check). Documentation is exactly
the kind of work where that discipline is easiest to skip — it would have been faster
to copy the evaluation numbers straight out of ADR 0012, the corpus size out of memory
from Phase 11, and the schema straight out of plan.md §8's original sketch.

**Decision.** Didn't. Re-ran the actual evaluation harness
(`app.services.evaluation.cli --mode all`) against the live seeded corpus rather than
citing ADR 0012's numbers — they came back identical (recall@1=0.700, recall@5=0.950,
MRR=0.808, citation_validity=1.0, tied across all three retrieval configurations),
which is itself confirmation the system's behavior hasn't drifted since Phase 12, not
something that could have been assumed without running it again. Counted the seed
corpus directly from the fixture JSON files (80 postmortems, 40 services, 8 teams, 57
edges, 12 incidents) instead of trusting a remembered number. Wrote `docs/data-model.md`
from the real SQLAlchemy models and the real Alembic migration's index definitions,
not from plan.md §8's pre-implementation sketch — which turned out to have drifted in
two real, documented ways (`agent_runs.brief_id`, added so the observability page can
resolve cache-hit status by a direct join; `eval_runs.mode`, added so a run can be
tagged by which retrieval configuration produced it, which is the column that makes
the whole ablation table possible). The single combined review pass re-ran the
evaluation harness independently a second time and got the same numbers, and
spot-checked the schema claims against the model files a second time — both came back
clean, which is the actual value of the discipline: a false claim in a README a
recruiter reads is a worse failure mode than a false claim anywhere else in this
project, and it's cheap to just check.
