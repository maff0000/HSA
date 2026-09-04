"""Strategy version lifecycle and lineage (PID lines 183-200).

This module implements one governance rule and its consequences:

    A promoted strategy version is immutable. A proposed modification is a
    SEPARATELY VERSIONED CANDIDATE that must pass the governed evidence
    gates again.  (PID lines 185-189, acceptance criterion 13 at line 262)

Everything here is a pure function over ``strategy_package`` documents. No
document is ever modified in place: ``derive_candidate`` and
``apply_status_transition`` deep-copy their input and return a new document,
so the caller decides what, if anything, is written to Git. There is no
store, index, registry or cache in this module — Git is the durable
authority (PID line 226) and the strategy inventory is a set of package
files, not a database.

The public surface:

    STATUSES / SUPERSEDABLE_STATUSES / ALLOWED_STATUS_TRANSITIONS
    parse_version(text) / format_version(parts) / bump_version(text, part)
    status_of(package) / is_promoted(package)
    derive_candidate(promoted, rationale, ...)   -> new candidate package
    apply_status_transition(package, new_status) -> new package
    describe_in_place_mutation(promoted, proposed) -> list[Change]
    refuse_in_place_mutation(promoted, proposed)  -> None or raises
    supersedes_of(package) / lineage(packages)

WHY THE ERRORS LIVE HERE, NOT IN ``hsa.errors``: ``hsa/errors.py`` is part
of the frozen W1 contract spine and is not edited by later work items. Both
error types below subclass ``HSAError``, so ``hsa.cli`` maps them onto exit
code 3 without knowing they exist.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, NamedTuple, Sequence

from hsa.errors import HSAError

__all__ = [
    "STATUS_CANDIDATE",
    "STATUS_PROMOTED",
    "STATUS_DORMANT",
    "STATUS_RETIRED",
    "STATUSES",
    "SUPERSEDABLE_STATUSES",
    "ALLOWED_STATUS_TRANSITIONS",
    "VERSION_PARTS",
    "CARRIED_FORWARD_REFERENCE_TYPES",
    "GATE_VERDICT_REFERENCE_TYPES",
    "VersioningError",
    "PromotedVersionImmutableError",
    "Change",
    "LineageLink",
    "parse_version",
    "format_version",
    "bump_version",
    "status_of",
    "is_promoted",
    "identity_of",
    "supersedes_of",
    "derive_candidate",
    "apply_status_transition",
    "describe_in_place_mutation",
    "refuse_in_place_mutation",
    "lineage",
    "utc_now",
]

#: Lifecycle statuses, mirroring the frozen ``lifecycle.status`` enum in
#: ``contracts/strategy_package.schema.json``.
STATUS_CANDIDATE = "CANDIDATE"
STATUS_PROMOTED = "PROMOTED"
STATUS_DORMANT = "DORMANT"
STATUS_RETIRED = "RETIRED"

STATUSES: tuple[str, ...] = (
    STATUS_CANDIDATE,
    STATUS_PROMOTED,
    STATUS_DORMANT,
    STATUS_RETIRED,
)

#: Statuses that mean "this version has been through promotion". These are
#: the immutable ones (PID line 185) and the only ones a candidate may
#: legitimately supersede: the frozen schema describes ``supersedes`` as
#: "the promoted version this candidate proposes to replace", and a version
#: that was never promoted is not that.
SUPERSEDABLE_STATUSES: tuple[str, ...] = (
    STATUS_PROMOTED,
    STATUS_DORMANT,
    STATUS_RETIRED,
)

#: The only status changes allowed on an existing version. Everything else
#: about a promoted version is frozen, but activation state must be able to
#: move, because dormancy is a normal resting state and an old proven
#: strategy must be able to reactivate when conditions return (PID lines
#: 195, 197). Nothing ever returns to CANDIDATE: a revision is a new
#: version, never a demotion of an existing one (PID line 189).
ALLOWED_STATUS_TRANSITIONS: dict[str, tuple[str, ...]] = {
    STATUS_CANDIDATE: (STATUS_PROMOTED, STATUS_RETIRED),
    STATUS_PROMOTED: (STATUS_DORMANT, STATUS_RETIRED),
    STATUS_DORMANT: (STATUS_PROMOTED, STATUS_RETIRED),
    STATUS_RETIRED: (),
}

#: Semver components, in the order ``parse_version`` returns them.
VERSION_PARTS: tuple[str, ...] = ("MAJOR", "MINOR", "PATCH")

#: CER reference types a derived candidate inherits from the version it
#: supersedes. These describe where the strategy came from and what was
#: learned; they remain true statements about their own anchored version.
CARRIED_FORWARD_REFERENCE_TYPES: tuple[str, ...] = (
    "SOURCE_ANALYSIS",
    "STRATEGY_HYPOTHESIS",
    "RESEARCH_FINDING",
    "VERSION_LINEAGE",
)

#: CER reference types a derived candidate does NOT inherit. These are
#: verdicts reached on the superseded version, and PID line 189 requires the
#: candidate to pass the governed evidence gates AGAIN. Carrying a parent's
#: promotion evidence onto a candidate would let a modification inherit an
#: approval it never earned, which is precisely what acceptance criterion 13
#: (PID line 262) exists to prevent.
GATE_VERDICT_REFERENCE_TYPES: tuple[str, ...] = (
    "PROMOTION_EVIDENCE",
    "REVISION_EVIDENCE",
    "REJECTION_EVIDENCE",
)

_LIFECYCLE = "lifecycle"
_STATUS = "status"


class VersioningError(HSAError):
    """A version, lifecycle or lineage operation was refused."""


class PromotedVersionImmutableError(VersioningError):
    """An in-place modification of a promoted version was refused.

    PID line 185: promoted strategy versions are immutable. PID line 187: do
    not tweak a live strategy in place. Raising this is the enforcement of
    those two lines; ``changes`` carries the exact JSON paths that were
    going to be edited so the refusal names what it refused.
    """

    def __init__(
        self,
        strategy_id: str,
        strategy_version: str,
        status: str,
        changes: Sequence["Change"],
        source: str | None = None,
    ) -> None:
        self.strategy_id = strategy_id
        self.strategy_version = strategy_version
        self.status = status
        self.changes = list(changes)
        self.source = source
        super().__init__(self._render())

    def _render(self) -> str:
        where = " (%s)" % self.source if self.source else ""
        head = (
            "refusing in-place modification of %s %s%s: that version is %s "
            "and promoted versions are immutable (PID lines 185-187). "
            "%d change%s refused:"
            % (
                self.strategy_id,
                self.strategy_version,
                where,
                self.status,
                len(self.changes),
                "" if len(self.changes) == 1 else "s",
            )
        )
        lines = [head]
        for change in self.changes:
            lines.append("  %s" % change.describe())
        lines.append(
            "a modification must be a separately versioned candidate that "
            "passes the governed evidence gates again (PID line 189, "
            "acceptance criterion 13 at PID line 262): derive one with "
            "hsa.versioning.derive_candidate()."
        )
        return "\n".join(lines)


class Change(NamedTuple):
    """One differing JSON location between two documents."""

    path: str
    before: Any
    after: Any

    def describe(self) -> str:
        return "%s: %s -> %s" % (self.path, _render(self.before), _render(self.after))


class LineageLink(NamedTuple):
    """One step in a strategy's version lineage."""

    strategy_id: str
    strategy_version: str
    status: str
    supersedes_version: str | None
    rationale: str | None


