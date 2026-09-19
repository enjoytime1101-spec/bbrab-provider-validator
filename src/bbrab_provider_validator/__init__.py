"""Offline-first acceptance checks for OpenAI-compatible providers."""

from .validator import validate_fixture, validate_live

__all__ = ["validate_fixture", "validate_live"]
__version__ = "0.1.0"
