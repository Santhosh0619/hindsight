"""Generates app/seed/fixtures/catalog.json — 40 services across 8 teams with a
realistic tiered dependency graph, 3 shared hard dependencies (postgres-primary,
redis-cache, message-bus), and 2 deliberate single points of failure
(session-service, payment-gateway-adapter — each with exactly one dependent and no
redundant path).

Run once, by hand, whenever the catalog fixture needs regenerating:
    python -m app.seed.generate_catalog
The output is committed to the repo; `make seed` only ever *reads* it, never
regenerates it (see FRD "Out of Scope").

`role` (web_frontend / business_logic / async_worker / cache / queue /
primary_datastore / external_adapter / infra) is metadata for the other generators
in this package to pick a plausible affected service by kind — it is not a real
`Service` column and is stripped before the fixture's `import` section is handed to
`catalog_service.import_catalog`.
"""

import json
from pathlib import Path
from typing import Any, TypedDict

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "catalog.json"


class ServiceDef(TypedDict):
    name: str
    tier: int
    team: str
    role: str
    description: str
    runbook_url: str | None


TEAMS: dict[str, dict[str, str]] = {
    "Checkout": {
        "slack_handle": "#checkout-team",
        "escalation_contact": "checkout-oncall@hindsight.demo",
    },
    "Payments": {
        "slack_handle": "#payments-team",
        "escalation_contact": "payments-oncall@hindsight.demo",
    },
    "Identity": {
        "slack_handle": "#identity-team",
        "escalation_contact": "identity-oncall@hindsight.demo",
    },
    "Platform": {
        "slack_handle": "#platform-team",
        "escalation_contact": "platform-oncall@hindsight.demo",
    },
    "Search": {
        "slack_handle": "#search-team",
        "escalation_contact": "search-oncall@hindsight.demo",
    },
    "Notifications": {
        "slack_handle": "#notify-team",
        "escalation_contact": "notify-oncall@hindsight.demo",
    },
    "Catalog": {
        "slack_handle": "#catalog-team",
        "escalation_contact": "catalog-oncall@hindsight.demo",
    },
    "Observability": {
        "slack_handle": "#observability-team",
        "escalation_contact": "observability-oncall@hindsight.demo",
    },
}

