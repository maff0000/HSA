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

__all__ = [
    "IntakeError",
    "LexiconError",
    "IntakeRequestError",
    "UnreportedMatchError",
]


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


class UnreportedMatchError(IntakeError):
    """A recognised term match reached the end of the scan unaccounted for.

    This is the analyser's own invariant breaking, not a malformed input, and
    it is raised rather than tolerated for the reason the whole R4-R8 sequence
    exists: FIVE independent audits found the same root cause, a recognised
    term deleted without being reported, wearing a different phrasing each
    time. Every one of them was silent. Exit 0, an empty refusal, a draft that
    declared in its own ``analyser_limits`` that nothing recognised had
    survived unruled.

    So the analyser no longer trusts itself to have reported everything. Every
    recognised match is written into a ledger with the single reason it is
    accounted for, and ``_verify_every_recognised_match_is_reported`` checks
    that ledger against the findings actually emitted. A sixth deletion path
    added by a future edit does not go quiet: it lands here, loudly, with the
    term and the span it dropped.
    """
