"""Read-only tag inspectors shared by the diagnostic service."""

from .mifare import MifareDiagnosticInspector
from .type2 import Type2DiagnosticInspector

__all__ = ["MifareDiagnosticInspector", "Type2DiagnosticInspector"]
