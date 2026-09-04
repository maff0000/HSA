"""Loading and structural checking of the declared intake lexicon.

The lexicon lives in ``hsa/intake/lexicon.json`` as DATA, not as code, so a
human can review every ruling without reading Python (see
``docs/AMBIGUITY-POLICY.md``). This module is the only thing that reads it.

It is checked on load rather than trusted. A malformed entry raises
``LexiconError`` instead of being skipped: an entry that silently failed to
load would stop its term being recognised, and an unrecognised discretionary
term is exactly what the fail-closed design exists to prevent.

The same reasoning covers ``realised_by`` and ``hermes_basis_relationship``,
the declared links from a ruled parameter to the catalogue entry that
implements it. Their *content* — that the two sides actually agree on
default, allowed range and measurement basis — is checked by
``tests/test_lexicon_catalogue_agreement.py``, which is the only place that
may read the catalogue; intake must not depend on the catalogue at runtime.
Their *shape* is checked here, so a link that is malformed enough to be
skipped by that test cannot reach it looking like an absent link.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from hsa.intake.errors import LexiconError

__all__ = [
    "LEXICON_PATH_ENV",
    "PARAMETERISE",
    "REFUSE",
    "Term",
    "Marker",
    "Lexicon",
    "default_lexicon_path",
    "load_lexicon",
]

#: Optional environment override, so a reviewer can run intake against a
#: candidate lexicon without editing the shipped one. Mirrors the existing
#: ``HSA_CONTRACTS_DIR`` convention in ``hsa.contracts``.
LEXICON_PATH_ENV = "HSA_INTAKE_LEXICON"

PARAMETERISE = "PARAMETERISE"
REFUSE = "REFUSE"
_DISPOSITIONS = (PARAMETERISE, REFUSE)

_BLOCKS = (
    "ATOMIC_DECOMPOSITION",
    "CHAIN_COMPOSITION",
    "PARAMETER_DEFINITION",
    "DIRECTION_SEMANTICS",
    "TIMING_SEMANTICS",
    "HERMES_MAPPING",
    "TEST_DEFINITION",
)
_SEVERITIES = ("BLOCKING", "ADVISORY")
_RESOLUTION_KINDS = (
    "MEASURABLE_DEFINITION",
    "PARAMETER_VALUE",
    "EVIDENCE",
    "HUMAN_DECISION",
    "DATA_SOURCE",
)
_RESPONSIBLE = ("MATT", "SOURCE_AUTHOR", "CER", "HERMES", "NEO")

_TERM_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_STRATEGY_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_PARAMETER_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


@dataclass(frozen=True)
class Term:
    """One ruled discretionary phrase."""

    term_id: str
    label: str
    disposition: str
    pattern: "re.Pattern[str]"
    raw_pattern: str
    pid_reference: str
    measurement_basis: str | None
    basis_rationale: str | None
    parameters: tuple[Mapping[str, Any], ...]
    required_hermes_fields: tuple[Mapping[str, Any], ...]
    why_unresolved: str | None
    blocks: tuple[str, ...]
    severity: str | None
    resolution_needed: Mapping[str, Any] | None
    candidate_definitions: tuple[Mapping[str, Any], ...]
    #: Declared links from this term's parameters to the catalogue parameters
    #: that realise them. Empty for a REFUSE term, which has no realisation.
    realised_by: tuple[Mapping[str, Any], ...]
    #: How the basis fields this term declares are derived from the fields the
    #: linked catalogue entry actually consumes. ``None`` for a REFUSE term.
    hermes_basis_relationship: Mapping[str, Any] | None


@dataclass(frozen=True)
class Marker:
    """A declared word or construction that signals discretionary language."""

    marker_id: str
    reason: str
    pattern: "re.Pattern[str]"
    raw_pattern: str


@dataclass(frozen=True)
class Lexicon:
    version: str
    ruling_document: str
    ratified_by: str
    source_path: Path
    terms: tuple[Term, ...]
    markers: tuple[Marker, ...]
    unknown_term_policy: Mapping[str, Any]

    def term(self, term_id: str) -> Term:
        for candidate in self.terms:
            if candidate.term_id == term_id:
                return candidate
        raise LexiconError("no lexicon term %r in %s" % (term_id, self.source_path))


def default_lexicon_path() -> Path:
    """Resolve the lexicon file, honouring ``HSA_INTAKE_LEXICON``."""
    override = os.environ.get(LEXICON_PATH_ENV)
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_file():
            raise LexiconError(
                "%s is set to %s but that is not a file"
                % (LEXICON_PATH_ENV, candidate)
            )
        return candidate
    return Path(__file__).resolve().parent / "lexicon.json"


def _require(mapping: Any, key: str, where: str) -> Any:
    if not isinstance(mapping, Mapping) or key not in mapping:
        raise LexiconError("%s is missing required key %r" % (where, key))
    return mapping[key]


def _require_text(mapping: Any, key: str, where: str) -> str:
    value = _require(mapping, key, where)
    if not isinstance(value, str) or not value.strip():
        raise LexiconError("%s: %r must be a non-empty string" % (where, key))
    return value


def _compile(raw: str, where: str) -> "re.Pattern[str]":
    try:
        return re.compile(raw)
    except re.error as exc:
        raise LexiconError("%s has an invalid pattern: %s" % (where, exc)) from exc


def _check_enum(value: Any, allowed: Sequence[str], where: str, key: str) -> str:
    if value not in allowed:
        raise LexiconError(
            "%s: %s must be one of %s, got %r"
            % (where, key, ", ".join(allowed), value)
        )
    return str(value)


def _check_parameter(param: Any, where: str) -> Mapping[str, Any]:
    """Structural check only; the authoritative check is the frozen contract.

    ``hsa.intake.documents`` validates every emitted parameter against
    ``common.defs.json#/$defs/parameter``, so this exists to fail at load
    time with a message naming the lexicon entry rather than failing later
    with a message naming a document.
    """
    for key in ("name", "description", "type", "units"):
        _require_text(param, key, where)
    if "default" not in param:
        raise LexiconError("%s is missing required key 'default'" % where)
    has_range = "allowed_range" in param
    has_values = "allowed_values" in param
    if has_range == has_values:
        raise LexiconError(
            "%s must declare exactly one of allowed_range or allowed_values "
            "(PID line 140: every parameter needs a mechanically checkable "
            "domain)" % where
        )
    return param


def _check_hermes_field(field: Any, where: str) -> Mapping[str, Any]:
    _require_text(field, "field", where)
    _require_text(field, "purpose", where)
    return field


def _check_realisation(
    link: Any, where: str, parameter_names: Sequence[str]
) -> Mapping[str, Any]:
    """Structural check of one declared lexicon-parameter -> catalogue link."""
    lexicon_parameter = _require_text(link, "lexicon_parameter", where)
    if lexicon_parameter not in parameter_names:
        raise LexiconError(
            "%s: lexicon_parameter %r is not declared by this term (declared: "
            "%s). A link to a parameter that does not exist would silently "
            "leave the real parameter unrealised"
            % (where, lexicon_parameter, ", ".join(parameter_names) or "none")
        )
    strategy_id = _require_text(link, "catalogue_strategy_id", where)
    if not _STRATEGY_ID.match(strategy_id):
        raise LexiconError(
            "%s: catalogue_strategy_id %r does not match the contract identity "
            "pattern ^[a-z][a-z0-9_]{2,63}$" % (where, strategy_id)
        )
    version = _require_text(link, "catalogue_strategy_version", where)
    if not _SEMVER.match(version):
        raise LexiconError(
            "%s: catalogue_strategy_version %r is not strict semver. Identity "
            "is strategy_id AND strategy_version together (PID line 72), so a "
            "link that does not pin a version does not pin a realisation"
            % (where, version)
        )
    catalogue_parameter = _require_text(link, "catalogue_parameter", where)
    if not _PARAMETER_NAME.match(catalogue_parameter):
        raise LexiconError(
            "%s: catalogue_parameter %r does not match the contract parameter "
            "name pattern ^[a-z][a-z0-9_]{0,63}$" % (where, catalogue_parameter)
        )
    phrases = _require(link, "basis_phrases", where)
    if not isinstance(phrases, list) or not phrases:
        raise LexiconError(
            "%s: basis_phrases must be a non-empty list. It is what makes "
            "'same measurement basis' checkable rather than asserted" % where
        )
    for i, phrase in enumerate(phrases):
        if not isinstance(phrase, str) or not phrase.strip():
            raise LexiconError(
                "%s: basis_phrases[%d] must be a non-empty string" % (where, i)
            )
    _require_text(link, "why_the_names_differ", where)
    _require_text(link, "range_reconciliation", where)
    return link


def _check_basis_relationship(
    relationship: Any, where: str, basis_fields: Sequence[str]
) -> Mapping[str, Any]:
    """Structural check of the declared basis-versus-derivation relationship.

    Intake declares the quantities the ruling is stated in; the catalogue
    declares the raw facts they are computed from. The lists differ on
    purpose. Requiring every declared basis field to carry a derivation is
    what stops that difference from being an unexplained divergence.
    """
    _require_text(relationship, "statement", where)
    raw = _require(relationship, "derivations", where)
    if not isinstance(raw, list) or not raw:
        raise LexiconError("%s: derivations must be a non-empty list" % where)
    covered: list[str] = []
    for i, derivation in enumerate(raw):
        sub = "%s derivations[%d]" % (where, i)
        basis_field = _require_text(derivation, "basis_field", sub)
        if basis_field not in basis_fields:
            raise LexiconError(
                "%s: basis_field %r is not one of this term's "
                "required_hermes_fields (%s)"
                % (sub, basis_field, ", ".join(basis_fields) or "none")
            )
        if basis_field in covered:
            raise LexiconError("%s: basis_field %r derived twice" % (sub, basis_field))
        covered.append(basis_field)
        sources = _require(derivation, "derived_from", sub)
        if not isinstance(sources, list) or not sources:
            raise LexiconError("%s: derived_from must be a non-empty list" % sub)
        for j, source in enumerate(sources):
            if not isinstance(source, str) or not source.strip():
                raise LexiconError(
                    "%s: derived_from[%d] must be a non-empty string" % (sub, j)
                )
        _require_text(derivation, "expression", sub)
    missing = [field for field in basis_fields if field not in covered]
    if missing:
        raise LexiconError(
            "%s: no derivation declared for required_hermes_fields %s. An "
            "undeclared basis field is exactly the divergence this exists to "
            "prevent" % (where, ", ".join(missing))
        )
    catalogue_only = relationship.get("catalogue_only_fields", [])
    if not isinstance(catalogue_only, list):
        raise LexiconError("%s: catalogue_only_fields must be a list" % where)
    for i, field in enumerate(catalogue_only):
        sub = "%s catalogue_only_fields[%d]" % (where, i)
        _require_text(field, "field", sub)
        _require_text(field, "why", sub)
    return relationship


def _check_resolution(resolution: Any, where: str) -> Mapping[str, Any]:
    _check_enum(_require(resolution, "kind", where), _RESOLUTION_KINDS, where, "kind")
    _check_enum(
        _require(resolution, "responsible", where), _RESPONSIBLE, where, "responsible"
    )
    return resolution


def _load_term(raw: Any, index: int, path: Path) -> Term:
    where = "%s: terms[%d]" % (path, index)
    term_id = _require_text(raw, "term_id", where)
    if not _TERM_ID.match(term_id):
        raise LexiconError(
            "%s: term_id %r does not match the contract identity pattern "
            "^[a-z][a-z0-9_]{2,63}$ — it is emitted as an unresolved item_id"
            % (where, term_id)
        )
    where = "%s (%s)" % (where, term_id)
    disposition = _check_enum(
        _require(raw, "disposition", where), _DISPOSITIONS, where, "disposition"
    )
    pattern_text = _require_text(raw, "pattern", where)

    parameters: tuple[Mapping[str, Any], ...] = ()
    hermes: tuple[Mapping[str, Any], ...] = ()
    measurement_basis: str | None = None
    basis_rationale: str | None = None
    why_unresolved: str | None = None
    blocks: tuple[str, ...] = ()
    severity: str | None = None
    resolution: Mapping[str, Any] | None = None
    candidates: tuple[Mapping[str, Any], ...] = ()
    realised_by: tuple[Mapping[str, Any], ...] = ()
    basis_relationship: Mapping[str, Any] | None = None

    if disposition == PARAMETERISE:
        measurement_basis = _require_text(raw, "measurement_basis", where)
        basis_rationale = _require_text(raw, "basis_rationale", where)
        raw_params = _require(raw, "parameters", where)
        if not isinstance(raw_params, list) or not raw_params:
            raise LexiconError(
                "%s: a PARAMETERISE term must declare at least one parameter, "
                "otherwise nothing is actually resolved" % where
            )
        parameters = tuple(
            _check_parameter(param, "%s parameters[%d]" % (where, i))
            for i, param in enumerate(raw_params)
        )
        raw_fields = raw.get("required_hermes_fields", [])
        if not isinstance(raw_fields, list):
            raise LexiconError("%s: required_hermes_fields must be a list" % where)
        hermes = tuple(
            _check_hermes_field(field, "%s required_hermes_fields[%d]" % (where, i))
            for i, field in enumerate(raw_fields)
        )
        parameter_names = [str(param["name"]) for param in parameters]
        raw_links = raw.get("realised_by", [])
        if not isinstance(raw_links, list):
            raise LexiconError("%s: realised_by must be a list" % where)
        linked: list[str] = []
        for i, link in enumerate(raw_links):
            checked = _check_realisation(
                link, "%s realised_by[%d]" % (where, i), parameter_names
            )
            name = str(checked["lexicon_parameter"])
            if name in linked:
                raise LexiconError(
                    "%s realised_by[%d]: lexicon_parameter %r is linked more "
                    "than once; one parameter has one realisation"
                    % (where, i, name)
                )
            linked.append(name)
        realised_by = tuple(raw_links)
        raw_relationship = raw.get("hermes_basis_relationship")
        if raw_relationship is not None:
            basis_relationship = _check_basis_relationship(
                raw_relationship,
                "%s hermes_basis_relationship" % where,
                [str(field["field"]) for field in hermes],
            )
    else:
        if raw.get("measurement_basis") is not None:
            raise LexiconError(
                "%s: a REFUSE term must declare measurement_basis as null. A "
                "known basis is precisely what would make it parameterisable "
                "(docs/AMBIGUITY-POLICY.md)" % where
            )
        for key in ("realised_by", "hermes_basis_relationship"):
            if key in raw:
                raise LexiconError(
                    "%s: a REFUSE term must not declare %r. There is no "
                    "measurement basis to realise, so a link to a catalogue "
                    "parameter would assert a resolution that was refused "
                    "(docs/AMBIGUITY-POLICY.md)" % (where, key)
                )
        why_unresolved = _require_text(raw, "why_unresolved", where)
        raw_blocks = _require(raw, "blocks", where)
        if not isinstance(raw_blocks, list) or not raw_blocks:
            raise LexiconError("%s: blocks must be a non-empty list" % where)
        for block in raw_blocks:
            _check_enum(block, _BLOCKS, where, "blocks entry")
        blocks = tuple(dict.fromkeys(str(block) for block in raw_blocks))
        severity = _check_enum(
            _require(raw, "severity", where), _SEVERITIES, where, "severity"
        )
        resolution = _check_resolution(
            _require(raw, "resolution_needed", where), "%s resolution_needed" % where
        )
        raw_candidates = raw.get("candidate_definitions", [])
        if not isinstance(raw_candidates, list):
            raise LexiconError("%s: candidate_definitions must be a list" % where)
        for i, candidate in enumerate(raw_candidates):
            sub = "%s candidate_definitions[%d]" % (where, i)
            _require_text(candidate, "label", sub)
            _require_text(candidate, "measurable_definition", sub)
            for j, field in enumerate(candidate.get("required_hermes_fields", [])):
                _check_hermes_field(field, "%s required_hermes_fields[%d]" % (sub, j))
            if "selected" in candidate or "chosen" in candidate:
                raise LexiconError(
                    "%s must not mark a candidate as selected or chosen: "
                    "presenting an option is not adopting it, and choosing is "
                    "the resolution (see not_sufficiently_defined.schema.json)"
                    % sub
                )
        candidates = tuple(raw_candidates)

    return Term(
        term_id=term_id,
        label=_require_text(raw, "label", where),
        disposition=disposition,
        pattern=_compile(pattern_text, where),
        raw_pattern=pattern_text,
        pid_reference=_require_text(raw, "pid_reference", where),
        measurement_basis=measurement_basis,
        basis_rationale=basis_rationale,
        parameters=parameters,
        required_hermes_fields=hermes,
        why_unresolved=why_unresolved,
        blocks=blocks,
        severity=severity,
        resolution_needed=resolution,
        candidate_definitions=candidates,
        realised_by=realised_by,
        hermes_basis_relationship=basis_relationship,
    )


def _load_unknown_policy(raw: Any, path: Path) -> Mapping[str, Any]:
    where = "%s: unknown_term_policy" % path
    _check_enum(
        _require(raw, "severity", where), _SEVERITIES, where, "severity"
    )
    raw_blocks = _require(raw, "blocks", where)
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise LexiconError("%s: blocks must be a non-empty list" % where)
    for block in raw_blocks:
        _check_enum(block, _BLOCKS, where, "blocks entry")
    _require_text(raw, "why_unresolved_template", where)
    resolution = _require(raw, "resolution_needed", where)
    sub = "%s resolution_needed" % where
    _check_enum(_require(resolution, "kind", sub), _RESOLUTION_KINDS, sub, "kind")
    _check_enum(
        _require(resolution, "responsible", sub), _RESPONSIBLE, sub, "responsible"
    )
    _require_text(resolution, "description_template", sub)
    if raw.get("disposition") != REFUSE:
        raise LexiconError(
            "%s: disposition must be REFUSE. Unknown discretionary terms fail "
            "closed; any other value would make intake fail open (PID line 39)"
            % where
        )
    return raw


def load_lexicon(path: str | os.PathLike | None = None) -> Lexicon:
    """Load, check and return the declared lexicon."""
    target = Path(path) if path is not None else default_lexicon_path()
    try:
        with target.open(encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError as exc:
        raise LexiconError("intake lexicon not found: %s" % target) from exc
    except OSError as exc:
        raise LexiconError("could not read intake lexicon %s: %s" % (target, exc)) from exc
    except json.JSONDecodeError as exc:
        raise LexiconError(
            "intake lexicon %s is not valid JSON: %s (line %d, column %d)"
            % (target, exc.msg, exc.lineno, exc.colno)
        ) from exc

    if not isinstance(raw, Mapping):
        raise LexiconError("intake lexicon %s must be a JSON object" % target)

    raw_terms = _require(raw, "terms", str(target))
    if not isinstance(raw_terms, list) or not raw_terms:
        raise LexiconError("%s: terms must be a non-empty list" % target)
    terms = tuple(_load_term(term, i, target) for i, term in enumerate(raw_terms))
    seen: set[str] = set()
    for term in terms:
        if term.term_id in seen:
            raise LexiconError(
                "%s declares term_id %r more than once; item ids must be unique"
                % (target, term.term_id)
            )
        seen.add(term.term_id)

    raw_markers = _require(raw, "discretionary_markers", str(target))
    if not isinstance(raw_markers, list) or not raw_markers:
        raise LexiconError(
            "%s: discretionary_markers must be a non-empty list. With no "
            "markers declared, nothing outside the ruled terms would ever be "
            "recognised as discretionary and intake would fail open" % target
        )
    markers = []
    for i, marker in enumerate(raw_markers):
        where = "%s: discretionary_markers[%d]" % (target, i)
        marker_id = _require_text(marker, "marker_id", where)
        pattern_text = _require_text(marker, "pattern", where)
        markers.append(
            Marker(
                marker_id=marker_id,
                reason=_require_text(marker, "reason", where),
                pattern=_compile(pattern_text, where),
                raw_pattern=pattern_text,
            )
        )

    return Lexicon(
        version=_require_text(raw, "lexicon_version", str(target)),
        ruling_document=_require_text(raw, "ruling_document", str(target)),
        ratified_by=_require_text(raw, "ratified_by", str(target)),
        source_path=target,
        terms=terms,
        markers=tuple(markers),
        unknown_term_policy=_load_unknown_policy(
            _require(raw, "unknown_term_policy", str(target)), target
        ),
    )