SERVICES: list[ServiceDef] = [
    # Checkout
    {
        "name": "checkout-api",
        "tier": 1,
        "team": "Checkout",
        "role": "web_frontend",
        "description": "Public checkout entrypoint.",
        "runbook_url": "https://runbooks.hindsight.demo/checkout-api",
    },
    {
        "name": "cart-service",
        "tier": 1,
        "team": "Checkout",
        "role": "business_logic",
        "description": "Shopping cart state and pricing snapshot.",
        "runbook_url": None,
    },
    {
        "name": "order-service",
        "tier": 1,
        "team": "Checkout",
        "role": "business_logic",
        "description": "Order creation and lifecycle.",
        "runbook_url": "https://runbooks.hindsight.demo/order-service",
    },
    {
        "name": "checkout-worker",
        "tier": 2,
        "team": "Checkout",
        "role": "async_worker",
        "description": "Background order finalization.",
        "runbook_url": None,
    },
    {
        "name": "checkout-cache",
        "tier": 2,
        "team": "Checkout",
        "role": "cache",
        "description": "Cart/session read-through cache.",
        "runbook_url": None,
    },
    # Payments
    {
        "name": "payments-svc",
        "tier": 1,
        "team": "Payments",
        "role": "business_logic",
        "description": "Payment orchestration.",
        "runbook_url": "https://runbooks.hindsight.demo/payments-svc",
    },
    {
        "name": "payment-gateway-adapter",
        "tier": 1,
        "team": "Payments",
        "role": "external_adapter",
        "description": "Sole adapter to the external card processor.",
        "runbook_url": "https://runbooks.hindsight.demo/payment-gateway-adapter",
    },
    {
        "name": "ledger-service",
        "tier": 2,
        "team": "Payments",
        "role": "business_logic",
        "description": "Double-entry transaction ledger.",
        "runbook_url": None,
    },
    {
        "name": "fraud-detection",
        "tier": 2,
        "team": "Payments",
        "role": "business_logic",
        "description": "Real-time fraud scoring.",
        "runbook_url": None,
    },
    {
        "name": "payments-db",
        "tier": 1,
        "team": "Payments",
        "role": "primary_datastore",
        "description": "Payments domain datastore.",
        "runbook_url": None,
    },
    # Identity
    {
        "name": "auth-service",
        "tier": 1,
        "team": "Identity",
        "role": "web_frontend",
        "description": "Login, token issuance.",
        "runbook_url": "https://runbooks.hindsight.demo/auth-service",
    },
    {
        "name": "session-service",
        "tier": 1,
        "team": "Identity",
        "role": "business_logic",
        "description": "Sole session-validity authority; no fallback path.",
        "runbook_url": "https://runbooks.hindsight.demo/session-service",
    },
    {
        "name": "sso-gateway",
        "tier": 2,
        "team": "Identity",
        "role": "external_adapter",
        "description": "Enterprise SSO federation.",
        "runbook_url": None,
    },
    {
        "name": "user-profile-svc",
        "tier": 2,
        "team": "Identity",
        "role": "business_logic",
        "description": "User profile and preferences.",
        "runbook_url": None,
    },
    {
        "name": "identity-db",
        "tier": 2,
        "team": "Identity",
        "role": "primary_datastore",
        "description": "Identity domain datastore.",
        "runbook_url": None,
    },
    # Platform
    {
        "name": "postgres-primary",
        "tier": 1,
        "team": "Platform",
        "role": "primary_datastore",
        "description": "Shared relational store used by several domains.",
        "runbook_url": "https://runbooks.hindsight.demo/postgres-primary",
    },
    {
        "name": "redis-cache",
        "tier": 1,
        "team": "Platform",
        "role": "cache",
        "description": "Shared cache layer used across teams.",
        "runbook_url": "https://runbooks.hindsight.demo/redis-cache",
    },
    {
        "name": "message-bus",
        "tier": 1,
        "team": "Platform",
        "role": "queue",
        "description": "Shared event bus used across teams.",
        "runbook_url": "https://runbooks.hindsight.demo/message-bus",
    },
    {
        "name": "api-gateway",
        "tier": 1,
        "team": "Platform",
        "role": "web_frontend",
        "description": "Edge routing for every public API.",
        "runbook_url": "https://runbooks.hindsight.demo/api-gateway",
    },
    {
        "name": "service-mesh-proxy",
        "tier": 2,
        "team": "Platform",
        "role": "infra",
        "description": "Sidecar proxy fleet.",
        "runbook_url": None,
    },
    # Search
    {
        "name": "search-api",
        "tier": 2,
        "team": "Search",
        "role": "web_frontend",
        "description": "Search query entrypoint.",
        "runbook_url": None,
    },
    {
        "name": "search-indexer",
        "tier": 2,
        "team": "Search",
        "role": "async_worker",
        "description": "Async document indexing.",
        "runbook_url": None,
    },
    {
        "name": "elasticsearch-cluster",
        "tier": 2,
        "team": "Search",
        "role": "primary_datastore",
        "description": "Search index storage.",
        "runbook_url": None,
    },
    {
        "name": "autocomplete-svc",
        "tier": 3,
        "team": "Search",
        "role": "business_logic",
        "description": "Typeahead suggestions.",
        "runbook_url": None,
    },
    {
        "name": "search-cache",
        "tier": 3,
        "team": "Search",
        "role": "cache",
        "description": "Query result cache.",
        "runbook_url": None,
    },
    # Notifications
    {
        "name": "notification-svc",
        "tier": 2,
        "team": "Notifications",
        "role": "business_logic",
        "description": "Notification fan-out orchestration.",
        "runbook_url": None,
    },
    {
        "name": "email-sender",
        "tier": 2,
        "team": "Notifications",
        "role": "external_adapter",
        "description": "Transactional email delivery.",
        "runbook_url": None,
    },
    {
        "name": "sms-gateway",
        "tier": 3,
        "team": "Notifications",
        "role": "external_adapter",
        "description": "SMS delivery.",
        "runbook_url": None,
    },
    {
        "name": "push-notification-svc",
        "tier": 3,
        "team": "Notifications",
        "role": "external_adapter",
        "description": "Mobile push delivery.",
        "runbook_url": None,
    },
    {
        "name": "notification-queue",
        "tier": 2,
        "team": "Notifications",
        "role": "queue",
        "description": "Per-channel delivery queue.",
        "runbook_url": None,
    },
    # Catalog
    {
        "name": "catalog-api",
        "tier": 2,
        "team": "Catalog",
        "role": "web_frontend",
        "description": "Product catalog read API.",
        "runbook_url": None,
    },
    {
        "name": "inventory-service",
        "tier": 2,
        "team": "Catalog",
        "role": "business_logic",
        "description": "Stock levels and reservations.",
        "runbook_url": None,
    },
    {
        "name": "pricing-engine",
        "tier": 2,
        "team": "Catalog",
        "role": "business_logic",
        "description": "Price computation and promotions.",
        "runbook_url": None,
    },
    {
        "name": "product-search",
        "tier": 3,
        "team": "Catalog",
        "role": "business_logic",
        "description": "Product-specific search facets.",
        "runbook_url": None,
    },
    {
        "name": "catalog-db",
        "tier": 2,
        "team": "Catalog",
        "role": "primary_datastore",
        "description": "Catalog domain datastore.",
        "runbook_url": None,
    },
    # Observability
    {
        "name": "metrics-collector",
        "tier": 3,
        "team": "Observability",
        "role": "infra",
        "description": "Metrics ingestion.",
        "runbook_url": None,
    },
    {
        "name": "log-aggregator",
        "tier": 3,
        "team": "Observability",
        "role": "infra",
        "description": "Centralized log storage.",
        "runbook_url": None,
    },
    {
        "name": "alerting-svc",
        "tier": 3,
        "team": "Observability",
        "role": "infra",
        "description": "Alert routing and paging.",
        "runbook_url": None,
    },
    {
        "name": "cdn-edge",
        "tier": 2,
        "team": "Observability",
        "role": "infra",
        "description": "Edge CDN in front of the API gateway.",
        "runbook_url": None,
    },
    {
        "name": "dns-resolver",
        "tier": 2,
        "team": "Observability",
        "role": "infra",
        "description": "Internal service-discovery DNS.",
        "runbook_url": None,
    },
]

