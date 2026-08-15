"""Generates app/seed/fixtures/postmortems.json — 80 postmortems spanning 3 years
across the 12 scenarios in scenarios.py, 6-7 per scenario, each composed from one of
that scenario's vocabulary variants against a real service picked from the catalog
fixture by role. Deterministic given `random.Random(_SEED)`, never the module-global
`random` state, so regenerating reproduces byte-identical output (FR-01/NFR
Constraints).

Run once, by hand, whenever the postmortem fixture needs regenerating:
    python -m app.seed.generate_postmortems
The output is committed to the repo; `make seed` only ever *reads* it.
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.seed.scenarios import SCENARIOS, Scenario, Vocabulary

CATALOG_PATH = Path(__file__).parent / "fixtures" / "catalog.json"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "postmortems.json"

_SEED = 1104
# Fixed anchor, not datetime.now() -- a generation run's output must be byte-identical
# to the last one until someone deliberately regenerates it (NFR Constraints).
_ANCHOR = datetime(2026, 1, 1)
_THREE_YEARS_DAYS = 3 * 365

_SEVERITY_WEIGHTS = [("sev1", 1), ("sev2", 3), ("sev3", 5), ("sev4", 3)]

# 8 scenarios get 7 postmortems, 4 get 6 -- totals exactly 80.
_EXTRA_COUNT_KEYS = {
    "connection_pool_exhaustion",
    "retry_storm",
    "cache_stampede",
    "poison_message",
    "cert_expiry",
    "disk_saturation",
    "config_rollout",
    "dependency_version_drift",
}


def _weighted_severity(rng: random.Random) -> str:
    pool = [sev for sev, weight in _SEVERITY_WEIGHTS for _ in range(weight)]
    return rng.choice(pool)


def _title_for(scenario: Scenario, service: str) -> str:
    readable = scenario.key.replace("_", " ")
    return f"{service}: {readable}"


def _compose_raw_text(vocab: Vocabulary, service: str) -> str:
    sections = [
        f"Summary:\n{vocab.summary.format(service=service)}",
        f"Timeline:\n{vocab.timeline.format(service=service)}",
        f"Root Cause:\n{vocab.root_cause.format(service=service)}",
        f"Impact:\n{vocab.impact.format(service=service)}",
        f"Remediation:\n{vocab.remediation.format(service=service)}",
        f"Action Items:\n{vocab.action_items.format(service=service)}",
    ]
    if vocab.detection is not None:
        sections.append(f"Detection:\n{vocab.detection.format(service=service)}")
    return "\n\n".join(sections)


def _facts_for(vocab: Vocabulary, service: str) -> list[dict[str, str]]:
    facts = [
        {
            "fact_type": "trigger",
            "statement": vocab.summary.format(service=service),
            "section_label": "Summary",
        },
        {
            "fact_type": "root_cause",
            "statement": vocab.root_cause.format(service=service),
            "section_label": "Root Cause",
        },
        {
            "fact_type": "remediation",
            "statement": vocab.remediation.format(service=service),
            "section_label": "Remediation",
        },
        {
            "fact_type": "contributing_factor",
            "statement": vocab.impact.format(service=service),
            "section_label": "Impact",
        },
    ]
    if vocab.detection is not None:
        facts.append(
            {
                "fact_type": "detection_gap",
                "statement": vocab.detection.format(service=service),
                "section_label": "Detection",
            }
        )
    return facts


def _load_services_by_role() -> dict[str, list[str]]:
    catalog = json.loads(CATALOG_PATH.read_text())
    by_role: dict[str, list[str]] = {}
    for name, role in catalog["service_roles"].items():
        by_role.setdefault(role, []).append(name)
    return by_role


def build_fixture() -> list[dict[str, Any]]:
    rng = random.Random(_SEED)
    services_by_role = _load_services_by_role()
    postmortems: list[dict[str, Any]] = []

    for scenario in SCENARIOS:
        count = 7 if scenario.key in _EXTRA_COUNT_KEYS else 6
        candidates = services_by_role[scenario.service_role]
        for i in range(count):
            service = candidates[i % len(candidates)]
            vocab = scenario.vocabularies[i % len(scenario.vocabularies)]
            occurred_at = _ANCHOR - timedelta(days=rng.randint(1, _THREE_YEARS_DAYS))
            postmortems.append(
                {
                    "title": _title_for(scenario, service),
                    "raw_text": _compose_raw_text(vocab, service),
                    "occurred_at": occurred_at.isoformat() + "Z",
                    "duration_minutes": rng.randint(10, 180),
                    "severity": _weighted_severity(rng),
                    "affected_service_names": [service],
                    "facts": _facts_for(vocab, service),
                    "failure_mode": scenario.family.value,
                    "scenario_key": scenario.key,
                }
            )

    rng.shuffle(postmortems)
    return postmortems


def main() -> None:
    fixture = build_fixture()
    FIXTURE_PATH.write_text(json.dumps(fixture, indent=2, sort_keys=False) + "\n")
    print(f"Wrote {len(fixture)} postmortems to {FIXTURE_PATH}")


if __name__ == "__main__":
    main()
