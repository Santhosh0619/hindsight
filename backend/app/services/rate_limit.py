import time


class TokenBucket:
    """In-memory, single-process token bucket keyed by an arbitrary string (e.g. IP).

    Deliberately not shared across replicas/workers — see NFR "Reliability" in
    docs/modules/phase-2-auth-workspaces/NFR.md for why that's an accepted limitation
    at this project's scale, and Phase 14 for the project-wide rate-limiting pass.
    """

    def __init__(self, capacity: int, refill_seconds: float) -> None:
        self._capacity = capacity
        self._refill_seconds = refill_seconds
        self._buckets: dict[str, tuple[float, float]] = {}

    def consume(self, key: str) -> bool:
        now = time.monotonic()
        tokens, last_refill = self._buckets.get(key, (float(self._capacity), now))

        elapsed = now - last_refill
        refilled = min(self._capacity, tokens + elapsed / self._refill_seconds)

        if refilled < 1:
            self._buckets[key] = (refilled, now)
            return False

        self._buckets[key] = (refilled - 1, now)
        return True


demo_signup_bucket = TokenBucket(capacity=5, refill_seconds=12 * 60)

# Bounds compute (and, once an LLM key exists, spend) a single already-minted demo
# guest session can trigger via brief generation -- independent of demo_signup_bucket,
# which only bounds how many guest sessions one IP can mint in the first place.
demo_brief_bucket = TokenBucket(capacity=10, refill_seconds=10 * 60)

# Phase 14 hardening -- see docs/modules/phase-14-hardening/FRD.md "Rate limiting".
# Shared by /auth/login and /auth/signup -- both are cheap-to-call, unauthenticated
# endpoints doing real password work per call, the same credential-stuffing/signup-spam
# threat model. Deliberately excludes /auth/refresh -- see auth.py's own comment.
login_bucket = TokenBucket(capacity=30, refill_seconds=60)

# Keyed by workspace_id, not caller -- a workspace's aggregate brief-generation rate is
# the thing worth bounding, independent of demo_brief_bucket (which bounds a single
# demo guest session's own usage, keyed by user id).
brief_bucket = TokenBucket(capacity=20, refill_seconds=60)
