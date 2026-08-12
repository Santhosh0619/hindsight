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
