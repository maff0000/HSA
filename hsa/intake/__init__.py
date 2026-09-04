"""Strategy intake — PID lines 99-120, acceptance criteria 2 and 3.

Intake converts a raw strategy description into exactly ONE of two
structured outcomes, and never anything in between:

``STRATEGY_INTAKE_DRAFT``
    A draft strategy specification in which every discretionary term the
    analyser recognised has been resolved onto a ratified measurement basis
    and declared as a bounded parameter, each carrying default, allowed
    range, units and visible provenance attributing the ruling.

``STRATEGY_NOT_SUFFICIENTLY_DEFINED``
    The frozen refusal contract, naming exactly what is unresolved and, per
    item, what evidence or decision is needed and who owes it.

A refusal is a SUCCESSFUL outcome of HSA, not an error. PID line 39 forbids
HSA from guessing ambiguous trading rules; the refusal is how it complies.
Nothing in this package raises an exception to signal one.

The boundary between the two — parameterise a term whose measurement basis
is known but whose threshold is unset, refuse a term whose measurement basis
is itself undefined — is stated in ``docs/AMBIGUITY-POLICY.md`` and applied
from the declared lexicon in ``hsa/intake/lexicon.json``. An undeclared
discretionary term refuses: unknown fails closed, not open.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from hsa.intake.analyser import Analysis, analyse, normalise
from hsa.intake.documents import (
    CONTRACT_VERSION,
    DRAFT_DISCRIMINATOR,
    DRAFT_MARKER,
    OUTCOME_DRAFT,
    OUTCOME_NOT_SUFFICIENTLY_DEFINED,
    build_draft,
    build_not_sufficiently_defined,
    unresolved_items,
    utc_now,
    write_document,
)
from hsa.intake.errors import IntakeError, IntakeRequestError, LexiconError
from hsa.intake.lexicon import Lexicon, load_lexicon
from hsa.intake.request import SOURCE_TYPES, build_request, read_request

__all__ = [
    "Analysis",
    "IntakeError",
    "IntakeRequestError",
    "IntakeResult",
    "Lexicon",
    "LexiconError",
    "CONTRACT_VERSION",
    "DRAFT_DISCRIMINATOR",
    "DRAFT_MARKER",
    "OUTCOME_DRAFT",
    "OUTCOME_NOT_SUFFICIENTLY_DEFINED",
    "SOURCE_TYPES",
    "analyse",
    "build_request",
    "intake",
    "load_lexicon",
    "normalise",
    "read_request",
    "utc_now",
    "write_document",
]


@dataclass(frozen=True)
class IntakeResult:
    """The outcome of one intake run.

    ``sufficiently_defined`` is the single branch a caller needs. It is
    False for a refusal, which is a correct result, not a failure.
    """

    outcome: str
    document: dict
    analysis: Analysis
    request: Mapping[str, Any]

    @property
    def sufficiently_defined(self) -> bool:
        return self.outcome == OUTCOME_DRAFT

    @property
    def blocking_items(self) -> list[dict]:
        return [
            item
            for item in self.document.get("unresolved_items", [])
            if item.get("severity") == "BLOCKING"
        ]

    @property
    def advisory_items(self) -> list[dict]:
        if self.sufficiently_defined:
            return list(self.document.get("advisory_items", []))
        return [
            item
            for item in self.document.get("unresolved_items", [])
            if item.get("severity") == "ADVISORY"
        ]


def intake(
    request: Mapping[str, Any],
    lexicon: Lexicon | None = None,
    generated_at_utc: str | None = None,
) -> IntakeResult:
    """Run the intake pipeline over an already-built request.

    The outcome is decided by one rule: if any unresolved item is BLOCKING,
    the result is a refusal. Otherwise it is a draft. ADVISORY items travel
    with the draft rather than stopping it.

    The rule is read off the items themselves rather than re-derived from the
    findings. It used to be re-derived, and that is how a whole class of
    unresolved item could be built by ``documents`` and still never stop an
    intake: two places decided "blocking" and only one of them knew about
    every kind of finding.
    """
    resolved_lexicon = lexicon if lexicon is not None else load_lexicon()
    analysis = analyse(request["text"], resolved_lexicon)
    stamp = generated_at_utc or utc_now()

    blocking = any(
        item["severity"] == "BLOCKING" for item in unresolved_items(analysis)
    )

    if blocking:
        document = build_not_sufficiently_defined(analysis, request, stamp)
        return IntakeResult(
            outcome=OUTCOME_NOT_SUFFICIENTLY_DEFINED,
            document=document,
            analysis=analysis,
            request=request,
        )

    document = build_draft(analysis, request, stamp)
    return IntakeResult(
        outcome=OUTCOME_DRAFT,
        document=document,
        analysis=analysis,
        request=request,
    )