def utc_now() -> str:
    """Current instant as a contract-shaped UTC timestamp.

    UTC is canonical (PID line 225); local time never reaches a document.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _render(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


def parse_version(text: Any) -> tuple[int, int, int]:
    """Parse strict ``MAJOR.MINOR.PATCH`` into a comparable tuple."""
    if not isinstance(text, str):
        raise VersioningError(
            "strategy_version must be a string, got %s" % type(text).__name__
        )
    parts = text.split(".")
    if len(parts) != 3:
        raise VersioningError(
            "strategy_version %r is not strict MAJOR.MINOR.PATCH semver" % text
        )
    numbers: list[int] = []
    for part in parts:
        if not part.isdigit() or (len(part) > 1 and part.startswith("0")):
            raise VersioningError(
                "strategy_version %r is not strict MAJOR.MINOR.PATCH semver" % text
            )
        numbers.append(int(part))
    return numbers[0], numbers[1], numbers[2]


def format_version(parts: Iterable[int]) -> str:
    """Render a ``(major, minor, patch)`` tuple as semver."""
    values = list(parts)
    if len(values) != 3:
        raise VersioningError("a version needs exactly 3 parts, got %d" % len(values))
    if any(not isinstance(value, int) or value < 0 for value in values):
        raise VersioningError("version parts must be non-negative integers")
    return "%d.%d.%d" % (values[0], values[1], values[2])


def bump_version(text: str, part: str = "MINOR") -> str:
    """Return the next version after ``text``, bumping ``part``."""
    if part not in VERSION_PARTS:
        raise VersioningError(
            "unknown version part %r (known: %s)" % (part, ", ".join(VERSION_PARTS))
        )
    major, minor, patch = parse_version(text)
    if part == "MAJOR":
        return format_version((major + 1, 0, 0))
    if part == "MINOR":
        return format_version((major, minor + 1, 0))
    return format_version((major, minor, patch + 1))


def _require_mapping(package: Any, label: str) -> Mapping:
    if not isinstance(package, Mapping):
        raise VersioningError(
            "%s must be a strategy_package object, got %s"
            % (label, type(package).__name__)
        )
    return package


def identity_of(package: Any) -> tuple[str, str]:
    """Return ``(strategy_id, strategy_version)``.

    Identity is always id plus version (PID line 259, acceptance criterion
    10); neither half alone identifies anything governable.
    """
    mapping = _require_mapping(package, "package")
    strategy_id = mapping.get("strategy_id")
    strategy_version = mapping.get("strategy_version")
    if not isinstance(strategy_id, str) or not strategy_id:
        raise VersioningError("package has no usable strategy_id")
    if not isinstance(strategy_version, str) or not strategy_version:
        raise VersioningError(
            "package %s has no usable strategy_version" % strategy_id
        )
    parse_version(strategy_version)
    return strategy_id, strategy_version


def status_of(package: Any) -> str:
    """Return the package's lifecycle status, refusing to guess."""
    mapping = _require_mapping(package, "package")
    lifecycle = mapping.get(_LIFECYCLE)
    if not isinstance(lifecycle, Mapping):
        raise VersioningError(
            "package has no lifecycle object; its version status cannot be "
            "determined and is not assumed"
        )
    status = lifecycle.get(_STATUS)
    if status not in STATUSES:
        raise VersioningError(
            "unknown lifecycle status %r (known: %s)" % (status, ", ".join(STATUSES))
        )
    return str(status)


