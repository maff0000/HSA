"""Cross-field semantic validation for HSA documents.

JSON Schema settles *shape*. It cannot compare one part of a document with
another, and several of the PID's hardest requirements are exactly that kind
of comparison: that a package and its embedded chain say the same thing, that
a ``CONTEXT`` input really sits above its ``TRIGGER``, that every atomic a
chain names actually exists. Those live here.

This module is a library, not a command. ``hsa/commands/chain.py`` is its
first consumer and later work items are expected to import it rather than
re-derive these rules.

    Finding                         one semantic problem: check id, path, message
    Catalogue                       the atomic strategy catalogue, loaded from disk
    CHECKS                          every check id this module can emit
    check_chain(doc, catalogue)     semantic checks for a chain document
    check_package(doc, catalogue)   semantic checks for a strategy package
    check_document(doc, ...)        dispatch on the document's own kind
    raise_if_invalid(findings, ...) turn findings into W1's DocumentInvalidError

ORDER OF OPERATIONS. These checks assume the document has already passed
``hsa.contracts.validate_document``. They are deliberately forgiving about
malformed regions — a section of the wrong type is skipped rather than
reported — because reporting a shape problem here would duplicate, and
probably contradict, what the schema already said about it. Structural first,
semantic second, always.

FINDING SHAPE. ``Finding.as_failure()`` returns the same three keys W1's
``DocumentInvalidError.failures`` carries — ``path``, ``message``,
``schema_path`` — so semantic findings render through exactly the same error
path as structural ones and a caller never has to branch on which kind of
problem it is looking at. The ``schema_path`` of a semantic finding is
``semantic/<check id>``, which cannot collide with a real JSON Schema path.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from hsa.contracts import detect_kind
from hsa.errors import DocumentInvalidError, SchemaLoadError

__all__ = [
    "CATALOGUE_DEPENDENT_CHECKS",
    "CATALOGUE_DIR_ENV",
    "CHECKS",
    "CONTEXT_TRIGGER_ROLES",
    "SEMANTIC_KINDS",
    "Catalogue",
    "Finding",
    "catalogue_dir",
    "check_chain",
    "check_document",
    "check_package",
    "raise_if_invalid",
    "timeframe_minutes",
]

#: Optional environment override for the catalogue directory. Configuration is
#: supplied externally; the repository-relative default below only exists so
#: the CLI works from a plain checkout.
CATALOGUE_DIR_ENV = "HSA_CATALOGUE_DIR"

#: Every check id this module can emit. Stable identifiers: a caller may filter
#: or suppress by id, so renaming one is a breaking change.
CHECKS: tuple[str, ...] = (
    "chain.input_id_unique",
    "chain.sequence_index_contiguous",
    "chain.sequence_index_misplaced",
    "chain.optional_input",
    "chain.reference_resolves",
    "chain.context_trigger_timeframes",
    "chain.context_trigger_roles",
    "chain.timeframe_role_mapping",
    "chain.reason_fields_attribute_inputs",
    "package.chain_agreement",
    "package.chain_inputs_embedded",
    "package.hermes_coverage",
    "package.reason_fields_bound",
)

#: The document kinds that have semantic rules beyond their schema. Every
#: other kind yields no findings, which is a real answer and not a silent
#: skip; a caller reporting to a human should say so in those words.
SEMANTIC_KINDS: tuple[str, ...] = ("chain", "strategy_package")

#: The checks that cannot run without a catalogue. Named here so a caller
#: that runs without one can report exactly which check DID NOT RUN, rather
#: than letting an unrun check read as a check that passed.
CATALOGUE_DEPENDENT_CHECKS: tuple[str, ...] = ("chain.reference_resolves",)

#: The two roles ``CONTEXT_TRIGGER`` is defined as, and the only two it may
#: carry. docs/COMPOSITION-DOCTRINE.md section 3 defines the primitive as a
#: higher-timeframe CONTEXT holding while a lower-timeframe TRIGGER fires and
#: says nothing at all about how a third role would combine.
CONTEXT_TRIGGER_ROLES: tuple[str, ...] = ("CONTEXT", "TRIGGER")

#: Sections a strategy package states authoritatively and its embedded chain
#: restates operationally. PID lines 135-137 govern these at package level; the
#: chain must not contradict them. Flagged by W1 as unenforceable in schema.
AGREEMENT_SECTIONS: tuple[str, ...] = (
    "direction_semantics",
    "timing",
    "persistence",
    "expiry",
    "state_semantics",
    "timeframe_roles",
)

_TIMEFRAME_RE = re.compile(r"^([1-9][0-9]*)(M|H|D|W)$")
_UNIT_MINUTES = {"M": 1, "H": 60, "D": 1440, "W": 10080}


# --- findings ----------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One semantic problem, located by JSON path.

    ``check`` is the stable identifier from ``CHECKS``; ``path`` is a JSON
    path rooted at ``$`` in the same notation ``hsa.contracts`` uses for
    structural failures.
    """

    check: str
    path: str
    message: str

    def as_failure(self) -> dict:
        """Render as a ``DocumentInvalidError.failures`` entry."""
        return {
            "path": self.path,
            "message": self.message,
            "schema_path": "semantic/" + self.check,
        }

    def __str__(self) -> str:
        return "%s: %s [%s]" % (self.path, self.message, self.check)


