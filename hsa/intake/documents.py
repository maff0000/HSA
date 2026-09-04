"""Building the two structured outcomes of intake.

Intake produces exactly one of two documents, and never anything in between:

* ``not_sufficiently_defined`` — the frozen contract kind, built whenever
  any BLOCKING ambiguity survives the scan. It is validated against the
  frozen schema here, before it is returned, so a builder bug surfaces as a
  contract failure rather than as a document that quietly does not conform.

* ``strategy_intake_draft`` — the draft specification, built when nothing
  blocking survives.

WHY THE DRAFT IS NOT A ``strategy_package``. A governed strategy package
(``contracts/strategy_package.schema.json``) requires atomic decomposition,
a chain, HERMES mapping, deterministic test cases, evidence requirements and
CER references. Intake cannot supply those from a raw description without
inventing trading logic, which PID lines 39 and 148 forbid. So the draft
declares ``$hsa_intake`` rather than ``$hsa_kind``: it is deliberately NOT a
governed contract kind, and ``hsa validate`` will decline to route it. Its
``not_yet_specified`` list names, explicitly, every package field intake did
not supply, so nothing looks decided that was not.

What the draft IS held to: every parameter, HERMES field and provenance
block it carries is validated against the shared definitions in
``contracts/common.defs.json``. The parts intake does produce conform to the
frozen contract, so they drop into an atomic strategy or a package unchanged.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

from hsa.contracts import contracts_dir, validate_document
from hsa.intake.analyser import Analysis, TermFinding, UnknownFinding
from hsa.intake.errors import IntakeError

__all__ = [
    "DRAFT_DISCRIMINATOR",
    "DRAFT_MARKER",
    "OUTCOME_DRAFT",
    "OUTCOME_NOT_SUFFICIENTLY_DEFINED",
    "CONTRACT_VERSION",
    "NOT_YET_SPECIFIED",
    "utc_now",
    "build_not_sufficiently_defined",
    "build_draft",
]

#: The draft's own discriminator. Deliberately NOT ``$hsa_kind``: a draft is
#: not a governed contract kind, and must not be mistakable for one.
DRAFT_DISCRIMINATOR = "$hsa_intake"
DRAFT_MARKER = "strategy_intake_draft"

OUTCOME_DRAFT = "STRATEGY_INTAKE_DRAFT"
OUTCOME_NOT_SUFFICIENTLY_DEFINED = "STRATEGY_NOT_SUFFICIENTLY_DEFINED"

#: Contract set this intake writes against.
CONTRACT_VERSION = "1.0.0"

#: Package fields intake structurally cannot supply from a raw description.
#: Named explicitly in every draft so a missing section reads as an
#: outstanding obligation rather than as an oversight.
NOT_YET_SPECIFIED: tuple[tuple[str, str], ...] = (
    ("atomic_strategies", "Atomic decomposition of the measurable logic (PID line 133)."),
    ("chain", "Chain composition using ALL / ANY / SEQUENCE / CONTEXT_TRIGGER (PID line 134)."),
    ("timeframe_roles", "Assignment of CONTEXT / LOCATION / CONFIRMATION / TRIGGER to timeframes (PID lines 84-97)."),
    ("direction_semantics", "Emitted directions and the rule that derives them (PID line 135)."),
    ("timing", "Evaluation trigger and timeframe (PID line 136)."),
    ("persistence", "Whether the signal persists, and for how long (PID line 136)."),
    ("expiry", "Whether the setup expires, and the rule (PID line 136)."),
    ("state_semantics", "States, initial state and reset conditions (PID line 137)."),
    ("invalidation_conditions", "What invalidates an in-progress setup (PID line 139)."),
    ("validity_conditions", "Market conditions under which the strategy is expected to hold (PID line 139)."),
    ("output_contract", "Normalised output shape including the reason field (PID line 141)."),
    ("deterministic_test_cases", "Fixed HERMES facts and the exact expected output (PID line 142)."),
    ("evidence_requirements", "Backtest and evidence requirements, stated before evidence exists (PID line 143)."),
    ("acceptance_criteria", "Machine-evaluable acceptance criteria (PID line 144)."),
    ("rejection_criteria", "Machine-evaluable rejection criteria (PID line 144)."),
    ("cer_references", "CER canonical identities and evidence references (PID line 146)."),
)

_defs_validators: dict[str, Draft202012Validator] = {}


def utc_now() -> str:
    """Current instant as a contract-shaped UTC timestamp.

    UTC is canonical for everything HSA persists (PID line 225); local time
    is display-only and never written.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _defs_validator(name: str) -> Draft202012Validator:
    """Validator for one shared definition in ``contracts/common.defs.json``.

    The frozen ``common.defs.json`` is the single definition of these
    shapes. Re-stating them here would let intake drift away from the
    contract silently, so they are read from the contract instead.
    """
    if name not in _defs_validators:
        path = contracts_dir() / "common.defs.json"
        try:
            with path.open(encoding="utf-8") as handle:
                common = json.load(handle)
        except OSError as exc:
            raise IntakeError("could not read %s: %s" % (path, exc)) from exc
        defs = common.get("$defs", {})
        if name not in defs:
            raise IntakeError("common.defs.json declares no $defs/%s" % name)
        _defs_validators[name] = Draft202012Validator(
            {"$ref": "#/$defs/" + name, "$defs": defs}
        )
    return _defs_validators[name]