def is_promoted(package: Any) -> bool:
    """True when this version has been through promotion and is frozen."""
    return status_of(package) in SUPERSEDABLE_STATUSES


def supersedes_of(package: Any) -> Mapping | None:
    """Return the ``lifecycle.supersedes`` object, or None for an original."""
    mapping = _require_mapping(package, "package")
    lifecycle = mapping.get(_LIFECYCLE)
    if not isinstance(lifecycle, Mapping):
        return None
    value = lifecycle.get("supersedes")
    return value if isinstance(value, Mapping) else None


def derive_candidate(
    promoted: Mapping,
    rationale: str,
    *,
    bump: str = "MINOR",
    changes: Mapping[str, Any] | None = None,
    created_at_utc: str | None = None,
    lineage_reference: Mapping | None = None,
) -> dict:
    """Derive a separately versioned CANDIDATE from a promoted package.

    This is acceptance criterion 13 (PID line 262) as a function: the way to
    propose a modification is to produce a NEW version, never to edit the
    promoted one. ``promoted`` is not modified; a deep copy is returned.

    ``changes`` is the proposed modification, applied as a top-level merge.
    Identity and lifecycle fields are refused there because this function
    derives them — smuggling a strategy_version through ``changes`` would be
    an in-place edit wearing a candidate's clothes.

    The returned candidate:

    * carries the same ``strategy_id`` (identity is preserved across
      versions, PID line 259);
    * has the next version, ``lifecycle.status`` CANDIDATE and
      ``lifecycle.supersedes`` naming the version it proposes to replace
      together with the rationale;
    * inherits only the CER references in
      ``CARRIED_FORWARD_REFERENCE_TYPES``. Promotion, revision and rejection
      evidence is deliberately dropped, because the candidate must pass the
      governed evidence gates again (PID line 189);
    * carries a VERSION_LINEAGE reference of its own when one is supplied.

    The result is NOT validated here — validation belongs to
    ``hsa.contracts.validate_document``, and this module does not duplicate
    the contract. Callers should validate before writing anything.
    """
    mapping = _require_mapping(promoted, "promoted package")
    strategy_id, strategy_version = identity_of(mapping)
    status = status_of(mapping)

    if status not in SUPERSEDABLE_STATUSES:
        raise VersioningError(
            "cannot derive a candidate from %s %s: it is %s, not a promoted "
            "version. A version that has never been promoted is not frozen, "
            "so it is edited directly rather than superseded (PID lines "
            "185-189)." % (strategy_id, strategy_version, status)
        )

    if not isinstance(rationale, str) or not rationale.strip():
        raise VersioningError(
            "a candidate superseding %s %s needs a non-empty rationale: the "
            "frozen contract requires one, so a redesign always says why "
            "(PID line 189)" % (strategy_id, strategy_version)
        )

    candidate = copy.deepcopy(dict(mapping))

    forbidden = {"strategy_id", "strategy_version", _LIFECYCLE}
    if changes:
        offending = sorted(forbidden.intersection(changes))
        if offending:
            raise VersioningError(
                "changes may not set %s: those are derived by "
                "derive_candidate(), and setting them by hand is how an "
                "in-place edit disguises itself as a candidate "
                "(PID lines 185-189)" % ", ".join(offending)
            )
        candidate.update(copy.deepcopy(dict(changes)))

    candidate["strategy_version"] = bump_version(strategy_version, bump)
    candidate[_LIFECYCLE] = {
        _STATUS: STATUS_CANDIDATE,
        "immutable_once_promoted": True,
        "created_at_utc": created_at_utc or utc_now(),
        "supersedes": {
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "rationale": rationale,
        },
    }

    inherited = [
        reference
        for reference in candidate.get("cer_references", [])
        if isinstance(reference, Mapping)
        and reference.get("reference_type") in CARRIED_FORWARD_REFERENCE_TYPES
    ]
    if lineage_reference is not None:
        inherited.append(copy.deepcopy(dict(lineage_reference)))
    candidate["cer_references"] = inherited

    return candidate


