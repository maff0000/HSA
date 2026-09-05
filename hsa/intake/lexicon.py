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
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from hsa.intake.errors import LexiconError

__all__ = [
    "LEXICON_PATH_ENV",
    "PARAMETERISE",
    "REFUSE",
    "BASIS_SLOT_GROUP",
    "ANCHOR_PLACEHOLDER",
    "WILDCARD_CLASS",
    "Term",
    "Marker",
    "BasisQualifier",
    "GlossConstruction",
    "Attachment",
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

#: The declared categories of basis re-basing. Closed on purpose: a new kind
#: of re-basing is a governance decision recorded in
#: ``docs/AMBIGUITY-POLICY.md``, not a new string invented in a data file.
_QUALIFIER_CATEGORIES = (
    "COMPARATIVE",
    "LOOKBACK",
    "ALTERNATIVE_BASIS",
    "NEIGHBOUR",
)

#: Window units the analyser knows how to cut. One value today; declared as an
#: enum so a lexicon asking for a window nobody implements fails at load
#: rather than silently inspecting the wrong span of text.
_WINDOW_UNITS = ("SENTENCE",)

#: The attachment forms the guard implements. Declared here as an enum the
#: lexicon must cover exactly, so a form added to the data without an
#: implementation — or dropped from the data while the code still relies on
#: it — fails the load instead of silently changing what the guard catches.
_ATTACHMENT_FORMS = ("SLOT", "COMPLEMENT", "GLOSS")

#: The named group every PARAMETERISE pattern must declare: the run of words
#: its pattern tolerates between the ruled adjective and the ruled head noun.
#: That slot is a wildcard, and a re-basing lands IN it ("a large ATR wick"),
#: so the guard has to know where it is. Requiring the group by name is why a
#: term cannot be added whose slot the guard would silently fail to inspect.
BASIS_SLOT_GROUP = "basis_slot"

#: A character class that can match a letter is a WILDCARD: it matches words
#: the lexicon never enumerated. Every one of those in a term pattern must sit
#: inside the declared ``basis_slot`` group, and ``_check_wildcard_slots``
#: refuses to load a lexicon where one does not.
#:
#: This is the structural half of the slot-suppression fix. The analyser can
#: only decline to treat wildcard text as ruled if it can SEE where the
#: wildcard is, and the only thing that tells it is the named group. A term
#: added later with an undeclared wildcard would silently reacquire the old
#: behaviour — its slot would swallow a REFUSE term or a marker and the scan
#: would never look inside — so the loader makes that lexicon unloadable
#: instead of letting it ship.
WILDCARD_CLASS = re.compile(r"\[(?:[^\]\\]|\\.)*\]")

#: Placeholder in a declared gloss pattern, replaced per match by the words
#: the ruled term actually consumed. Substituted with str.replace, never
#: str.format: the patterns carry regex quantifiers such as ``{0,24}``.
ANCHOR_PLACEHOLDER = "{anchor}"

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
class BasisQualifier:
    """A declared construction that re-bases a ruled term.

    ``docs/AMBIGUITY-POLICY.md`` rules on the phrase the lexicon declares.
    Text around that phrase can name a different measurement basis — "large
    wick RELATIVE TO THE RECENT AVERAGE" is not the claim "large wick" — and
    the ruling does not cover the different claim. These are the
    constructions HSA recognises as doing that. Like every other ruling in
    this file they are DATA, so the vocabulary is reviewable without reading
    Python, and like every other pattern here they are surface patterns and
    therefore incomplete; see ``Lexicon.basis_qualifier_policy['limits']``.
    """

    qualifier_id: str
    category: str
    reason: str
    pattern: "re.Pattern[str]"
    raw_pattern: str


@dataclass(frozen=True)
class GlossConstruction:
    """A declared construction in which the source defines its own term.

    "a large wick, and by large I mean twice the 14-period ATR" re-bases the
    ruled term, but nothing about the words "twice the ATR" is attached to
    "wick" by position — what attaches them is that the gloss NAMES the ruled
    word. So the pattern carries an ``{anchor}`` placeholder, replaced per
    match by the words that match actually consumed, and a gloss that names no
    ruled word does not fire.
    """

    gloss_id: str
    reason: str
    raw_pattern: str

    def compile_for(self, anchors: Sequence[str]) -> "re.Pattern[str]":
        """This construction, bound to one term match's own words."""
        return _compile_gloss(self.raw_pattern, tuple(anchors))


@dataclass(frozen=True)
class Attachment:
    """The declared ruling on WHEN a qualifier re-bases a ruled term.

    The window says where a qualifier may be looked for. This says when one
    that was found actually counts, and it is the difference between a guard
    that refuses ordinary trading prose and one that does not. See
    ``basis_qualifier_policy.attachment`` in the lexicon for the ruling
    itself, and ``docs/AMBIGUITY-POLICY.md`` for the reasoning.
    """

    rule: str
    forms: tuple[Mapping[str, Any], ...]
    complement_categories: tuple[str, ...]
    complement_filler: "re.Pattern[str]"
    complement_filler_pattern: str
    gloss_constructions: tuple[GlossConstruction, ...]
    not_attached: str

    def form(self, name: str) -> Mapping[str, Any]:
        for entry in self.forms:
            if entry["form"] == name:
                return entry
        raise LexiconError("no attachment form %r declared" % name)


@lru_cache(maxsize=512)
def _compile_gloss(raw_pattern: str, anchors: tuple[str, ...]) -> "re.Pattern[str]":
    alternation = "(?:%s)" % "|".join(re.escape(anchor) for anchor in anchors)
    return re.compile(raw_pattern.replace(ANCHOR_PLACEHOLDER, alternation))


@dataclass(frozen=True)
class Lexicon:
    version: str
    ruling_document: str
    ratified_by: str
    source_path: Path
    terms: tuple[Term, ...]
    markers: tuple[Marker, ...]
    basis_qualifiers: tuple[BasisQualifier, ...]
    unknown_term_policy: Mapping[str, Any]
    term_match_policy: Mapping[str, Any]
    basis_qualifier_policy: Mapping[str, Any]
    attachment: Attachment

    @property
    def unruled_slot_policy(self) -> Mapping[str, Any]:
        """The ruling applied when a term's wildcard slot holds unruled text."""
        return self.term_match_policy["unruled_slot_content"]

    @property
    def overlap_policy(self) -> Mapping[str, Any]:
        """The ruling applied when two rulings claim the same words.

        Overlap resolution picks which term parameterises; this states what it
        may NOT do while picking, which is delete a refusal or a marker from
        the report.
        """
        return self.term_match_policy["overlap_resolution"]

    @property
    def sentence_boundary_policy(self) -> Mapping[str, Any]:
        """The ruling applied when a match runs across a sentence boundary.

        The third of the three rules that can stop a recognised match
        resolving, and the last to be given a consequence. Its shape is the
        same as the other two on purpose: a reviewer comparing the three
        should not have to notice that one of them says nothing.
        """
        return self.term_match_policy["sentence_boundary"]

    @property
    def sentence_terminators(self) -> str:
        """Terminators a term match may not cross. One declaration, one place.

        ``term_match_policy`` and ``basis_qualifier_policy.window`` are checked
        at load time to declare the same set, because a match boundary and a
        window boundary that disagreed would cut the same text two ways.
        """
        return str(self.term_match_policy["sentence_boundary"]["sentence_terminators"])

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


def _slot_group_span(pattern: str) -> tuple[int, int] | None:
    """Where the declared ``basis_slot`` group sits in the pattern SOURCE.

    Returns the offsets of the group's opening and closing parentheses, or
    ``None`` when the pattern declares no slot. Parentheses are counted with
    escapes and character classes honoured, because ``[)]`` and ``\\)`` are
    literal brackets and closing on one of them would report the wrong span.
    """
    opener = "(?P<%s>" % BASIS_SLOT_GROUP
    start = pattern.find(opener)
    if start < 0:
        return None
    depth = 0
    in_class = False
    index = start
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            index += 2
            continue
        if in_class:
            if char == "]":
                in_class = False
        elif char == "[":
            in_class = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return (start, index + 1)
        index += 1
    return (start, len(pattern))


#: The alphanumeric characters a character class is tested against. ASCII
#: only, because that is what the analyser's normalised text is made of and
#: what every declared pattern is written in.
_PROBE_CHARACTERS = tuple(
    chr(code)
    for code in range(0x20, 0x7F)
    if chr(code).isalnum()
)

#: How many of those a class may accept before it counts as a WILDCARD rather
#: than an enumeration. A ruled term names its words; a class listing three or
#: fewer alphanumerics is naming characters ("[ -]", "[0-9]" is not — that is
#: ten), while one that accepts a run of the alphabet has stopped naming and
#: started accepting whatever is there. This threshold is the guard's declared
#: limit and is stated in its own error message and in
#: ``docs/AMBIGUITY-POLICY.md`` rather than left for a reader to infer.
_ENUMERATED_CLASS_LIMIT = 3


def _class_is_a_wildcard(klass: str) -> bool:
    """Whether a character class accepts an unenumerated run of characters.

    Decided by ASKING the class what it matches, not by looking for known
    spellings in its source text. The previous version tested for the literal
    tokens ``a-z``, ``A-Z``, ``\\w``, ``\\S``, ``\\D`` and a leading ``^``,
    and claimed in its docstring to find "every construct that can match an
    unenumerated word". It did not: ``[a-y ]``, ``[b-z ]`` and
    ``[\\x61-\\x7a ]`` all name a run of the alphabet, spell none of those
    tokens, and loaded cleanly — and with one of them in a pattern the
    analyser silently swallows markers, so "a large wick healthy pullback"
    resolves. That was latent rather than live (no shipped pattern does it,
    and REFUSE terms still surface), but an overstated guard is worse than
    none, and this repository holds itself to that elsewhere.

    A malformed class is treated as a wildcard: refusing to load beats
    guessing what it meant.
    """
    try:
        compiled = re.compile(klass)
    except re.error:
        return True
    accepted = sum(1 for char in _PROBE_CHARACTERS if compiled.match(char))
    return accepted > _ENUMERATED_CLASS_LIMIT


def _wildcards_outside_slot(pattern: str) -> list[str]:
    """Every construct in ``pattern`` that accepts an unenumerated run.

    A ruled term is a phrase the lexicon names. Wherever a pattern stops
    naming words and starts accepting whatever is there, that run is a
    WILDCARD and the text it consumes is not ruled. This finds those runs and
    reports the ones that fall outside the declared ``basis_slot`` group.

    WHAT THIS DOES AND DOES NOT CLAIM. It reports: the escapes ``\\w``,
    ``\\W``, ``\\s``, ``\\S`` and ``\\D``; a bare ``.``; and any character
    class that accepts more than ``_ENUMERATED_CLASS_LIMIT`` ASCII
    alphanumerics, however that class is spelled. It does NOT claim to find
    every conceivable way a regular expression can be permissive — a
    pathological alternation enumerating a hundred words is not a wildcard by
    this test and arguably should not be. The limit is stated rather than
    implied, which is the difference between a guard and an assurance.
    """
    slot = _slot_group_span(pattern)
    slot_start, slot_end = slot if slot else (-1, -1)
    found: list[str] = []
    index = 0
    length = len(pattern)
    while index < length:
        char = pattern[index]
        if char == "\\":
            escape = pattern[index : index + 2]
            if escape[-1:] in ("w", "W", "s", "S", "D"):
                if not (slot_start <= index < slot_end):
                    found.append(escape)
            index += 2
            continue
        if char == "[":
            close = index + 1
            if pattern[close : close + 1] == "^":
                close += 1
            if pattern[close : close + 1] == "]":
                close += 1
            while close < length and pattern[close] != "]":
                close += 2 if pattern[close] == "\\" else 1
            klass = pattern[index : close + 1]
            if _class_is_a_wildcard(klass) and not (slot_start <= index < slot_end):
                found.append(klass)
            index = close + 1
            continue
        if char == ".":
            if not (slot_start <= index < slot_end):
                found.append(".")
        index += 1
    return found


def _check_wildcard_slots(pattern: str, where: str) -> None:
    """Refuse a term pattern whose wildcards are not declared as the slot.

    The analyser treats a term match as ruled text and stops scanning inside
    it — that is how a phrase the lexicon rules on avoids being reported twice
    — with ONE exception: the declared ``basis_slot``, which is wildcard text
    that merely sits between the ruled words and is scanned like any other
    prose. That exception can only be applied where the analyser knows the
    wildcard is, and the named group is the only thing that tells it.

    So an undeclared wildcard is not a style problem. It is the original
    defect, re-armed: a slot that swallowed "near resistance" — one of PID
    line 115's must-not-guess phrases — and hid it behind a resolution,
    silently, at exit 0. Rather than trusting a future author to remember,
    the lexicon simply does not load.

    What counts as a wildcard is decided by ``_wildcards_outside_slot``, and
    its limit is declared there rather than implied. It is not a proof that a
    pattern is free of every possible permissiveness.
    """
    stray = _wildcards_outside_slot(pattern)
    if not stray:
        return
    raise LexiconError(
        "%s: the pattern contains wildcard construct(s) %s outside the "
        "declared (?P<%s>...) group. A wildcard matches words the lexicon "
        "never ruled on, and the analyser must be able to see where it is: "
        "text a term consumed is not scanned again, so an undeclared wildcard "
        "silently swallows whatever falls into it — including a REFUSE term "
        "or a discretionary marker. Wrap the wildcard run in (?P<%s>...), or "
        "enumerate the words the pattern is willing to accept. A character "
        "class counts as a wildcard here when it accepts more than %d ASCII "
        "alphanumerics, whatever it is spelled as "
        "(docs/AMBIGUITY-POLICY.md, 'A wildcard slot is not ruled text')."
        % (where, ", ".join(repr(item) for item in stray), BASIS_SLOT_GROUP,
           BASIS_SLOT_GROUP, _ENUMERATED_CLASS_LIMIT)
    )


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
    _check_wildcard_slots(pattern_text, where)

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
        if BASIS_SLOT_GROUP not in _compile(pattern_text, where).groupindex:
            raise LexiconError(
                "%s: a PARAMETERISE pattern must declare the named group "
                "(?P<%s>...) around the words it tolerates between its ruled "
                "adjective and its ruled head noun. That slot is a wildcard, "
                "and a re-basing lands inside it (\"a large ATR wick\"); "
                "without the group the guard cannot tell the term's own ruled "
                "words from a yardstick smuggled between them, and would "
                "resolve the re-basing silently "
                "(docs/AMBIGUITY-POLICY.md, 'What attaches a qualifier to a "
                "ruled term')." % (where, BASIS_SLOT_GROUP)
            )
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
        if disposition == PARAMETERISE and parameter_names and not raw_links:
            raise LexiconError(
                "%s: a PARAMETERISE term declaring parameters must declare "
                "realised_by linking each one to the catalogue parameter that "
                "implements it. Without the link nothing checks that the ruled "
                "number is the number the catalogue runs, which is the silent "
                "guess PID line 39 forbids wearing a ratified parameter's "
                "paperwork." % where
            )
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


def _load_term_match_policy(
    raw: Any, raw_qualifier_policy: Any, path: Path
) -> Mapping[str, Any]:
    """Check the ruling on how much of a term match counts as RULED text.

    Two declarations live here and both change what the analyser refuses, so
    both are data rather than constants in code:

    * ``sentence_boundary`` — a term match may not span a sentence boundary.
      Its terminator set must be the same one ``basis_qualifier_policy.window``
      cuts sentences with; two different sets would mean a match boundary and
      a window boundary disagreeing about where a sentence ends, which is a
      contradiction a reviewer would have to find by reading code. It must
      also declare a DISPOSITION and everything needed to emit an item, like
      the other two. It did not, and that gap is the whole of R8: it was the
      one of the three rules that could stop a recognised match resolving
      while declaring no consequence and emitting no finding, so for four
      audits it deleted terms in silence. A rule with no declared consequence
      is not a ruling, and this loader no longer accepts one.
    * ``unruled_slot_content`` — what happens when a PARAMETERISE term's
      wildcard slot holds a REFUSE term or an unruled marker. It refuses, for
      the same reason ``unknown_term_policy`` does: undefined language about
      the measurement is undefined language, and it fails closed.
    * ``overlap_resolution`` — what the overlap contest may and may not do. It
      may decide which term parameterises; it may not decide that the loser was
      never said. A PARAMETERISE term whose match collides with a refusal
      refuses too, and for the same reason the other two do.

    All three are declared here rather than assumed in code so that a lexicon
    which drops one, or flips it to PARAMETERISE, fails to load instead of
    quietly re-opening the silent path.
    """
    where = "%s: term_match_policy" % path
    _require_text(raw, "description", where)

    sub = "%s sentence_boundary" % where
    boundary = _require(raw, "sentence_boundary", where)
    _check_enum(_require(boundary, "rule", sub), _WINDOW_UNITS, sub, "rule")
    terminators = _require_text(boundary, "sentence_terminators", sub)
    _require_text(boundary, "intra_token_exception", sub)
    _require_text(boundary, "why", sub)
    if boundary.get("disposition") != REFUSE:
        raise LexiconError(
            "%s: disposition must be REFUSE. A recognised term match that runs "
            "across a sentence boundary is a term HSA will not resolve, and a "
            "term HSA will not resolve fails closed like every other one. This "
            "rule declared no disposition at all for four audits: it discarded "
            "the match instead, so \"a valid m.a breakout\" lost a PID line "
            "118 must-not-guess phrase and drafted at exit 0 with nothing "
            "unresolved (PID line 39)" % sub
        )
    _check_enum(_require(boundary, "severity", sub), _SEVERITIES, sub, "severity")
    raw_blocks = _require(boundary, "blocks", sub)
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise LexiconError("%s: blocks must be a non-empty list" % sub)
    for block in raw_blocks:
        _check_enum(block, _BLOCKS, sub, "blocks entry")
    _require_text(boundary, "precedence", sub)
    _require_text(boundary, "why_unresolved_template", sub)
    resolution = _require(boundary, "resolution_needed", sub)
    deeper = "%s resolution_needed" % sub
    _check_enum(_require(resolution, "kind", deeper), _RESOLUTION_KINDS, deeper, "kind")
    _check_enum(
        _require(resolution, "responsible", deeper), _RESPONSIBLE, deeper, "responsible"
    )
    _require_text(resolution, "description_template", deeper)
    window = _require(raw_qualifier_policy, "window", where)
    declared = window.get("sentence_terminators") if isinstance(window, Mapping) else None
    if declared != terminators:
        raise LexiconError(
            "%s: sentence_terminators is %r but basis_qualifier_policy.window "
            "declares %r. One text, one set of sentence boundaries: a match "
            "that may not cross a boundary and a window bounded by one must "
            "agree on where the boundaries are" % (sub, terminators, declared)
        )

    sub = "%s slot_is_not_ruled_text" % where
    slot_rule = _require(raw, "slot_is_not_ruled_text", where)
    _require_text(slot_rule, "rule", sub)
    _require_text(slot_rule, "why", sub)

    sub = "%s unruled_slot_content" % where
    unruled = _require(raw, "unruled_slot_content", where)
    if unruled.get("disposition") != REFUSE:
        raise LexiconError(
            "%s: disposition must be REFUSE. A wildcard slot holding a REFUSE "
            "term or an unruled marker is undefined language about the "
            "measurement itself; resolving the term over the top of it would "
            "declare a parameter for a quantity the source has not finished "
            "describing, which is the silent guess PID line 39 forbids" % sub
        )
    _check_enum(_require(unruled, "severity", sub), _SEVERITIES, sub, "severity")
    raw_blocks = _require(unruled, "blocks", sub)
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise LexiconError("%s: blocks must be a non-empty list" % sub)
    for block in raw_blocks:
        _check_enum(block, _BLOCKS, sub, "blocks entry")
    _require_text(unruled, "precedence", sub)
    _require_text(unruled, "why_unresolved_template", sub)
    resolution = _require(unruled, "resolution_needed", sub)
    deeper = "%s resolution_needed" % sub
    _check_enum(_require(resolution, "kind", deeper), _RESOLUTION_KINDS, deeper, "kind")
    _check_enum(
        _require(resolution, "responsible", deeper), _RESPONSIBLE, deeper, "responsible"
    )
    _require_text(resolution, "description_template", deeper)

    sub = "%s overlap_resolution" % where
    overlap = _require(raw, "overlap_resolution", where)
    if overlap.get("disposition") != REFUSE:
        raise LexiconError(
            "%s: disposition must be REFUSE. When a ruled PARAMETERISE phrase "
            "and a ruled REFUSE phrase claim the same words, which one the "
            "source means is exactly what is undefined; resolving the "
            "PARAMETERISE reading because the analyser sorted it first is a "
            "silent guess (PID line 39)" % sub
        )
    _check_enum(_require(overlap, "severity", sub), _SEVERITIES, sub, "severity")
    raw_blocks = _require(overlap, "blocks", sub)
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise LexiconError("%s: blocks must be a non-empty list" % sub)
    for block in raw_blocks:
        _check_enum(block, _BLOCKS, sub, "blocks entry")
    _require_text(overlap, "rule", sub)
    _require_text(overlap, "precedence", sub)
    _require_text(overlap, "why", sub)
    _require_text(overlap, "why_unresolved_template", sub)
    resolution = _require(overlap, "resolution_needed", sub)
    deeper = "%s resolution_needed" % sub
    _check_enum(_require(resolution, "kind", deeper), _RESOLUTION_KINDS, deeper, "kind")
    _check_enum(
        _require(resolution, "responsible", deeper), _RESPONSIBLE, deeper, "responsible"
    )
    _require_text(resolution, "description_template", deeper)
    return raw


def _load_basis_qualifier_policy(raw: Any, path: Path) -> Mapping[str, Any]:
    """Check the ruling that governs a re-based term.

    A term whose context re-bases it is an UNDECLARED term, and an undeclared
    term refuses (docs/AMBIGUITY-POLICY.md, "Unknown terms fail closed"). This
    policy therefore has to refuse for the same reason
    ``unknown_term_policy`` does, and the check is the same: any other
    disposition would let a ruled basis be applied over a source that stated
    a different one, which is the silent guess PID line 39 forbids.
    """
    where = "%s: basis_qualifier_policy" % path
    if raw.get("disposition") != REFUSE:
        raise LexiconError(
            "%s: disposition must be REFUSE. A term whose context re-bases it "
            "is an undeclared term, and an undeclared term fails closed; any "
            "other value would let HSA apply a ruled basis over a source that "
            "stated a different one (PID line 39)" % where
        )
    _check_enum(_require(raw, "severity", where), _SEVERITIES, where, "severity")
    raw_blocks = _require(raw, "blocks", where)
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise LexiconError("%s: blocks must be a non-empty list" % where)
    for block in raw_blocks:
        _check_enum(block, _BLOCKS, where, "blocks entry")
    _require_text(raw, "why_unresolved_template", where)
    _require_text(raw, "limits", where)
    resolution = _require(raw, "resolution_needed", where)
    sub = "%s resolution_needed" % where
    _check_enum(_require(resolution, "kind", sub), _RESOLUTION_KINDS, sub, "kind")
    _check_enum(
        _require(resolution, "responsible", sub), _RESPONSIBLE, sub, "responsible"
    )
    _require_text(resolution, "description_template", sub)

    window = _require(raw, "window", where)
    sub = "%s window" % where
    _check_enum(_require(window, "unit", sub), _WINDOW_UNITS, sub, "unit")
    _require_text(window, "sentence_terminators", sub)
    after = _require(window, "sentences_after", sub)
    if not isinstance(after, int) or isinstance(after, bool) or after < 0:
        raise LexiconError(
            "%s: sentences_after must be a non-negative integer; it is the "
            "declared size of the inspected window and must not be guessed in "
            "code" % sub
        )
    _require_text(window, "description", sub)
    return raw


def _load_attachment(raw_policy: Any, path: Path) -> Attachment:
    """Check the ruling that decides WHEN a found qualifier counts.

    This is the reviewable half of the precision fix, so it lives in data and
    is checked here rather than assumed. Every declared form must be one the
    code implements and every implemented form must be declared: a form that
    appeared in the data without an implementation would read as a guarantee
    nothing enforces, which is the exact defect this ruling was rewritten to
    remove.
    """
    where = "%s: basis_qualifier_policy attachment" % path
    raw = _require(raw_policy, "attachment", "%s: basis_qualifier_policy" % path)
    _require_text(raw, "rule", where)
    _require_text(raw, "not_attached", where)

    raw_forms = _require(raw, "forms", where)
    if not isinstance(raw_forms, list) or not raw_forms:
        raise LexiconError("%s: forms must be a non-empty list" % where)
    forms: list[Mapping[str, Any]] = []
    declared: list[str] = []
    for i, entry in enumerate(raw_forms):
        sub = "%s forms[%d]" % (where, i)
        name = _check_enum(_require(entry, "form", sub), _ATTACHMENT_FORMS, sub, "form")
        _require_text(entry, "description", sub)
        _require(entry, "categories", sub)
        declared.append(name)
        forms.append(entry)
    if sorted(declared) != sorted(_ATTACHMENT_FORMS):
        raise LexiconError(
            "%s: forms must declare exactly the attachment forms the guard "
            "implements (%s); it declares %s. A form the code implements but "
            "the data omits is an unreviewed refusal, and a form the data "
            "declares but the code does not implement is a promise nothing "
            "keeps"
            % (where, ", ".join(_ATTACHMENT_FORMS), ", ".join(declared) or "none")
        )

    complement = next(e for e in forms if e["form"] == "COMPLEMENT")
    categories = complement["categories"]
    if not isinstance(categories, list) or not categories:
        raise LexiconError(
            "%s: the COMPLEMENT form must declare a non-empty categories "
            "list. With none, no comparative could ever attach and the "
            "policy document's own worked example would resolve" % where
        )
    for category in categories:
        _check_enum(category, _QUALIFIER_CATEGORIES, where, "COMPLEMENT category")

    filler_text = _require_text(raw, "complement_filler_pattern", where)

    raw_glosses = _require(raw, "gloss_constructions", where)
    if not isinstance(raw_glosses, list) or not raw_glosses:
        raise LexiconError(
            "%s: gloss_constructions must be a non-empty list. With none, a "
            "source that defines its own ruled term (\"by large I mean twice "
            "the ATR\") would resolve onto the ruled basis it just displaced"
            % where
        )
    glosses: list[GlossConstruction] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw_glosses):
        sub = "%s gloss_constructions[%d]" % (where, i)
        gloss_id = _require_text(entry, "gloss_id", sub)
        if gloss_id in seen:
            raise LexiconError("%s declares gloss_id %r more than once" % (where, gloss_id))
        seen.add(gloss_id)
        pattern_text = _require_text(entry, "pattern", sub)
        if ANCHOR_PLACEHOLDER not in pattern_text:
            raise LexiconError(
                "%s: pattern must contain the %s placeholder. A gloss is "
                "attached to a ruled term only because it names that term's "
                "own word; a gloss pattern that names nothing would fire on "
                "any definition anywhere in the window"
                % (sub, ANCHOR_PLACEHOLDER)
            )
        gloss = GlossConstruction(
            gloss_id=gloss_id,
            reason=_require_text(entry, "reason", sub),
            raw_pattern=pattern_text,
        )
        try:
            gloss.compile_for(("probe",))
        except re.error as exc:
            raise LexiconError(
                "%s: pattern is not a valid regular expression once %s is "
                "substituted: %s" % (sub, ANCHOR_PLACEHOLDER, exc)
            ) from exc
        glosses.append(gloss)

    return Attachment(
        rule=str(raw["rule"]),
        forms=tuple(forms),
        complement_categories=tuple(str(c) for c in categories),
        complement_filler=_compile(filler_text, where),
        complement_filler_pattern=filler_text,
        gloss_constructions=tuple(glosses),
        not_attached=str(raw["not_attached"]),
    )


