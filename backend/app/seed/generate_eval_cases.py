"""Generates app/seed/fixtures/eval_cases.json — 20 golden cases for Phase 12's
evaluation harness: alert text plus the scenario whose postmortems are the genuinely
correct match, known because the generator itself wrote both. The first 12 reuse the
demo incidents' own alert text (`Scenario.alert_variants[0]`); the remaining 8 use
each scenario's second alert variant, giving eval coverage independent of exactly
which incidents got a precomputed brief. `seed.py` resolves `expected_scenario_key`
to real postmortem ids at load time, the same way it resolves incidents (FRD Gap #4)
-- `EvalCase.expected_postmortem_ids` doesn't exist until postmortems are actually
inserted.

Run once, by hand, whenever the eval-cases fixture needs regenerating:
    python -m app.seed.generate_eval_cases
The output is committed to the repo; `make seed` only ever *reads* it.
"""

import json
from pathlib import Path
from typing import Any

from app.seed.scenarios import SCENARIOS

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "eval_cases.json"

# The 8 scenarios that get a second eval case (using their second alert variant) --
# same set precomputed briefs use, so the two "8 out of 12" subsets tell one
# consistent story about which scenarios this demo build treats as its flagship
# examples.
_SECOND_CASE_SCENARIO_KEYS = {
    "connection_pool_exhaustion",
    "retry_storm",
    "cache_stampede",
    "poison_message",
    "cert_expiry",
    "config_rollout",
    "thread_pool_starvation",
    "quota_exhaustion",
}


def build_fixture() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        cases.append(
            {
                "name": f"{scenario.key}-primary",
                "incident_text": scenario.alert_variants[0],
                "expected_scenario_key": scenario.key,
            }
        )
    for scenario in SCENARIOS:
        if scenario.key not in _SECOND_CASE_SCENARIO_KEYS:
            continue
        cases.append(
            {
                "name": f"{scenario.key}-secondary",
                "incident_text": scenario.alert_variants[1],
                "expected_scenario_key": scenario.key,
            }
        )
    return cases


def main() -> None:
    fixture = build_fixture()
    FIXTURE_PATH.write_text(json.dumps(fixture, indent=2, sort_keys=False) + "\n")
    print(f"Wrote {len(fixture)} eval cases to {FIXTURE_PATH}")


if __name__ == "__main__":
    main()