def apply_status_transition(
    package: Mapping,
    new_status: str,
    *,
    source: str | None = None,
) -> dict:
    """Return a copy of ``package`` with its lifecycle status changed.

    Activation state is the one thing about a promoted version that moves:
    dormancy is not failure and an old proven strategy must be able to
    reactivate when conditions return (PID lines 195, 197). Everything else
    stays frozen, and no transition ever returns a version to CANDIDATE.
    """
    mapping = _require_mapping(package, "package")
    strategy_id, strategy_version = identity_of(mapping)
    current = status_of(mapping)

    if new_status not in STATUSES:
        raise VersioningError(
            "unknown lifecycle status %r (known: %s)"
            % (new_status, ", ".join(STATUSES))
        )
    if new_status == current:
        return copy.deepcopy(dict(mapping))
    allowed = ALLOWED_STATUS_TRANSITIONS[current]
    if new_status not in allowed:
        where = " (%s)" % source if source else ""
        raise VersioningError(
            "refusing lifecycle transition %s -> %s for %s %s%s: allowed "
            "from %s is %s. A revision is a new candidate version, never a "
            "demotion of an existing one (PID line 189)."
            % (
                current,
                new_status,
                strategy_id,
                strategy_version,
                where,
                current,
                ", ".join(allowed) if allowed else "nothing",
            )
        )

    updated = copy.deepcopy(dict(mapping))
    lifecycle = dict(updated[_LIFECYCLE])
    lifecycle[_STATUS] = new_status
    updated[_LIFECYCLE] = lifecycle
    return updated