def raise_if_invalid(
    findings: Sequence[Finding],
    kind: str,
    source: str | None = None,
) -> None:
    """Raise ``DocumentInvalidError`` if ``findings`` is non-empty.

    Uses W1's typed error so semantic failure reaches the process exit code
    by the same route as structural failure; ``hsa.cli`` owns that mapping.
    """
    if findings:
        raise DocumentInvalidError(
            kind, [finding.as_failure() for finding in findings], source=source
        )


# --- timeframes --------------------------------------------------------------


def timeframe_minutes(timeframe: Any) -> int | None:
    """Length of a contract timeframe in minutes, or None if unparseable.

    ``M`` is minutes, per ``common.defs.json``: there is no month suffix, so
    ``15M`` is a quarter of an hour and never fifteen months.
    """
    if not isinstance(timeframe, str):
        return None
    match = _TIMEFRAME_RE.match(timeframe)
    if match is None:
        return None
    return int(match.group(1)) * _UNIT_MINUTES[match.group(2)]


# --- the catalogue -----------------------------------------------------------


def catalogue_dir() -> Path:
    """Resolve the atomic strategy catalogue directory, failing loudly.

    ``HSA_CATALOGUE_DIR`` wins if set. Otherwise ``catalogue/atomic`` is found
    by walking up from this file, which is what makes the CLI work from a
    plain checkout with no configuration at all.
    """
    override = os.environ.get(CATALOGUE_DIR_ENV)
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_dir():
            raise SchemaLoadError(
                "%s is set to %s but that is not a directory"
                % (CATALOGUE_DIR_ENV, candidate)
            )
        return candidate

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "catalogue" / "atomic"
        if candidate.is_dir():
            return candidate

    raise SchemaLoadError(
        "could not locate catalogue/atomic above %s; set %s"
        % (here, CATALOGUE_DIR_ENV)
    )


class Catalogue:
    """The atomic strategy catalogue, keyed by identity *and* version.

    Identity in HSA is always id plus version (PID line 72), and promoted
    versions are immutable (PID lines 185-189), so two versions of one
    strategy are two separate entries here and never overwrite each other.
    """

    def __init__(
        self,
        entries: Mapping[tuple[str, str], dict],
        source: Path | None = None,
    ) -> None:
        self._entries = dict(entries)
        self.source = source

    @classmethod
    def from_directory(cls, directory: str | os.PathLike | None = None) -> "Catalogue":
        """Load every ``*.json`` in ``directory`` as a catalogue entry.

        Defaults to ``catalogue_dir()``. A file that is not a JSON object, or
        that carries no ``strategy_id``/``strategy_version``, is a broken
        catalogue and raises rather than being skipped quietly.
        """
        base = Path(directory) if directory is not None else catalogue_dir()
        if not base.is_dir():
            raise SchemaLoadError("catalogue directory not found: %s" % base)

        entries: dict[tuple[str, str], dict] = {}
        for path in sorted(base.glob("*.json")):
            try:
                with path.open(encoding="utf-8") as handle:
                    document = json.load(handle)
            except json.JSONDecodeError as exc:
                raise SchemaLoadError(
                    "catalogue entry %s is not valid JSON: %s" % (path, exc)
                ) from exc
            except OSError as exc:
                raise SchemaLoadError(
                    "could not read catalogue entry %s: %s" % (path, exc)
                ) from exc
            if not isinstance(document, dict):
                raise SchemaLoadError(
                    "catalogue entry %s must be a JSON object" % path
                )
            strategy_id = document.get("strategy_id")
            version = document.get("strategy_version")
            if not isinstance(strategy_id, str) or not isinstance(version, str):
                raise SchemaLoadError(
                    "catalogue entry %s declares no strategy_id/strategy_version"
                    % path
                )
            key = (strategy_id, version)
            if key in entries:
                raise SchemaLoadError(
                    "catalogue declares %s %s more than once (at %s)"
                    % (strategy_id, version, path)
                )
            entries[key] = document
        return cls(entries, source=base)

    @classmethod
    def empty(cls) -> "Catalogue":
        """An empty catalogue, for callers that want resolution to fail."""
        return cls({}, source=None)

    def get(self, strategy_id: str, strategy_version: str) -> dict | None:
        """One entry by identity and version, or None."""
        return self._entries.get((strategy_id, strategy_version))

    def versions(self, strategy_id: str) -> tuple[str, ...]:
        """Every version of ``strategy_id`` held, in sorted order."""
        return tuple(
            sorted(
                version
                for (held_id, version) in self._entries
                if held_id == strategy_id
            )
        )

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(sorted({held_id for (held_id, _) in self._entries}))

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[dict]:
        for key in sorted(self._entries):
            yield self._entries[key]

    def __repr__(self) -> str:
        return "Catalogue(%d entries, source=%s)" % (len(self._entries), self.source)