def _check_against_common_defs(value: Any, name: str, where: str) -> Any:
    errors = sorted(
        _defs_validator(name).iter_errors(value), key=lambda error: list(error.path)
    )
    if errors:
        first = errors[0]
        location = "".join("[%r]" % part for part in first.path)
        raise IntakeError(
            "%s does not satisfy common.defs.json#/$defs/%s%s: %s"
            % (where, name, location, first.message)
        )
    return value


def _provenance(request: Mapping[str, Any], ingested_at_utc: str) -> dict:
    provenance = {
        "source_type": request["source_type"],
        "source_reference": request["source_reference"],
        "ingested_at_utc": ingested_at_utc,
    }
    excerpt = request.get("excerpt")
    if excerpt:
        provenance["excerpt"] = excerpt
    notes = request.get("notes")
    if notes:
        provenance["notes"] = notes
    return _check_against_common_defs(provenance, "provenance", "intake provenance")


def _resolution_provenance(finding: TermFinding, analysis: Analysis) -> dict:
    """Attribution for a parameterised term. Never silent, never a guess.

    Records that a human-ratified ruling resolved the term, which ruling,
    and that the DEFAULT it carries is provisional pending CER evidence.
    See ``docs/AMBIGUITY-POLICY.md``, section "Attribution".
    """
    lexicon = analysis.lexicon
    return {
        "disposition": "PARAMETERISED",
        "authority": "HUMAN_ARCHITECT_RULING",
        "ratified_by": lexicon.ratified_by,
        "ruling_document": lexicon.ruling_document,
        "lexicon_term": finding.term.term_id,
        "lexicon_version": lexicon.version,
        "pid_reference": finding.term.pid_reference,
        "hsa_guessed": False,
        "default_status": "PROVISIONAL_PENDING_EVIDENCE",
        "evidence_required": True,
        "evidence_note": (
            "The measurement basis is ratified; the default value is not. It "
            "must be settled by CER evidence before this strategy version is "
            "promoted (PID lines 143, 189, 198)."
        ),
    }


def _unresolved_from_term(finding: TermFinding) -> dict:
    term = finding.term
    item: dict[str, Any] = {
        "item_id": term.term_id,
        "source_language": finding.occurrences[0].text,
        "location": finding.location,
        "why_unresolved": term.why_unresolved,
        "blocks": list(term.blocks),
        "severity": term.severity,
        "resolution_needed": dict(term.resolution_needed or {}),
    }
    if term.candidate_definitions:
        item["candidate_definitions"] = [
            dict(candidate) for candidate in term.candidate_definitions
        ]
    return item


def _unresolved_from_unknown(finding: UnknownFinding, analysis: Analysis) -> dict:
    policy = analysis.lexicon.unknown_term_policy
    phrase = finding.phrase
    resolution = policy["resolution_needed"]
    item: dict[str, Any] = {
        "item_id": finding.item_id,
        "source_language": phrase,
        "location": finding.location,
        "why_unresolved": policy["why_unresolved_template"].format(
            phrase=phrase, marker_reason=finding.marker.reason
        ),
        "blocks": list(policy["blocks"]),
        "severity": policy["severity"],
        "resolution_needed": {
            "kind": resolution["kind"],
            "description": resolution["description_template"].format(phrase=phrase),
            "responsible": resolution["responsible"],
        },
    }
    return item


def unresolved_items(analysis: Analysis) -> list[dict]:
    """Every unresolved item, ruled refusals first then unknown terms.

    Order is fixed so two runs over the same source produce byte-identical
    documents apart from the timestamp.
    """
    items = [_unresolved_from_term(finding) for finding in analysis.refused]
    items.extend(
        _unresolved_from_unknown(finding, analysis)
        for finding in analysis.unknown_findings
    )
    return items


def _resolved_summary(analysis: Analysis) -> list[str]:
    """What intake DID extract before it stopped, so nothing is lost."""
    summary = []
    for finding in analysis.parameterised:
        summary.append(
            "Resolved %r onto a measured definition: %s Declared parameter(s): %s."
            % (
                finding.occurrences[0].text,
                finding.term.measurement_basis,
                ", ".join(param["name"] for param in finding.term.parameters),
            )
        )
    summary.append(
        "Scanned against declared lexicon %s (%s), %d ruled terms and %d "
        "discretionary markers. This scan is pattern-based and cannot prove "
        "the description is unambiguous; see docs/AMBIGUITY-POLICY.md."
        % (
            analysis.lexicon.version,
            analysis.lexicon.source_path.name,
            len(analysis.lexicon.terms),
            len(analysis.lexicon.markers),
        )
    )
    return summary


