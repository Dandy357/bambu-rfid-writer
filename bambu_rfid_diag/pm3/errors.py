"""Exceptions raised by the Proxmark3 integration layer."""


class ProxmarkError(RuntimeError):
    """Base class for Proxmark transport and command failures."""


class BundleValidationError(ProxmarkError):
    """The selected RRG/Iceman bundle is missing required files."""


class UnsafeCommandError(ProxmarkError):
    """A command or argument violated the bounded command policy."""


class UnsupportedPlatformError(ProxmarkError):
    """The requested operation is unavailable on this platform."""


class OperationCancelledError(ProxmarkError):
    """The user cancelled an active Proxmark operation."""