# --- helpers -----------------------------------------------------------------


def _objects(value: Any) -> list[dict]:
    """The dict members of ``value`` if it is a list, else an empty list.

    Non-dict members are dropped: the schema already rejected them, and this
    module does not duplicate structural complaints.
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _render(value: Any) -> str:
    """Compact, stable rendering of a value for an error message."""
    return json.dumps(value, sort_keys=True, default=str)


def _join(prefix: str, *parts: Any) -> str:
    path = prefix
    for part in parts:
        if isinstance(part, int):
            path += "[%d]" % part
        else:
            path += "." + str(part)
    return path


# --- chain checks ------------------------------------------------------------


def _check_input_ids_unique(chain: Mapping, prefix: str) -> list[Finding]:
    """``input_id`` is the handle the explanation contract attributes by.

    Two inputs sharing one handle makes a per-input reason ambiguous, which
    defeats PID line 80. JSON Schema's ``uniqueItems`` compares whole objects,
    so it cannot see this.
    """
    findings: list[Finding] = []
    seen: dict[str, int] = {}
    for index, item in enumerate(_objects(chain.get("inputs"))):
        input_id = item.get("input_id")
        if not isinstance(input_id, str):
            continue
        if input_id in seen:
            findings.append(
                Finding(
                    "chain.input_id_unique",
                    _join(prefix, "inputs", index, "input_id"),
                    "input_id %r is already used by inputs[%d]; input_id must be "
                    "unique within a chain so a per-input reason can attribute "
                    "a match or non-match unambiguously (PID line 80)"
                    % (input_id, seen[input_id]),
                )
            )
        else:
            seen[input_id] = index
    return findings


def _check_sequence_indices(chain: Mapping, prefix: str) -> list[Finding]:
    """SEQUENCE indices must be contiguous from 1 with no duplicates.

    The schema requires ``sequence_index`` to be present on a SEQUENCE chain
    and to be at least 1. It cannot see gaps, duplicates, or an index left
    behind on a chain whose primitive is no longer SEQUENCE.
    """
    findings: list[Finding] = []
    primitive = chain.get("primitive")
    inputs = _objects(chain.get("inputs"))

    if primitive != "SEQUENCE":
        for index, item in enumerate(inputs):
            if "sequence_index" in item:
                findings.append(
                    Finding(
                        "chain.sequence_index_misplaced",
                        _join(prefix, "inputs", index, "sequence_index"),
                        "sequence_index is only meaningful when the chain "
                        "primitive is SEQUENCE, but this chain is %s; remove it "
                        "rather than leave an ordering that nothing enforces"
                        % _render(primitive),
                    )
                )
        return findings

    indices: list[int] = []
    for index, item in enumerate(inputs):
        value = item.get("sequence_index")
        if isinstance(value, int) and not isinstance(value, bool):
            indices.append(value)

    if len(indices) != len(inputs):
        # A missing index is a structural failure the schema already reports.
        return findings

    expected = list(range(1, len(indices) + 1))
    if sorted(indices) != expected:
        findings.append(
            Finding(
                "chain.sequence_index_contiguous",
                _join(prefix, "inputs"),
                "SEQUENCE sequence_index values must be contiguous from 1 with "
                "no duplicates; expected %s but found %s. A gap or a repeat "
                "leaves the order of the steps undetermined (PID line 75)"
                % (_render(expected), _render(sorted(indices))),
            )
        )
    return findings


def _check_optional_inputs(chain: Mapping, prefix: str) -> list[Finding]:
    """An optional input can never be the sole cause of a match.

    ``optional`` exists for PID line 242's optional lower-timeframe trigger.
    It marks a step whose absence does not prevent a match — which is only
    coherent while something else is *required* to cause one.
    """
    findings: list[Finding] = []
    primitive = chain.get("primitive")
    inputs = _objects(chain.get("inputs"))
    optional = [
        index for index, item in enumerate(inputs) if item.get("optional") is True
    ]
    if not optional:
        return findings

    if len(inputs) == 1:
        return [
            Finding(
                "chain.optional_input",
                _join(prefix, "inputs", 0, "optional"),
                "the only input of this chain is optional, so nothing is "
                "required to cause a match; an optional input can never be the "
                "sole cause of a match",
            )
        ]

    if len(optional) == len(inputs):
        findings.append(
            Finding(
                "chain.optional_input",
                _join(prefix, "inputs"),
                "every input of this chain is optional, so no input is required "
                "to cause a match; at least one input must be required",
            )
        )
        return findings

    if primitive == "ANY":
        for index in optional:
            findings.append(
                Finding(
                    "chain.optional_input",
                    _join(prefix, "inputs", index, "optional"),
                    "under ANY a single matching input causes the chain to "
                    "match, so an optional input here can be the sole cause of "
                    "a match; make it required or move it to a chain whose "
                    "primitive requires a second input",
                )
            )

    if primitive == "CONTEXT_TRIGGER":
        for index in optional:
            role = inputs[index].get("timeframe_role")
            if role in ("CONTEXT", "TRIGGER"):
                findings.append(
                    Finding(
                        "chain.optional_input",
                        _join(prefix, "inputs", index, "optional"),
                        "the %s input of a CONTEXT_TRIGGER chain cannot be "
                        "optional: the primitive is defined as a CONTEXT that "
                        "holds while a TRIGGER fires, so neither role can be "
                        "skipped" % role,
                    )
                )
    return findings


def _check_timeframe_roles(chain: Mapping, prefix: str) -> list[Finding]:
    """An input's timeframe must match the role mapping the chain declares.

    ``timeframe_roles`` is the chain's semantic role model (PID lines 84-97).
    An input claiming role CONTEXT on 15M while the chain maps CONTEXT to 4H
    means the document states two different things about the same role.
    """
    findings: list[Finding] = []
    roles = chain.get("timeframe_roles")
    if not isinstance(roles, Mapping):
        return findings
    for index, item in enumerate(_objects(chain.get("inputs"))):
        role = item.get("timeframe_role")
        timeframe = item.get("timeframe")
        if not isinstance(role, str):
            continue
        if role not in roles:
            findings.append(
                Finding(
                    "chain.timeframe_role_mapping",
                    _join(prefix, "inputs", index, "timeframe_role"),
                    "input declares role %s but timeframe_roles maps no "
                    "timeframe for it; every role an input uses must appear in "
                    "the chain's role model (PID lines 84-97)" % role,
                )
            )
            continue
        mapped = roles[role]
        if isinstance(timeframe, str) and mapped != timeframe:
            findings.append(
                Finding(
                    "chain.timeframe_role_mapping",
                    _join(prefix, "inputs", index, "timeframe"),
                    "input runs role %s on %s but timeframe_roles maps %s to "
                    "%s; the two statements of the same role must agree"
                    % (role, timeframe, role, mapped),
                )
            )
    return findings


def _check_context_trigger_timeframes(chain: Mapping, prefix: str) -> list[Finding]:
    """CONTEXT must genuinely sit above TRIGGER.

    The schema requires a CONTEXT_TRIGGER chain to contain both roles. It
    cannot compare their timeframes, so a chain declaring a 5M context over a
    4H trigger validates while inverting the entire semantic model of PID
    lines 84-97.
    """
    findings: list[Finding] = []
    if chain.get("primitive") != "CONTEXT_TRIGGER":
        return findings

    inputs = _objects(chain.get("inputs"))
    contexts = [
        (index, item)
        for index, item in enumerate(inputs)
        if item.get("timeframe_role") == "CONTEXT"
    ]
    triggers = [
        (index, item)
        for index, item in enumerate(inputs)
        if item.get("timeframe_role") == "TRIGGER"
    ]

    for context_index, context in contexts:
        context_minutes = timeframe_minutes(context.get("timeframe"))
        if context_minutes is None:
            continue
        for trigger_index, trigger in triggers:
            trigger_minutes = timeframe_minutes(trigger.get("timeframe"))
            if trigger_minutes is None:
                continue
            if context_minutes > trigger_minutes:
                continue
            relation = "the same timeframe as" if context_minutes == trigger_minutes else "a lower timeframe than"
            findings.append(
                Finding(
                    "chain.context_trigger_timeframes",
                    _join(prefix, "inputs", context_index, "timeframe"),
                    "CONTEXT input %r runs on %s, which is %s TRIGGER input %r "
                    "on %s; CONTEXT_TRIGGER means a higher-timeframe context "
                    "holding while a lower-timeframe trigger fires, so the "
                    "context must be strictly the higher of the two"
                    % (
                        context.get("input_id"),
                        context.get("timeframe"),
                        relation,
                        trigger.get("input_id"),
                        trigger.get("timeframe"),
                    ),
                )
            )
    return findings


def _check_context_trigger_roles(chain: Mapping, prefix: str) -> list[Finding]:
    """CONTEXT_TRIGGER carries exactly one CONTEXT and one TRIGGER, and nothing else.

    The schema's conditional only requires that the inputs *contain* a CONTEXT
    and *contain* a TRIGGER. ``contains`` is satisfied by one or by five, and
    it says nothing whatever about the other roles present, so a chain can
    validate while carrying a second TRIGGER, or a LOCATION input, under a
    primitive that has no defined meaning for either.

    That is not a stylistic objection. docs/COMPOSITION-DOCTRINE.md section 3
    defines CONTEXT_TRIGGER as one thing — a higher-timeframe context holding
    while a lower-timeframe trigger fires — and defines no combination rule for
    a third participant. A document carrying one is asking FORGE to invent the
    semantics, which is exactly what PID line 148 forbids.

    SCOPE. This reports only what the schema cannot see: a *surplus* role, and
    a *duplicate* of one of the two defined roles. It deliberately does not
    report a role that is entirely absent, because the schema's ``contains``
    already rejects that and this module does not duplicate structural
    complaints. "Exactly one" is therefore enforced jointly: at least one by
    ``chain.schema.json``, at most one here.
    """
    findings: list[Finding] = []
    if chain.get("primitive") != "CONTEXT_TRIGGER":
        return findings

    inputs = _objects(chain.get("inputs"))
    by_role: dict[str, list[int]] = {}
    for index, item in enumerate(inputs):
        role = item.get("timeframe_role")
        if isinstance(role, str):
            by_role.setdefault(role, []).append(index)

    for role in CONTEXT_TRIGGER_ROLES:
        held = by_role.get(role, [])
        for ordinal, index in enumerate(held[1:], start=2):
            findings.append(
                Finding(
                    "chain.context_trigger_roles",
                    _join(prefix, "inputs", index, "timeframe_role"),
                    "input %r is the %d%s %s input of a CONTEXT_TRIGGER chain; "
                    "the primitive is defined as exactly one CONTEXT holding "
                    "while exactly one TRIGGER fires, and no rule says how a "
                    "second %s would combine with the first (inputs[%d] is "
                    "already the %s)"
                    % (
                        inputs[index].get("input_id"),
                        ordinal,
                        "nd" if ordinal == 2 else ("rd" if ordinal == 3 else "th"),
                        role,
                        role,
                        held[0],
                        role,
                    ),
                )
            )

    for role in sorted(set(by_role) - set(CONTEXT_TRIGGER_ROLES)):
        for index in by_role[role]:
            findings.append(
                Finding(
                    "chain.context_trigger_roles",
                    _join(prefix, "inputs", index, "timeframe_role"),
                    "input %r declares role %s, but a CONTEXT_TRIGGER chain "
                    "may carry only CONTEXT and TRIGGER inputs; the primitive "
                    "is defined as those two roles and nothing states how a %s "
                    "input combines with them. Use ALL or SEQUENCE, whose "
                    "combination rules are defined, or drop the input"
                    % (inputs[index].get("input_id"), role, role),
                )
            )
    return findings


def _check_reason_fields_attribute_inputs(chain: Mapping, prefix: str) -> list[Finding]:
    """``per_input_evaluation_reported`` must be backed by named inputs.

    PID line 80 requires an explicit reason for match and non-match, and
    ``docs/COMPOSITION-DOCTRINE.md`` section "The reason requirement is the
    strictest of them" says what that means: attribution must be **per
    input**, using each atomic's own ``reason_field``. "The chain did not
    match" is not a reason.

    The schema can hold the three flags at ``const: true`` and can require
    ``reason_fields`` to be non-empty, and that is all it can do — it cannot
    compare ``reason_fields`` with the ``input_id`` list beside it. So a
    chain could declare ``per_input_evaluation_reported: true`` and a
    ``reason_fields`` of ``["reason"]``, naming none of its inputs, and pass
    every structural check. The per-input requirement then rested entirely on
    prose. This is the comparison the schema cannot make.

    An entry attributes an input when it is written ``<input_id>.<field>``.
    That is the convention already in force in the governed packages, and it
    is the only one that binds a reason to a handle mechanically.
    """
    findings: list[Finding] = []
    contract = chain.get("explanation_contract")
    if not isinstance(contract, Mapping):
        return findings
    if contract.get("per_input_evaluation_reported") is not True:
        return findings
    fields = contract.get("reason_fields")
    if not isinstance(fields, list):
        return findings
    named = {
        str(entry).split(".", 1)[0]
        for entry in fields
        if isinstance(entry, str) and "." in entry
    }
    for index, item in enumerate(_objects(chain.get("inputs"))):
        input_id = item.get("input_id")
        if not isinstance(input_id, str) or input_id in named:
            continue
        findings.append(
            Finding(
                "chain.reason_fields_attribute_inputs",
                _join(prefix, "explanation_contract", "reason_fields"),
                "explanation_contract declares per_input_evaluation_reported "
                "true but reason_fields names no field for input %r; PID line "
                "80 and docs/COMPOSITION-DOCTRINE.md require the reason to be "
                "attributed per input, written as %r, so a non-match can be "
                "traced to the input that caused it"
                % (input_id, input_id + ".<reason_field>"),
            )
        )
    return findings


def _check_references_resolve(
    chain: Mapping, catalogue: "Catalogue | None", prefix: str
) -> list[Finding]:
    """Every referenced atomic must exist in the catalogue at that version.

    Skipped entirely when no catalogue is supplied: a chain can be checked for
    internal coherence without one, and silently inventing an empty catalogue
    would turn every reference into a failure.
    """
    if catalogue is None:
        return []

    findings: list[Finding] = []
    for index, item in enumerate(_objects(chain.get("inputs"))):
        strategy_id = item.get("strategy_id")
        version = item.get("strategy_version")
        if not isinstance(strategy_id, str) or not isinstance(version, str):
            continue
        if catalogue.get(strategy_id, version) is not None:
            continue
        held = catalogue.versions(strategy_id)
        if held:
            message = (
                "catalogue holds %s at %s but not at %s; a chain pins the exact "
                "immutable version it was proven against (PID lines 72, 185-189)"
                % (strategy_id, ", ".join(held), version)
            )
            path = _join(prefix, "inputs", index, "strategy_version")
        else:
            message = (
                "no catalogue entry for strategy_id %r; a chain may only "
                "compose atomic strategies that exist in the catalogue"
                % strategy_id
            )
            path = _join(prefix, "inputs", index, "strategy_id")
        findings.append(Finding("chain.reference_resolves", path, message))
    return findings


def check_chain(
    chain: Any,
    catalogue: "Catalogue | None" = None,
    prefix: str = "$",
) -> list[Finding]:
    """Every semantic check that applies to a chain document.

    ``catalogue`` enables reference resolution; omit it to check only the
    chain's internal coherence. ``prefix`` roots the reported paths, so an
    embedded chain reports at ``$.chain.inputs[0]`` rather than ``$.inputs[0]``.
    """
    if not isinstance(chain, Mapping):
        return []
    findings: list[Finding] = []
    findings.extend(_check_input_ids_unique(chain, prefix))
    findings.extend(_check_sequence_indices(chain, prefix))
    findings.extend(_check_optional_inputs(chain, prefix))
    findings.extend(_check_timeframe_roles(chain, prefix))
    findings.extend(_check_context_trigger_timeframes(chain, prefix))
    findings.extend(_check_context_trigger_roles(chain, prefix))
    findings.extend(_check_reason_fields_attribute_inputs(chain, prefix))
    findings.extend(_check_references_resolve(chain, catalogue, prefix))
    return findings


# --- package checks ----------------------------------------------------------


def _check_package_chain_agreement(package: Mapping, prefix: str) -> list[Finding]:
    """The package and its embedded chain must say the same thing.

    W1 recorded this as a real unenforced gap. A strategy package states
    direction, timing, persistence, expiry, state and the role model at
    package level (PID lines 135-137) and the embedded chain restates them
    operationally. The package level is authoritative; disagreement means
    FORGE has been handed two specifications and no way to choose.
    """
    findings: list[Finding] = []
    chain = package.get("chain")
    if not isinstance(chain, Mapping):
        return findings

    for section in AGREEMENT_SECTIONS:
        package_section = package.get(section)
        chain_section = chain.get(section)
        if not isinstance(package_section, Mapping) or not isinstance(
            chain_section, Mapping
        ):
            continue
        for key in sorted(set(package_section) | set(chain_section)):
            in_package = key in package_section
            in_chain = key in chain_section
            if in_package and not in_chain:
                findings.append(
                    Finding(
                        "package.chain_agreement",
                        _join(prefix, "chain", section, key),
                        "package declares %s.%s as %s but the embedded chain "
                        "omits it; the package level is authoritative and the "
                        "chain must restate it, not drop it"
                        % (section, key, _render(package_section[key])),
                    )
                )
            elif in_chain and not in_package:
                findings.append(
                    Finding(
                        "package.chain_agreement",
                        _join(prefix, "chain", section, key),
                        "embedded chain declares %s.%s as %s but the package "
                        "does not declare it at all; the package level is the "
                        "governed statement and must carry it"
                        % (section, key, _render(chain_section[key])),
                    )
                )
            elif package_section[key] != chain_section[key]:
                findings.append(
                    Finding(
                        "package.chain_agreement",
                        _join(prefix, "chain", section, key),
                        "embedded chain declares %s.%s as %s but the package "
                        "declares %s; the two must agree and the package level "
                        "is authoritative (PID lines 135-137)"
                        % (
                            section,
                            key,
                            _render(chain_section[key]),
                            _render(package_section[key]),
                        ),
                    )
                )
    return findings


def _check_chain_inputs_embedded(package: Mapping, prefix: str) -> list[Finding]:
    """A package is self-contained: every chain input must be embedded in it.

    The package embeds full atomic definitions rather than referencing them,
    so FORGE implements from one document. A chain input naming a strategy the
    package does not carry breaks that guarantee.
    """
    findings: list[Finding] = []
    chain = package.get("chain")
    if not isinstance(chain, Mapping):
        return findings

    embedded = {
        (atomic.get("strategy_id"), atomic.get("strategy_version"))
        for atomic in _objects(package.get("atomic_strategies"))
    }
    for index, item in enumerate(_objects(chain.get("inputs"))):
        key = (item.get("strategy_id"), item.get("strategy_version"))
        if key in embedded:
            continue
        findings.append(
            Finding(
                "package.chain_inputs_embedded",
                _join(prefix, "chain", "inputs", index),
                "chain input %r references %s %s, which is not embedded in the "
                "package's atomic_strategies; a package must be implementable "
                "from the one document (PID line 148)"
                % (item.get("input_id"), key[0], key[1]),
            )
        )
    return findings


def _check_hermes_coverage(package: Mapping, prefix: str) -> list[Finding]:
    """Every atomic's HERMES requirement must be carried up to package level.

    PID line 132 states required HERMES fields once at package level so FORGE
    can provision inputs without walking the atomics. That is only true if the
    package-level list is a superset of what the atomics ask for. A package
    entry that declares no timeframe covers the field on any timeframe.
    """
    findings: list[Finding] = []
    package_fields = _objects(package.get("required_hermes_fields"))
    exact: set[tuple[str, str | None]] = set()
    any_timeframe: set[str] = set()
    for entry in package_fields:
        name = entry.get("field")
        if not isinstance(name, str):
            continue
        timeframe = entry.get("timeframe")
        if timeframe is None:
            any_timeframe.add(name)
        exact.add((name, timeframe if isinstance(timeframe, str) else None))

    for atomic_index, atomic in enumerate(_objects(package.get("atomic_strategies"))):
        for field_index, entry in enumerate(
            _objects(atomic.get("required_hermes_fields"))
        ):
            name = entry.get("field")
            if not isinstance(name, str):
                continue
            timeframe = entry.get("timeframe")
            timeframe = timeframe if isinstance(timeframe, str) else None
            if name in any_timeframe or (name, timeframe) in exact:
                continue
            where = "%s on %s" % (name, timeframe) if timeframe else name
            findings.append(
                Finding(
                    "package.hermes_coverage",
                    _join(
                        prefix,
                        "atomic_strategies",
                        atomic_index,
                        "required_hermes_fields",
                        field_index,
                    ),
                    "atomic strategy %r requires HERMES field %s, which the "
                    "package's required_hermes_fields does not declare; the "
                    "package-level list must be the union of what its atomics "
                    "consume (PID line 132)" % (atomic.get("strategy_id"), where),
                )
            )
    return findings


def _check_reason_fields_bound(package: Mapping, prefix: str) -> list[Finding]:
    """Every ``reason_fields`` entry must name something that exists.

    ``reason_fields`` is a list of free strings as far as the schema is
    concerned, so an entry can name a field nothing emits and still validate.
    Both governed packages did exactly that in different directions: one
    declared ``chain_reason``, which appears in no ``output_contract.fields``;
    the other declared ``["reason"]``, which names none of its three inputs
    while asserting ``per_input_evaluation_reported: true``. Per-input reason
    attribution — a PID line 80 requirement — was resting on prose.

    An entry binds one of two ways, and must bind one of them:

    * ``<input_id>.<field>`` where ``input_id`` is a chain input and
      ``<field>`` is a field that input's embedded atomic actually emits; or
    * a bare name declared in the package's ``output_contract.fields``.

    The package's own ``output_contract.reason_field`` must also appear, so
    the chain-level reason PID line 80 requires is one of the fields the
    contract promises to emit.
    """
    findings: list[Finding] = []
    chain = package.get("chain")
    if not isinstance(chain, Mapping):
        return findings
    contract = chain.get("explanation_contract")
    if not isinstance(contract, Mapping):
        return findings
    declared = contract.get("reason_fields")
    if not isinstance(declared, list):
        return findings

    output = package.get("output_contract")
    output = output if isinstance(output, Mapping) else {}
    output_fields = {
        entry["name"]
        for entry in _objects(output.get("fields"))
        if isinstance(entry.get("name"), str)
    }

    atomic_fields: dict[tuple[Any, Any], set[str]] = {}
    for atomic in _objects(package.get("atomic_strategies")):
        atomic_output = atomic.get("output_contract")
        atomic_output = atomic_output if isinstance(atomic_output, Mapping) else {}
        atomic_fields[(atomic.get("strategy_id"), atomic.get("strategy_version"))] = {
            entry["name"]
            for entry in _objects(atomic_output.get("fields"))
            if isinstance(entry.get("name"), str)
        }

    inputs = {
        item["input_id"]: item
        for item in _objects(chain.get("inputs"))
        if isinstance(item.get("input_id"), str)
    }

    path = _join(prefix, "chain", "explanation_contract", "reason_fields")
    for index, entry in enumerate(declared):
        if not isinstance(entry, str):
            continue
        if "." not in entry:
            if entry in output_fields:
                continue
            findings.append(
                Finding(
                    "package.reason_fields_bound",
                    "%s[%d]" % (path, index),
                    "reason field %r is declared by the explanation contract "
                    "but is not a field of the package's output_contract "
                    "(%s), and is not written as <input_id>.<field>; a reason "
                    "field nothing emits cannot explain a match or a "
                    "non-match (PID line 80)"
                    % (entry, ", ".join(sorted(output_fields)) or "none"),
                )
            )
            continue
        handle, field = entry.split(".", 1)
        if handle not in inputs:
            findings.append(
                Finding(
                    "package.reason_fields_bound",
                    "%s[%d]" % (path, index),
                    "reason field %r attributes to input %r, which the chain "
                    "does not declare (declared: %s)"
                    % (entry, handle, ", ".join(sorted(inputs)) or "none"),
                )
            )
            continue
        item = inputs[handle]
        key = (item.get("strategy_id"), item.get("strategy_version"))
        emitted = atomic_fields.get(key)
        if emitted is None:
            # The atomic is not embedded. package.chain_inputs_embedded
            # already says so; do not report the same defect twice.
            continue
        if field in emitted:
            continue
        findings.append(
            Finding(
                "package.reason_fields_bound",
                "%s[%d]" % (path, index),
                "reason field %r attributes to input %r, but %s %s emits no "
                "field %r (it emits: %s)"
                % (entry, handle, key[0], key[1], field, ", ".join(sorted(emitted))),
            )
        )

    reason_field = output.get("reason_field")
    if isinstance(reason_field, str) and reason_field not in declared:
        findings.append(
            Finding(
                "package.reason_fields_bound",
                path,
                "the output_contract names %r as its reason_field, but the "
                "explanation contract's reason_fields does not include it; "
                "the chain-level reason PID line 80 requires must be one of "
                "the fields the contract promises to emit" % reason_field,
            )
        )
    return findings


def check_package(
    package: Any,
    catalogue: "Catalogue | None" = None,
    prefix: str = "$",
) -> list[Finding]:
    """Every semantic check that applies to a strategy package.

    Includes the full chain check run against the embedded chain, with paths
    rooted at ``$.chain``.
    """
    if not isinstance(package, Mapping):
        return []
    findings: list[Finding] = []
    findings.extend(_check_package_chain_agreement(package, prefix))
    findings.extend(_check_chain_inputs_embedded(package, prefix))
    findings.extend(_check_hermes_coverage(package, prefix))
    findings.extend(_check_reason_fields_bound(package, prefix))
    chain = package.get("chain")
    if isinstance(chain, Mapping):
        findings.extend(
            check_chain(chain, catalogue=catalogue, prefix=_join(prefix, "chain"))
        )
    return findings


# --- dispatch ----------------------------------------------------------------


def check_document(
    document: Any,
    kind: str | None = None,
    catalogue: "Catalogue | None" = None,
) -> list[Finding]:
    """Run the semantic checks for ``document``'s kind.

    ``kind`` is auto-detected from the ``$hsa_kind`` discriminator when
    omitted. Kinds with no semantic rules beyond their schema return an empty
    list; that is a real answer, not a silent skip.
    """
    resolved = kind if kind is not None else detect_kind(document)
    if resolved == "chain":
        return check_chain(document, catalogue=catalogue)
    if resolved == "strategy_package":
        return check_package(document, catalogue=catalogue)
    return []