def _parameters(analysis: Analysis) -> list[dict]:
    parameters: list[dict] = []
    seen: set[str] = set()
    for finding in analysis.parameterised:
        for param in finding.term.parameters:
            if param["name"] in seen:
                continue
            seen.add(param["name"])
            declared = dict(param)
            _check_against_common_defs(
                declared,
                "parameter",
                "parameter %r declared by lexicon term %r"
                % (param["name"], finding.term.term_id),
            )
            parameters.append(declared)
    return parameters


def _hermes_fields(analysis: Analysis) -> list[dict]:
    fields: list[dict] = []
    seen: set[tuple] = set()
    for finding in analysis.parameterised:
        for field in finding.term.required_hermes_fields:
            key = (field["field"], field.get("timeframe"))
            if key in seen:
                continue
            seen.add(key)
            declared = dict(field)
            _check_against_common_defs(
                declared,
                "hermes_field",
                "HERMES field %r declared by lexicon term %r"
                % (field["field"], finding.term.term_id),
            )
            fields.append(declared)
    return fields


def build_not_sufficiently_defined(
    analysis: Analysis,
    request: Mapping[str, Any],
    generated_at_utc: str,
) -> dict:
    """Build and validate the structured refusal (PID line 120).

    Validated against the frozen contract before being returned: a refusal
    that did not conform would be worse than no refusal, because a caller
    would branch on it.
    """
    items = unresolved_items(analysis)
    if not items:
        raise IntakeError(
            "refusal requested with nothing unresolved; that is a contradiction"
        )
    document = {
        "$hsa_kind": "not_sufficiently_defined",
        "$hsa_contract_version": CONTRACT_VERSION,
        "result": OUTCOME_NOT_SUFFICIENTLY_DEFINED,
        "intake_id": request["intake_id"],
        "generated_at_utc": generated_at_utc,
        "provenance": _provenance(request, generated_at_utc),
        "resolved_summary": _resolved_summary(analysis),
        "unresolved_items": items,
    }
    validate_document(document, kind="not_sufficiently_defined", source="hsa intake")
    return document


def build_draft(
    analysis: Analysis,
    request: Mapping[str, Any],
    generated_at_utc: str,
) -> dict:
    """Build the draft strategy specification.

    Only reached when nothing BLOCKING survived the scan. Any ADVISORY items
    travel with the draft rather than being dropped.
    """
    advisory = [
        item for item in unresolved_items(analysis) if item["severity"] == "ADVISORY"
    ]
    resolved_terms = []
    for finding in analysis.parameterised:
        term = finding.term
        resolved_terms.append(
            {
                "term_id": term.term_id,
                "label": term.label,
                "source_language": finding.occurrences[0].text,
                "location": finding.location,
                "occurrences": len(finding.occurrences),
                "measurement_basis": term.measurement_basis,
                "basis_rationale": term.basis_rationale,
                "declared_parameters": [param["name"] for param in term.parameters],
                "resolution": _resolution_provenance(finding, analysis),
            }
        )

    document = {
        DRAFT_DISCRIMINATOR: DRAFT_MARKER,
        "$hsa_contract_version": CONTRACT_VERSION,
        "result": OUTCOME_DRAFT,
        "intake_id": request["intake_id"],
        "generated_at_utc": generated_at_utc,
        "provenance": _provenance(request, generated_at_utc),
        "title": request.get("title") or request["source_reference"],
        "raw_description": analysis.text,
        "lexicon": {
            "version": analysis.lexicon.version,
            "source": analysis.lexicon.source_path.name,
            "ruling_document": analysis.lexicon.ruling_document,
            "terms_declared": len(analysis.lexicon.terms),
            "markers_declared": len(analysis.lexicon.markers),
        },
        "resolved_terms": resolved_terms,
        "parameters": _parameters(analysis),
        "required_hermes_fields": _hermes_fields(analysis),
        "advisory_items": advisory,
        "not_yet_specified": [
            {"field": field, "obligation": obligation}
            for field, obligation in NOT_YET_SPECIFIED
        ],
        "analyser_limits": [
            "This draft is not a governed strategy_package. It declares "
            "$hsa_intake, not $hsa_kind, and hsa validate will not route it.",
            "A clean scan means nothing HSA recognises as discretionary "
            "survived unruled. It does NOT mean the description is fully "
            "specified: the analyser matches declared patterns and does not "
            "understand English (docs/AMBIGUITY-POLICY.md).",
            "Every parameter default above is PROVISIONAL and must be settled "
            "by CER evidence before promotion.",
        ],
    }
    return document


def write_document(document: Mapping[str, Any], path: str | Path) -> Path:
    """Write a document as UTF-8 JSON with a trailing newline."""
    target = Path(path)
    try:
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except OSError as exc:
        raise IntakeError("could not write %s: %s" % (target, exc)) from exc
    return target