def _diff(before: Any, after: Any, path: str = "$") -> list[Change]:
    """Every JSON location at which two documents differ."""
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        found: list[Change] = []
        for key in sorted(set(before) | set(after)):
            child = "%s.%s" % (path, key)
            if key not in before:
                found.append(Change(child, None, after[key]))
            elif key not in after:
                found.append(Change(child, before[key], None))
            else:
                found.extend(_diff(before[key], after[key], child))
        return found
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return [Change(path, before, after)]
        found = []
        for index, (left, right) in enumerate(zip(before, after)):
            found.extend(_diff(left, right, "%s[%d]" % (path, index)))
        return found
    if type(before) is not type(after) or before != after:
        return [Change(path, before, after)]
    return []


def describe_in_place_mutation(
    promoted: Mapping,
    proposed: Mapping,
) -> list[Change]:
    """Return the changes that would mutate a promoted version in place.

    An empty list means ``proposed`` is not an in-place mutation: either it
    is a different version, or the version it shares has never been
    promoted, or the only difference is a permitted status transition.

    Raises ``VersioningError`` if the two documents are not the same
    strategy — comparing unrelated strategies is a caller mistake, and
    answering "no mutation" to it would be a misleading pass.
    """
    left_id, left_version = identity_of(promoted)
    right_id, right_version = identity_of(proposed)

    if left_id != right_id:
        raise VersioningError(
            "cannot compare %s with %s: different strategies, so neither is "
            "an in-place modification of the other" % (left_id, right_id)
        )
    if left_version != right_version:
        return []
    if status_of(promoted) not in SUPERSEDABLE_STATUSES:
        return []

    differences = _diff(dict(promoted), dict(proposed))

    status_path = "$.%s.%s" % (_LIFECYCLE, _STATUS)
    permitted: list[Change] = []
    for change in differences:
        if change.path != status_path:
            continue
        allowed = ALLOWED_STATUS_TRANSITIONS.get(str(change.before), ())
        if change.after in allowed:
            permitted.append(change)

    return [change for change in differences if change not in permitted]


def refuse_in_place_mutation(
    promoted: Mapping,
    proposed: Mapping,
    *,
    source: str | None = None,
) -> None:
    """Raise ``PromotedVersionImmutableError`` on an in-place modification.

    The enforcement point for PID lines 185-187 and acceptance criterion 13.
    Returns None when ``proposed`` is a legitimate new version, an untouched
    copy, or a permitted activation-state change.
    """
    changes = describe_in_place_mutation(promoted, proposed)
    if not changes:
        return
    strategy_id, strategy_version = identity_of(promoted)
    raise PromotedVersionImmutableError(
        strategy_id,
        strategy_version,
        status_of(promoted),
        changes,
        source=source,
    )


def lineage(packages: Iterable[Mapping]) -> list[LineageLink]:
    """Order a set of packages for one strategy into its version lineage.

    Ordering is by semver, oldest first, which is also supersession order:
    a candidate always supersedes an earlier version. Refuses a mixed
    strategy_id, because a lineage crosses versions, never strategies.
    """
    links: list[tuple[tuple[int, int, int], LineageLink]] = []
    seen_ids: set[str] = set()
    seen_versions: set[str] = set()

    for package in packages:
        strategy_id, strategy_version = identity_of(package)
        seen_ids.add(strategy_id)
        if len(seen_ids) > 1:
            raise VersioningError(
                "cannot build a lineage across different strategies: %s"
                % ", ".join(sorted(seen_ids))
            )
        if strategy_version in seen_versions:
            raise VersioningError(
                "duplicate version %s %s in lineage: a version is immutable, "
                "so it appears exactly once (PID line 185)"
                % (strategy_id, strategy_version)
            )
        seen_versions.add(strategy_version)

        supersedes = supersedes_of(package)
        links.append(
            (
                parse_version(strategy_version),
                LineageLink(
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    status=status_of(package),
                    supersedes_version=(
                        str(supersedes.get("strategy_version"))
                        if supersedes
                        else None
                    ),
                    rationale=(
                        str(supersedes.get("rationale")) if supersedes else None
                    ),
                ),
            )
        )

    links.sort(key=lambda item: item[0])
    return [link for _, link in links]
