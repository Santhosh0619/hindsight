"""The 12 failure scenarios named in plan.md §12, each mapped to the Phase 6
extraction taxonomy family it classifies under (`app/services/extraction/
taxonomy.py`) and to 2 distinct vocabulary sets for describing the same underlying
failure -- see FRD Gap #1 for why these are a different list from Phase 6's own
12-family classification taxonomy, and Gap #3 for why the phrase banks are written
against `generate_postmortems.py`'s exact section headers.

A third, even more different vocabulary set lives in each `Scenario.alert_variants`
below -- `generate_incidents.py` uses that one for alert text, so matching an incident
back to its postmortems is a genuine test of retrieval generalizing across
vocabulary, not a substring match.
"""

from dataclasses import dataclass

from app.services.extraction.taxonomy import FailureModeFamily

# A postmortem's affected service is picked from the catalog fixture by this role tag
# (see generate_catalog.py's SERVICES). Matches the scenario's actual failure surface,
# not picked arbitrarily.
ServiceRole = str


@dataclass(frozen=True)
class Vocabulary:
    """One way of describing a scenario's failure -- section text keyed by the exact
    header `chunk.py`'s section-heading pattern recognizes, so each maps to a real,
    separately-chunked section a generated fact can cite."""

    summary: str
    timeline: str
    root_cause: str
    impact: str
    remediation: str
    action_items: str
    detection: str | None = None


@dataclass(frozen=True)
class Scenario:
    key: str
    family: FailureModeFamily
    service_role: ServiceRole
    vocabularies: list[Vocabulary]
    alert_variants: list[str]


