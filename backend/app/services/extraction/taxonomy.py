import enum


class FailureModeFamily(enum.StrEnum):
    """Fixed 12-family failure-mode taxonomy, plus OTHER.

    Not free-form: a fixed taxonomy is what makes failure modes joinable across
    postmortems (plan.md/Master-Prompt.md call for "the fixed 12-family taxonomy" but
    don't name the families -- this list is this phase's own design decision, see the
    ADR for the rationale behind each category).
    """

    CONFIGURATION_ERROR = "configuration_error"
    DEPLOYMENT_FAILURE = "deployment_failure"
    CAPACITY_EXHAUSTION = "capacity_exhaustion"
    DEPENDENCY_FAILURE = "dependency_failure"
    NETWORK_CONNECTIVITY = "network_connectivity"
    DATA_CORRUPTION = "data_corruption"
    CODE_DEFECT = "code_defect"
    HUMAN_PROCESS_ERROR = "human_process_error"
    SECURITY_INCIDENT = "security_incident"
    INFRASTRUCTURE_HARDWARE = "infrastructure_hardware"
    SCALING_LOAD = "scaling_load"
    MONITORING_GAP = "monitoring_gap"
    OTHER = "other"
