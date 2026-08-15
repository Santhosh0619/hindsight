"""Generates app/seed/fixtures/incidents.json — 12 demo incidents, one per
scenario in scenarios.py, using a *third* vocabulary variant (`Scenario.
alert_variants[0]`) beyond the postmortems' own two, so matching an incident back to
its postmortems is a real test of retrieval generalizing across vocabulary. 8 of the
12 are flagged for a precomputed brief (`has_precomputed_brief`); `seed.py` resolves
`matched_scenario_key` to real postmortem/service ids at load time (they don't exist
yet when this generator runs) and does the actual retrieval/blast-radius computation
that produces the precomputed brief -- see FRD Gap #4.

Run once, by hand, whenever the incidents fixture needs regenerating:
    python -m app.seed.generate_incidents
The output is committed to the repo; `make seed` only ever *reads* it.
"""

import json
from pathlib import Path
from typing import Any

from app.seed.scenarios import SCENARIOS

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "incidents.json"

# The 8 scenarios whose demo incident gets a precomputed brief -- chosen to cover a
# spread of severities and families, not the first 8 alphabetically. The remaining 4
# incidents exist with no brief yet, so a demo visitor generating a *new* brief has
# realistic incidents to try it against beyond just creating their own from scratch.
_PRECOMPUTED_SCENARIO_KEYS = {
    "connection_pool_exhaustion",
    "retry_storm",
    "cache_stampede",
    "poison_message",
    "cert_expiry",
    "config_rollout",
    "thread_pool_starvation",
    "quota_exhaustion",
}

_SEVERITY_BY_SCENARIO = {
    "connection_pool_exhaustion": "sev2",
    "retry_storm": "sev3",
    "cache_stampede": "sev2",
    "poison_message": "sev2",
    "cert_expiry": "sev1",
    "disk_saturation": "sev1",
    "config_rollout": "sev2",
    "dependency_version_drift": "sev3",
    "clock_skew": "sev2",
    "thread_pool_starvation": "sev3",
    "dns_failover": "sev2",
    "quota_exhaustion": "sev3",
}


def _title_for(alert_text: str) -> str:
    return alert_text[:1].upper() + alert_text[1:120]


def build_fixture() -> list[dict[str, Any]]:
    incidents: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        alert_text = scenario.alert_variants[0]
        incidents.append(
            {
                "title": _title_for(alert_text),
                "raw_alert_text": alert_text,
                "severity": _SEVERITY_BY_SCENARIO[scenario.key],
                "matched_scenario_key": scenario.key,
                "has_precomputed_brief": scenario.key in _PRECOMPUTED_SCENARIO_KEYS,
            }
        )
    return incidents


def main() -> None:
    fixture = build_fixture()
    FIXTURE_PATH.write_text(json.dumps(fixture, indent=2, sort_keys=False) + "\n")
    with_briefs = sum(1 for i in fixture if i["has_precomputed_brief"])
    print(
        f"Wrote {len(fixture)} incidents ({with_briefs} with a precomputed brief) to {FIXTURE_PATH}"
    )


if __name__ == "__main__":
    main()
