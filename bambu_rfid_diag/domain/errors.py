"""Domain-level exceptions independent of GUI and localization."""


class BambuRfidError(RuntimeError):
    """Base class for application-domain failures."""


class ConfigurationError(BambuRfidError):
    """A required runtime dependency or setting is missing."""


class WorkflowInvariantError(BambuRfidError):
    """An internal workflow prerequisite was not established."""