# (from, to, kind, criticality). postgres-primary / redis-cache / message-bus are
# each depended on by several unrelated services (the "3 shared hard dependencies").
# session-service and payment-gateway-adapter each have exactly one dependent and no
# alternate route to the same function (the "2 deliberate single points of failure").
EDGES: list[tuple[str, str, str, str]] = [
    ("api-gateway", "checkout-api", "calls", "soft"),
    ("api-gateway", "auth-service", "calls", "soft"),
    ("api-gateway", "catalog-api", "calls", "soft"),
    ("api-gateway", "search-api", "calls", "soft"),
    ("api-gateway", "notification-svc", "calls", "soft"),
    ("api-gateway", "dns-resolver", "calls", "hard"),
    ("cdn-edge", "api-gateway", "calls", "soft"),
    ("service-mesh-proxy", "api-gateway", "calls", "soft"),
    ("checkout-api", "cart-service", "calls", "hard"),
    ("checkout-api", "auth-service", "calls", "hard"),
    ("checkout-api", "payments-svc", "calls", "hard"),
    ("checkout-api", "checkout-cache", "reads_from", "soft"),
    ("cart-service", "catalog-api", "calls", "hard"),
    ("cart-service", "postgres-primary", "reads_from", "hard"),
    ("order-service", "postgres-primary", "reads_from", "hard"),
    ("order-service", "message-bus", "publishes_to", "hard"),
    ("checkout-worker", "message-bus", "reads_from", "hard"),
    ("checkout-worker", "order-service", "calls", "hard"),
    ("checkout-worker", "notification-svc", "calls", "soft"),
    ("payments-svc", "payment-gateway-adapter", "calls", "hard"),
    ("payments-svc", "ledger-service", "calls", "hard"),
    ("payments-svc", "fraud-detection", "calls", "soft"),
    ("payments-svc", "payments-db", "reads_from", "hard"),
    ("ledger-service", "payments-db", "reads_from", "hard"),
    ("fraud-detection", "redis-cache", "reads_from", "soft"),
    ("auth-service", "session-service", "calls", "hard"),
    ("auth-service", "identity-db", "reads_from", "hard"),
    ("session-service", "redis-cache", "reads_from", "hard"),
    ("sso-gateway", "auth-service", "calls", "soft"),
    ("user-profile-svc", "identity-db", "reads_from", "hard"),
    ("user-profile-svc", "postgres-primary", "reads_from", "soft"),
    ("user-profile-svc", "redis-cache", "reads_from", "soft"),
    ("search-api", "elasticsearch-cluster", "reads_from", "hard"),
    ("search-api", "search-cache", "reads_from", "soft"),
    ("search-indexer", "elasticsearch-cluster", "publishes_to", "hard"),
    ("search-indexer", "message-bus", "reads_from", "hard"),
    ("autocomplete-svc", "search-cache", "reads_from", "hard"),
    ("autocomplete-svc", "elasticsearch-cluster", "reads_from", "soft"),
    ("notification-svc", "notification-queue", "publishes_to", "hard"),
    ("notification-svc", "email-sender", "calls", "soft"),
    ("notification-svc", "sms-gateway", "calls", "soft"),
    ("notification-svc", "push-notification-svc", "calls", "soft"),
    ("email-sender", "notification-queue", "reads_from", "hard"),
    ("sms-gateway", "notification-queue", "reads_from", "hard"),
    ("push-notification-svc", "notification-queue", "reads_from", "hard"),
    ("catalog-api", "catalog-db", "reads_from", "hard"),
    ("catalog-api", "redis-cache", "reads_from", "soft"),
    ("inventory-service", "catalog-db", "reads_from", "hard"),
    ("inventory-service", "postgres-primary", "publishes_to", "soft"),
    ("inventory-service", "message-bus", "publishes_to", "soft"),
    ("pricing-engine", "catalog-db", "reads_from", "hard"),
    ("product-search", "elasticsearch-cluster", "reads_from", "soft"),
    ("product-search", "catalog-api", "calls", "soft"),
    ("metrics-collector", "message-bus", "reads_from", "soft"),
    ("log-aggregator", "message-bus", "reads_from", "soft"),
    ("alerting-svc", "metrics-collector", "calls", "hard"),
    ("alerting-svc", "log-aggregator", "calls", "soft"),
]


def build_fixture() -> dict[str, Any]:
    return {
        "import": {
            "teams": [
                {
                    "name": name,
                    "slack_handle": v["slack_handle"],
                    "escalation_contact": v["escalation_contact"],
                }
                for name, v in TEAMS.items()
            ],
            "services": [
                {
                    "name": s["name"],
                    "tier": s["tier"],
                    "team_name": s["team"],
                    "description": s["description"],
                    "runbook_url": s["runbook_url"],
                }
                for s in SERVICES
            ],
            "edges": [
                {"from_service_name": f, "to_service_name": t, "kind": k, "criticality": c}
                for f, t, k, c in EDGES
            ],
        },
        # Generator-only metadata -- read by generate_postmortems.py/generate_
        # incidents.py to pick a plausible service by role, never sent to
        # catalog_service.import_catalog.
        "service_roles": {s["name"]: s["role"] for s in SERVICES},
    }


def main() -> None:
    fixture = build_fixture()
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(fixture, indent=2, sort_keys=False) + "\n")
    print(
        f"Wrote {len(SERVICES)} services, {len(TEAMS)} teams, {len(EDGES)} edges to {FIXTURE_PATH}"
    )


if __name__ == "__main__":
    main()