def _load_basis_qualifiers(raw: Any, path: Path) -> tuple[BasisQualifier, ...]:
    """Load the declared re-basing vocabulary. Empty is not allowed.

    With no qualifiers declared, nothing would ever be recognised as changing
    a ruled term's basis, and every ruled term would resolve on sight — the
    exact behaviour the guard exists to stop. So an empty list fails the load,
    for the same reason an empty ``discretionary_markers`` does.
    """
    if not isinstance(raw, list) or not raw:
        raise LexiconError(
            "%s: basis_qualifiers must be a non-empty list. With none "
            "declared, no context could ever be recognised as re-basing a "
            "ruled term and intake would fail open on exactly the case "
            "docs/AMBIGUITY-POLICY.md says refuses" % path
        )
    qualifiers: list[BasisQualifier] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw):
        where = "%s: basis_qualifiers[%d]" % (path, i)
        qualifier_id = _require_text(entry, "qualifier_id", where)
        if qualifier_id in seen:
            raise LexiconError(
                "%s declares qualifier_id %r more than once" % (path, qualifier_id)
            )
        seen.add(qualifier_id)
        pattern_text = _require_text(entry, "pattern", where)
        qualifiers.append(
            BasisQualifier(
                qualifier_id=qualifier_id,
                category=_check_enum(
                    _require(entry, "category", where),
                    _QUALIFIER_CATEGORIES,
                    where,
                    "category",
                ),
                reason=_require_text(entry, "reason", where),
                pattern=_compile(pattern_text, where),
                raw_pattern=pattern_text,
            )
        )
    return tuple(qualifiers)


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
        basis_qualifiers=_load_basis_qualifiers(
            _require(raw, "basis_qualifiers", str(target)), target
        ),
        unknown_term_policy=_load_unknown_policy(
            _require(raw, "unknown_term_policy", str(target)), target
        ),
        term_match_policy=_load_term_match_policy(
            _require(raw, "term_match_policy", str(target)),
            _require(raw, "basis_qualifier_policy", str(target)),
            target,
        ),
        basis_qualifier_policy=_load_basis_qualifier_policy(
            _require(raw, "basis_qualifier_policy", str(target)), target
        ),
        attachment=_load_attachment(
            _require(raw, "basis_qualifier_policy", str(target)), target
        ),
    )