SCENARIOS: list[Scenario] = [
    Scenario(
        key="connection_pool_exhaustion",
        family=FailureModeFamily.CAPACITY_EXHAUSTION,
        service_role="primary_datastore",
        vocabularies=[
            Vocabulary(
                summary="{service} exhausted its outbound connection pool during a "
                "traffic spike, causing a five-minute window of elevated latency and "
                "request timeouts.",
                timeline="At first the on-call engineer suspected a bad deploy from "
                "earlier that day and rolled it back, which did not help.",
                root_cause="The connection pool size was left at its default of 10, "
                "far below what the service's actual concurrent request volume "
                "required once traffic exceeded the previous quarter's peak.",
                impact="Roughly 8% of requests during the window returned a 503 or "
                "timed out client-side.",
                remediation="The pool size was raised to 50 and a queueing timeout "
                "was added so exhaustion degrades gracefully instead of hanging "
                "connections indefinitely.",
                action_items="Add pool-utilization alerting. Load-test the new pool "
                "size before the next seasonal traffic peak.",
                detection="No alert fired on pool utilization itself -- only "
                "downstream request-latency alerts caught this, several minutes "
                "after the pool was already saturated.",
            ),
            Vocabulary(
                summary="{service} ran out of available client slots under load, "
                "and every service depending on it queued behind the same limited "
                "pool.",
                timeline="An initial hypothesis blamed a network partition between "
                "availability zones; packet captures ruled that out within twenty "
                "minutes.",
                root_cause="A recent capacity-planning review had not accounted for "
                "a new caller that opened long-lived connections instead of "
                "releasing them between requests, silently consuming a growing "
                "share of the fixed pool.",
                impact="Downstream callers saw their own request queues back up, "
                "and the incident briefly looked like a multi-service outage before "
                "the shared root cause was found.",
                remediation="The offending caller was patched to release "
                "connections properly, and a hard cap on per-caller pool share was "
                "added as a backstop.",
                action_items="Audit every other high-traffic caller for the same "
                "connection-lifecycle bug. Document the pool-sizing formula.",
            ),
        ],
        alert_variants=[
            "checkout is throwing 500s, database looks maxed out",
            "elevated error rate on the order path, DB connections all busy",
        ],
    ),
    Scenario(
        key="retry_storm",
        family=FailureModeFamily.SCALING_LOAD,
        service_role="external_adapter",
        vocabularies=[
            Vocabulary(
                summary="A brief upstream blip on {service} triggered a retry storm "
                "that outlasted the original outage by twenty minutes.",
                timeline="On-call first assumed the upstream provider was still "
                "down, but the provider's own status page had already recovered "
                "five minutes earlier.",
                root_cause="Every caller retried failed requests immediately with "
                "no backoff or jitter, so the moment the upstream recovered it was "
                "immediately re-saturated by a synchronized wave of retries.",
                impact="Sustained 3x normal request volume against {service} for "
                "twenty minutes after the real outage had already ended.",
                remediation="Exponential backoff with jitter was added to every "
                "retry path calling {service}, and a circuit breaker now trips "
                "after a threshold of consecutive failures.",
                action_items="Standardize the retry/backoff library across all "
                "outbound HTTP clients instead of each team implementing its own.",
            ),
            Vocabulary(
                summary="A short-lived hiccup calling out to {service} turned into a "
                "self-inflicted overload once the retries synchronized.",
                timeline="Dashboards initially suggested the incident was still "
                "ongoing on the provider side, delaying the correct diagnosis.",
                root_cause="A fixed one-second retry interval, shared by every "
                "instance of the calling service, meant thousands of retries fired "
                "in the same one-second window over and over.",
                impact="Request volume against {service} was three times normal "
                "for nearly half an hour after the original blip resolved.",
                remediation="Retries now use randomized jitter so instances no "
                "longer retry in lockstep, and a circuit breaker caps concurrent "
                "outbound retries.",
                action_items="Add an automated check that flags any new outbound "
                "client missing jitter in its retry configuration.",
            ),
        ],
        alert_variants=[
            "traffic to the payment provider tripled out of nowhere",
            "outbound call volume way above normal, provider says they're fine now",
        ],
    ),
    Scenario(
        key="cache_stampede",
        family=FailureModeFamily.SCALING_LOAD,
        service_role="cache",
        vocabularies=[
            Vocabulary(
                summary="{service} evicted a hot key at the same moment thousands of "
                "requests needed it, and every one of them fell through to the "
                "origin at once.",
                timeline="The team initially suspected the cache cluster itself had "
                "crashed, since request latency to it spiked at the same time.",
                root_cause="The hot key's TTL expired with no jitter, so every "
                "instance's local view of the cache went stale in the same "
                "millisecond, and none of them coordinated on who should "
                "repopulate it.",
                impact="The origin datastore behind {service} saw a 40x spike in "
                "read load for about ninety seconds.",
                remediation="Added TTL jitter so keys don't all expire together, "
                "and a single-flight lock so only one request repopulates a given "
                "key while the rest wait on that result instead of all hitting the "
                "origin.",
                action_items="Identify other high-traffic cache keys with the same "
                "synchronized-TTL risk and apply the same jitter fix proactively.",
            ),
            Vocabulary(
                summary="A single popular cache entry behind {service} expired and "
                "every waiting request stampeded the origin simultaneously.",
                timeline="Initial paging suggested a database outage, since query "
                "latency to the origin store spiked in step with the cache miss.",
                root_cause="No mechanism existed to serialize origin fetches for a "
                "single key on a cache miss, so a thundering herd of identical "
                "queries hit the origin at once instead of one query populating "
                "the cache for everyone else.",
                impact="Origin query latency spiked enough to trip an unrelated "
                "downstream timeout, briefly widening the incident's blast radius.",
                remediation="A request-coalescing layer was added in front of the "
                "origin so concurrent misses for the same key share one fetch.",
                action_items="Extend request coalescing to the other two "
                "high-traffic cache namespaces that share this same risk.",
            ),
        ],
        alert_variants=[
            "origin database load spiked 40x for no obvious reason",
            "sudden latency spike right after a cache eviction",
        ],
    ),
    Scenario(
        key="poison_message",
        family=FailureModeFamily.CODE_DEFECT,
        service_role="queue",
        vocabularies=[
            Vocabulary(
                summary="A single malformed message on {service} was repeatedly "
                "redelivered and crashed every consumer that tried to process it.",
                timeline="The on-call engineer initially restarted the consumer "
                "fleet, which briefly appeared to help before the same crash "
                "recurred within a minute.",
                root_cause="A message with an unexpected null field bypassed input "
                "validation at the producer, and the consumer's deserializer threw "
                "an unhandled exception on every delivery attempt instead of "
                "moving the message aside.",
                impact="The consumer fleet crash-looped for close to an hour, "
                "backing up the rest of the queue behind the one bad message.",
                remediation="Added a dead-letter queue so a message that fails "
                "processing a fixed number of times is moved aside instead of "
                "blocking the whole queue, plus stricter producer-side validation.",
                action_items="Add a schema-validation gate at the producer for "
                "every topic that doesn't already have one.",
            ),
            Vocabulary(
                summary="One bad event on {service} kept getting redelivered and "
                "taking down whichever consumer instance picked it up next.",
                timeline="Metrics showed consumer lag growing steadily, which "
                "initially looked like a simple capacity problem rather than a "
                "single message repeatedly crashing every worker.",
                root_cause="The consumer had no per-message retry limit, so a "
                "message that always fails to deserialize was retried forever, "
                "each attempt crashing the worker that picked it up.",
                impact="Queue lag grew for the better part of an hour before the "
                "actual cause -- one message, not a capacity shortfall -- was "
                "identified.",
                remediation="A maximum redelivery count now routes a "
                "repeatedly-failing message to a dead-letter queue for manual "
                "inspection instead of endless retry.",
                action_items="Build a small dashboard for dead-letter queue depth "
                "so a growing pile of poison messages is visible before it causes "
                "an incident.",
            ),
        ],
        alert_variants=[
            "consumers keep crash-looping on the notification queue",
            "queue lag climbing, workers keep restarting",
        ],
    ),
    Scenario(
        key="cert_expiry",
        family=FailureModeFamily.CONFIGURATION_ERROR,
        service_role="external_adapter",
        vocabularies=[
            Vocabulary(
                summary="The TLS certificate for {service} expired at midnight, and "
                "every caller started failing the handshake within seconds.",
                timeline="The first reports were mistaken for a DNS problem, since "
                "callers just saw connection failures with no useful error detail "
                "at first glance.",
                root_cause="Certificate renewal was a manual process the team had "
                "meant to automate the previous quarter but never got to, and "
                "nobody was tracking the expiry date on a calendar either.",
                impact="Every caller of {service} failed outright for eighteen "
                "minutes until a new certificate was issued and deployed.",
                remediation="Certificate renewal was automated end-to-end, and a "
                "45-day-before-expiry alert was added as a backstop even for "
                "automated certificates.",
                action_items="Audit every other service for a manually-managed "
                "certificate with no expiry alerting.",
            ),
            Vocabulary(
                summary="An expired TLS cert on {service} broke every inbound "
                "connection the instant the clock passed midnight.",
                timeline="Because the failure was so sudden and total, the team's "
                "first guess was a bad deploy that had gone out around the same "
                "time, which turned out to be unrelated.",
                root_cause="The certificate had a 90-day validity window and no "
                "automated renewal was ever wired up after the service was "
                "migrated to a new load balancer.",
                impact="A full outage of {service} for all callers until the cert "
                "was manually replaced.",
                remediation="Automated certificate renewal is now standard for "
                "every service behind this load balancer, not just newly "
                "provisioned ones.",
                action_items="Add expiry monitoring across the whole certificate "
                "inventory, not just the ones known to be manually managed.",
            ),
        ],
        alert_variants=[
            "every request to the SSO provider is failing TLS handshake",
            "sudden total outage right at midnight, looks cert-related",
        ],
    ),
    Scenario(
        key="disk_saturation",
        family=FailureModeFamily.CAPACITY_EXHAUSTION,
        service_role="primary_datastore",
        vocabularies=[
            Vocabulary(
                summary="{service}'s disk filled up from unbounded log retention, "
                "and writes started failing once there was no space left.",
                timeline="The first alert was a generic disk-space warning that "
                "was acknowledged but not acted on for several hours before "
                "writes actually started failing.",
                root_cause="A log-rotation policy that was supposed to cap "
                "retention at 14 days had silently stopped running after a "
                "configuration change months earlier, and nobody noticed until "
                "the disk was completely full.",
                impact="Write operations against {service} failed for close to "
                "forty minutes while space was cleared.",
                remediation="Restored the log-rotation job, added a hard alert "
                "threshold at 85% disk usage instead of only at 95%, and moved "
                "older logs to cheaper cold storage automatically.",
                action_items="Review every other host's log-retention "
                "configuration for the same silent-failure risk.",
            ),
            Vocabulary(
                summary="Disk usage on {service} crept up for weeks until it "
                "finally hit 100% and every write started erroring.",
                timeline="Capacity dashboards had shown a slow upward trend for "
                "weeks, but the trend line wasn't alerting on and nobody was "
                "watching it closely enough to catch it before it topped out.",
                root_cause="An old debug-logging flag had been left enabled in "
                "production, generating far more log volume than the retention "
                "policy was designed to handle.",
                impact="{service} rejected writes for roughly forty minutes.",
                remediation="Disabled the debug-logging flag, freed space "
                "immediately, and added a trend-based alert that fires well "
                "before disk usage reaches capacity rather than only at a fixed "
                "threshold.",
                action_items="Audit production configuration for any other "
                "debug flags left on from an earlier investigation.",
            ),
        ],
        alert_variants=[
            "writes failing against the primary database, disk might be full",
            "database errors, ops dashboard shows disk usage pinned at 100%",
        ],
    ),
    Scenario(
        key="config_rollout",
        family=FailureModeFamily.CONFIGURATION_ERROR,
        service_role="web_frontend",
        vocabularies=[
            Vocabulary(
                summary="A configuration rollout to {service} shipped a typo'd "
                "feature-flag value that disabled a required code path for every "
                "request.",
                timeline="Because the deploy itself looked healthy in the "
                "pipeline, the team spent the first ten minutes ruling out a code "
                "regression before checking the configuration change.",
                root_cause="The config change was pushed directly through the "
                "admin panel rather than through the reviewed pipeline, so the "
                "typo skipped both code review and the pipeline's own validation "
                "step.",
                impact="Every request to {service} hit the disabled code path and "
                "returned an error for the duration of the incident.",
                remediation="Config changes now go through the same reviewed "
                "pipeline as code, with a validation step that rejects unknown "
                "flag values instead of silently accepting them.",
                action_items="Close the admin-panel direct-edit path entirely, "
                "or at minimum require the same review as a code change.",
            ),
            Vocabulary(
                summary="An unreviewed config push to {service} flipped a flag to "
                "an invalid value and broke a required request path instantly.",
                timeline="The rollout itself wasn't flagged as risky by anyone "
                "since it was 'just a config change,' which is exactly why it "
                "skipped the scrutiny a code change would have gotten.",
                root_cause="No schema validation existed for this particular "
                "flag's allowed values, so a typo produced a value the code "
                "silently treated as 'disabled' instead of raising an error.",
                impact="A full outage of the affected request path in "
                "{service} until the config was rolled back.",
                remediation="Added schema validation for every feature-flag "
                "value and required config changes to go through the same "
                "review gate as code.",
                action_items="Retroactively add schema validation to every "
                "existing flag, not just newly created ones.",
            ),
        ],
        alert_variants=[
            "a chunk of requests failing right after the config push",
            "errors started the moment the new flag value went live",
        ],
    ),
    Scenario(
        key="dependency_version_drift",
        family=FailureModeFamily.DEPENDENCY_FAILURE,
        service_role="business_logic",
        vocabularies=[
            Vocabulary(
                summary="A minor version bump of a shared library used by "
                "{service} silently changed a default timeout, and nobody caught "
                "it in review.",
                timeline="The regression only showed up under real production "
                "load, since the staging environment's traffic volume never "
                "exercised the changed timeout.",
                root_cause="The library's changelog didn't call out the default "
                "value change as breaking, and the team's dependency-update "
                "process didn't include reading the diff of default values, only "
                "the changelog's own headline bullets.",
                impact="A subset of requests through {service} began timing out "
                "under peak load that had previously completed successfully.",
                remediation="Pinned the previous default explicitly rather than "
                "relying on the library's default, and added a load test to the "
                "dependency-upgrade checklist.",
                action_items="Review every other shared library dependency for "
                "implicitly-relied-upon default values.",
            ),
            Vocabulary(
                summary="{service} started behaving differently after a routine "
                "dependency upgrade quietly changed a default configuration "
                "value.",
                timeline="Symptoms were intermittent at first, which delayed "
                "connecting them to a dependency bump that had shipped two days "
                "earlier with no apparent issues at the time.",
                root_cause="A transitive dependency's own minor version bump "
                "changed a connection-pooling default several layers removed "
                "from the direct dependency the team had actually reviewed.",
                impact="Intermittent elevated latency in {service} for two days "
                "before the actual cause was identified.",
                remediation="Pinned the transitive dependency's version "
                "explicitly and added a diff review step covering transitive, "
                "not just direct, dependency changes.",
                action_items="Add automated alerting on any transitive "
                "dependency version change, not only direct ones.",
            ),
        ],
        alert_variants=[
            "latency creeping up on the order path since the last deploy",
            "intermittent slow requests, nothing obviously changed in our own code",
        ],
    ),
    Scenario(
        key="clock_skew",
        family=FailureModeFamily.INFRASTRUCTURE_HARDWARE,
        service_role="infra",
        vocabularies=[
            Vocabulary(
                summary="An NTP sync failure let {service}'s clock drift far "
                "enough that time-based auth tokens started being rejected as "
                "expired the moment they were issued.",
                timeline="The first theory was a bug in the token-issuing code "
                "itself, since the tokens looked correctly formed -- just always "
                "expired.",
                root_cause="The NTP daemon on the affected host had silently "
                "stopped syncing three days earlier, and the host's clock had "
                "drifted almost four minutes ahead of real time by the time "
                "tokens started failing validation.",
                impact="Every token issued from the affected host was rejected "
                "downstream as already expired.",
                remediation="Restarted NTP sync and added host-level clock-drift "
                "alerting instead of relying on NTP daemon health alone.",
                action_items="Audit every host's NTP daemon status rather than "
                "assuming it's running because it was configured to be.",
            ),
            Vocabulary(
                summary="A drifting system clock on one host running {service} "
                "caused every short-lived token it issued to look already "
                "expired to everyone else.",
                timeline="Because only one host out of the fleet was affected, "
                "the failure was intermittent and initially looked like a "
                "flaky-test-style false alarm rather than a real, ongoing issue.",
                root_cause="A virtualization-layer change had disabled the "
                "hypervisor's own time synchronization for one host in the "
                "fleet, and that host's local NTP client never caught the "
                "resulting drift.",
                impact="Roughly one-fourth of requests -- the fraction routed to "
                "the drifting host -- failed token validation.",
                remediation="Re-enabled hypervisor time sync and added a "
                "fleet-wide clock-drift check independent of NTP daemon status.",
                action_items="Add the clock-drift check to the standard host "
                "health check run before a host is added back to rotation.",
            ),
        ],
        alert_variants=[
            "auth tokens getting rejected as expired right after they're issued",
            "intermittent auth failures, seems to be one host in the fleet",
        ],
    ),
    Scenario(
        key="thread_pool_starvation",
        family=FailureModeFamily.CAPACITY_EXHAUSTION,
        service_role="business_logic",
        vocabularies=[
            Vocabulary(
                summary="A slow downstream call on {service} held worker threads "
                "long enough that the thread pool starved and every other "
                "request queued behind it.",
                timeline="Request latency climbed gradually rather than spiking, "
                "which delayed recognizing this as thread starvation rather than "
                "a simple traffic increase.",
                root_cause="One endpoint made a synchronous call to a slow "
                "downstream dependency with no timeout, so under load enough "
                "threads were parked waiting on that one call that the shared "
                "pool had nothing left for any other endpoint.",
                impact="Latency across every endpoint on {service} degraded, not "
                "just the one making the slow call, since they all shared the "
                "same thread pool.",
                remediation="Added an explicit timeout on the slow downstream "
                "call and moved it to its own isolated thread pool so it can't "
                "starve unrelated endpoints.",
                action_items="Audit every synchronous downstream call on "
                "{service} for a missing timeout.",
            ),
            Vocabulary(
                summary="{service}'s shared worker pool was starved by one "
                "endpoint's unbounded downstream call, degrading every other "
                "endpoint that shared the same pool.",
                timeline="On-call initially scaled up the instance count, which "
                "helped only briefly before the larger pool starved the same "
                "way under continued load.",
                root_cause="The pool-starving endpoint had no circuit breaker "
                "and no timeout, so each slow downstream call held its thread "
                "for the full length of the downstream's own hang.",
                impact="Every endpoint sharing the pool saw degraded latency, "
                "widening what looked at first like an isolated problem into a "
                "service-wide one.",
                remediation="Isolated the offending endpoint into its own "
                "bounded thread pool with a hard timeout, so it can now only "
                "ever starve itself.",
                action_items="Apply the same per-endpoint pool isolation to "
                "every other endpoint making a downstream call with no timeout.",
            ),
        ],
        alert_variants=[
            "latency degrading across the board, not just one endpoint",
            "requests queueing up, thread pool looks maxed",
        ],
    ),
    Scenario(
        key="dns_failover",
        family=FailureModeFamily.NETWORK_CONNECTIVITY,
        service_role="infra",
        vocabularies=[
            Vocabulary(
                summary="{service} failed to fail over to the secondary region "
                "because its DNS TTL was cached far longer than configured.",
                timeline="The primary region's own outage was resolved quickly, "
                "but traffic kept failing well past that point, which was the "
                "actual mystery on-call had to chase down.",
                root_cause="An intermediate resolver ignored the configured "
                "60-second TTL and cached the primary region's record for over "
                "twenty minutes, so clients kept trying the still-down primary "
                "long after failover should have redirected them.",
                impact="Clients behind the misbehaving resolver saw failures "
                "for twenty extra minutes after the primary region itself had "
                "already recovered.",
                remediation="Lowered the TTL further as a partial mitigation and "
                "added an application-level health check that doesn't depend on "
                "DNS propagation timing at all.",
                action_items="Stop relying on DNS TTL alone for failover "
                "timing; treat it as best-effort, not guaranteed.",
            ),
            Vocabulary(
                summary="Failover for {service} didn't take effect as fast as "
                "expected because a resolver somewhere in the path held onto a "
                "stale DNS record.",
                timeline="Some clients recovered immediately when the primary "
                "region came back up, while others stayed broken for another "
                "twenty minutes -- the split behavior was the first clue this "
                "was a DNS caching issue rather than a still-ongoing outage.",
                root_cause="A caching resolver operated outside the team's own "
                "infrastructure did not honor the record's TTL, extending the "
                "effective outage window well past the configured failover "
                "time for anyone routed through it.",
                impact="A subset of clients experienced an extended outage "
                "window of about twenty minutes beyond the primary region's own "
                "recovery.",
                remediation="Added an application-level health check as a "
                "second failover mechanism that doesn't depend on DNS caching "
                "behavior outside the team's control.",
                action_items="Document which resolvers in the request path are "
                "outside the team's control and can't be trusted to honor TTL.",
            ),
        ],
        alert_variants=[
            "some clients still failing even though the region's back up",
            "failover seems partial, some traffic still hitting the dead region",
        ],
    ),
    Scenario(
        key="quota_exhaustion",
        family=FailureModeFamily.CAPACITY_EXHAUSTION,
        service_role="external_adapter",
        vocabularies=[
            Vocabulary(
                summary="{service} hit its external provider's rate quota "
                "mid-day and every call past that point was rejected until the "
                "quota reset.",
                timeline="The team initially assumed the provider itself was "
                "having an outage, since the error responses didn't clearly "
                "indicate a quota rejection.",
                root_cause="Usage had grown steadily over the past month, but "
                "nobody was tracking usage against the fixed quota, so the "
                "threshold was crossed with no warning.",
                impact="Every call to {service} past the quota limit failed "
                "for the rest of the billing period until the quota reset at "
                "midnight.",
                remediation="Requested a quota increase from the provider and "
                "added usage-tracking alerting at 80% of the current limit.",
                action_items="Set up the same usage-tracking alert for every "
                "other external provider with a fixed quota.",
            ),
            Vocabulary(
                summary="Growing call volume to {service} finally crossed an "
                "external quota limit nobody had been watching, and every call "
                "past that point failed outright.",
                timeline="Retries against the quota-exceeded error just kept "
                "failing identically, which at least ruled out a transient "
                "network issue quickly.",
                root_cause="The provider's quota was set based on usage "
                "projections from over a year earlier and had never been "
                "revisited as the integration's traffic grew.",
                impact="All calls to {service} failed for the remainder of the billing window.",
                remediation="Negotiated a higher quota with the provider and "
                "added proactive usage alerting well before the new limit.",
                action_items="Establish a recurring quarterly review of usage "
                "against quota for every metered external dependency.",
            ),
        ],
        alert_variants=[
            "third-party calls all failing, might be rate limited",
            "every request to the external provider erroring since midday",
        ],
    ),
]

SCENARIOS_BY_KEY: dict[str, Scenario] = {s.key: s for s in SCENARIOS}

__all__ = ["Scenario", "Vocabulary", "SCENARIOS", "SCENARIOS_BY_KEY"]
