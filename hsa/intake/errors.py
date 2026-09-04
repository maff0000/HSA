"""Typed errors raised by strategy intake.

Every class here descends from ``hsa.errors.HSAError``, so ``hsa/cli.py``
maps them onto its existing exit codes without any change: an intake
failure is an ordinary HSA error (exit 3).

Note what is deliberately NOT here: there is no exception for the
``STRATEGY_NOT_SUFFICIENTLY_DEFINED`` outcome. A refusal is a successful,
governed result of intake (PID lines 39 and 120), not a failure, so it is
returned as a document rather than raised. Modelling it as an exception
would quietly reclassify HSA's most important behaviour as an error.
"""

from __future__ import annotations

from hsa.errors import HSAError

__all__ = ["IntakeError", "LexiconError", "IntakeRequestError"]


class IntakeError(HSAError):
    """Base class for deliberate intake failures."""


class LexiconError(IntakeError):
    """The declared lexicon is missing, unreadable, or malformed.

    Raised loudly rather than tolerated. A partially-loaded lexicon would
    silently stop recognising terms, which turns fail-closed into fail-open
    — the one failure mode intake exists to prevent.
    """


class IntakeRequestError(IntakeError):
    """The raw strategy description could not be read as an intake request."""
