"""The CER adapter: build, validate and resolve CER evidence references.

CER owns evidence. HSA points at it (PID lines 160-181). This module is the
thin layer that lets HSA do that correctly while CER is not yet live.

WHAT THIS MODULE IS NOT
-----------------------
It is not an evidence store, and it must never become one. PID line 269
makes a CER datastore an explicit non-goal, and PID line 181 permits
fixtures only on the condition that HSA does not create an incompatible
permanent evidence store. So there is deliberately no write path here: no
database, no append-only log, no index file, no cache written to disk.
Every function below either reads a fixture file or checks a document
against the frozen ``cer_reference`` contract. If a future change adds a
write to this module, that change is building the thing the PID forbids.

The consequence, stated plainly so nobody has to infer it: HSA can tell you
what a document CLAIMS about CER evidence, and it can tell you that the
claim is well formed. It cannot tell you the evidence is true. Only CER can,
and until CER is live nothing here has been checked against reality.

TWO SHIPPED SHAPES
------------------
A CER reference reaches HSA in one of two forms, and this module reads both:

  * a single ``cer_reference`` document, which declares ``$hsa_kind``;
  * an inventory evidence container — ``strategies/<id>/<version>/
    evidence.json`` — which declares no ``$hsa_kind`` and holds an array of
    full ``cer_reference`` documents under ``references``.

The container is a convention, not a contract kind, and that is deliberate:
carrying no discriminator is what stops a tool routing it to a schema it was
never meant to satisfy. It exists because evidence is anchored to a version,
so a version's evidence belongs together, with the index metadata that
describes the set rather than any one reference.

``split_evidence_document()`` is the one place that tells the two apart, by
the discriminator and never by filename, and it reports the JSON path of
every reference it finds so a failure can name which entry of a container
failed and which field in it.

THE SEAM
--------
``open_evidence_reader()`` is the single boundary where a live CER client
replaces fixture reads. It returns an ``EvidenceReader``. Today the only
implementation is ``FixtureEvidenceReader``, backed by the JSON documents in
``contracts/fixtures/cer/``; every one of them declares
``source: CONTRACT_FIXTURE``.

When CER goes live, the whole change is:

  1. add a ``LiveCerEvidenceReader`` implementing the same three methods;
  2. have ``open_evidence_reader()`` return it when CER connection details
     are supplied externally (environment/runtime config — never in this
     source, PID line 224);
  3. references it returns declare ``source: CER_LIVE``.

Nothing else in HSA changes, and no fixture data is migrated anywhere:
fixtures are DELETED or left as test data, never promoted into a parallel
evidence store. ``docs/CER-CONTRACT.md`` is the durable statement of this.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from hsa.contracts import (
    DISCRIMINATOR,
    contracts_dir,
    read_json_file,
    validate_document,
)
from hsa.errors import HSAError

__all__ = [
    "KIND",
    "SOURCE_CER_LIVE",
    "SOURCE_CONTRACT_FIXTURE",
    "SOURCES",
    "IDENTITY_FIELDS",
    "OPAQUE_IDENTITY_FIELDS",
    "SUPPORTS",
    "FIXTURES_DIR_ENV",
    "EVIDENCE_CONTAINER_ARRAY",
    "CerError",
    "FixtureUnavailableError",
    "EvidenceNotFoundError",
    "EvidenceDocumentShapeError",
    "reference_types",
    "fixtures_dir",
    "build_reference",
    "validate_reference",
    "validate_reference_file",
    "is_fixture",
    "is_evidence_container",
    "split_evidence_document",
    "read_reference_documents",
    "locate_reference",
    "EvidenceReader",
    "FixtureEvidenceReader",
    "open_evidence_reader",
    "group_by_reference_type",
]

#: The contract kind this module speaks.
KIND = "cer_reference"

#: The two legal values of the ``source`` field. The distinction is declared
#: in every document rather than inferred, which is what makes fixture-backed
#: references findable and replaceable when CER goes live (PID line 181).
SOURCE_CER_LIVE = "CER_LIVE"
SOURCE_CONTRACT_FIXTURE = "CONTRACT_FIXTURE"
SOURCES: tuple[str, ...] = (SOURCE_CER_LIVE, SOURCE_CONTRACT_FIXTURE)

#: The canonical CER identities (PID lines 166-171).
IDENTITY_FIELDS: tuple[str, ...] = (
    "strategy_id",
    "strategy_version",
    "experiment_id",
    "run_id",
    "evidence_id",
    "artifact_id",
)

#: The four CER identities that are opaque to HSA. HSA carries them; it
#: never mints, parses or interprets them. Where the PID is silent about
#: CER's internals that silence is CER's authority, not an invitation.
OPAQUE_IDENTITY_FIELDS: tuple[str, ...] = (
    "experiment_id",
    "run_id",
    "evidence_id",
    "artifact_id",
)

#: What decision a reference is offered in support of (PID line 179).
SUPPORTS: tuple[str, ...] = (
    "PROMOTION",
    "REVISION",
    "REJECTION",
    "INFORMATIONAL",
)

#: Optional environment override for the CER fixture directory. Supplied
#: externally; nothing about location is baked into this source beyond the
#: repository-relative default (PID line 224).
FIXTURES_DIR_ENV = "HSA_CER_FIXTURES_DIR"

#: The array an inventory-local evidence container holds its references
#: in. ``strategies/<id>/<version>/evidence.json`` is a CONVENTION, not a
#: contract kind: it deliberately carries no ``$hsa_kind`` so that no tool
#: routes it to a schema it was never meant to satisfy. What it does carry
#: is this array, and every entry in it IS a full ``cer_reference``.
#:
#: Two shapes therefore ship, and they are told apart by the discriminator
#: rather than by filename: a ``cer_reference`` declares ``$hsa_kind``, a
#: container does not. Both governed packages in ``strategies/`` use the
#: container form, which is why the reader understands it.
EVIDENCE_CONTAINER_ARRAY = "references"

_COMMON_DEFS = "common.defs.json"

_reference_types_cache: tuple[str, ...] | None = None


class CerError(HSAError):
    """A CER adapter operation failed.

    Lives here rather than in ``hsa.errors`` because that module is part of
    the frozen W1 spine. Subclassing ``HSAError`` is enough for ``hsa.cli``
    to map it onto an exit code without knowing it exists.
    """


class FixtureUnavailableError(CerError):
    """The CER fixture directory is missing or unreadable."""


class EvidenceNotFoundError(CerError):
    """No fixture reference matches the requested identity."""


class EvidenceDocumentShapeError(CerError):
    """A file is neither a ``cer_reference`` nor an evidence container.

    Raised instead of guessing. A file HSA cannot recognise is reported
    as unrecognised, naming both shapes it accepts, rather than being
    pushed through the ``cer_reference`` schema and failing with errors
    about a contract it was never meant to satisfy.
    """


def reference_types() -> tuple[str, ...]:
    """The canonical ``reference_type`` values (PID lines 175-179).

    Read from the frozen ``common.defs.json`` rather than restated here, so
    this module cannot drift from the contract it adapts.
    """
    global _reference_types_cache
    if _reference_types_cache is None:
        defs = read_json_file(contracts_dir() / _COMMON_DEFS)
        try:
            values = defs["$defs"]["cer_reference_type"]["enum"]
        except (KeyError, TypeError) as exc:
            raise CerError(
                "%s does not define $defs.cer_reference_type.enum; the "
                "contract set is not the one this adapter expects" % _COMMON_DEFS
            ) from exc
        _reference_types_cache = tuple(str(value) for value in values)
    return _reference_types_cache


def fixtures_dir() -> Path:
    """Resolve the CER fixture directory, failing loudly if it is absent."""
    override = os.environ.get(FIXTURES_DIR_ENV)
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_dir():
            raise FixtureUnavailableError(
                "%s is set to %s but that is not a directory"
                % (FIXTURES_DIR_ENV, candidate)
            )
        return candidate
    candidate = contracts_dir() / "fixtures" / "cer"
    if not candidate.is_dir():
        raise FixtureUnavailableError(
            "CER fixture directory not found at %s; set %s"
            % (candidate, FIXTURES_DIR_ENV)
        )
    return candidate


def build_reference(
    strategy_id: str,
    strategy_version: str,
    reference_type: str,
    source: str,
    recorded_at_utc: str,
    *,
    experiment_id: str | None = None,
    run_id: str | None = None,
    evidence_id: str | None = None,
    artifact_id: str | None = None,
    summary: str | None = None,
    supports: str | None = None,
    contract_version: str | None = None,
) -> dict:
    """Build a ``cer_reference`` document and validate it before returning.

    ``recorded_at_utc`` is required rather than defaulted to "now", because
    a reference records when CER recorded the evidence, which HSA does not
    get to invent.

    At least one of the four opaque CER identities must be supplied; the
    frozen contract rejects a reference that names a strategy but no
    evidence. That check is left to the schema so there is exactly one
    statement of the rule.
    """
    document: dict[str, Any] = {
        "$hsa_kind": KIND,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "reference_type": reference_type,
        "source": source,
        "recorded_at_utc": recorded_at_utc,
    }
    optional = {
        "$hsa_contract_version": contract_version,
        "experiment_id": experiment_id,
        "run_id": run_id,
        "evidence_id": evidence_id,
        "artifact_id": artifact_id,
        "summary": summary,
        "supports": supports,
    }
    for key, value in optional.items():
        if value is not None:
            document[key] = value

    validate_document(document, kind=KIND, source="built cer_reference")
    return document


def validate_reference(document: Any, source: str | None = None) -> dict:
    """Validate a ``cer_reference`` document, returning it unchanged.

    Raises ``DocumentInvalidError`` (exit code 1) on a contract failure.
    """
    validate_document(document, kind=KIND, source=source)
    return dict(document)


def is_fixture(document: Mapping) -> bool:
    """True when this reference stands in for CER rather than resolving in it."""
    return document.get("source") == SOURCE_CONTRACT_FIXTURE


def is_evidence_container(document: Any) -> bool:
    """True when ``document`` is an inventory-local evidence index.

    The inventory stores a strategy version's evidence as one container at
    ``strategies/<id>/<version>/evidence.json`` rather than one file per
    reference: a container groups the evidence anchored to a version and
    carries the index metadata (what is fixture, what is still owed) that
    belongs to the version rather than to any single reference.

    The container is not a contract kind and carries no ``$hsa_kind``. That
    absence is the discriminator, so this check never depends on a filename.
    """
    return (
        isinstance(document, Mapping)
        and DISCRIMINATOR not in document
        and isinstance(document.get(EVIDENCE_CONTAINER_ARRAY), list)
    )


def locate_reference(source: str, json_path: str) -> str:
    """Render "which reference, in which file" as one location label.

    A container holds many references; saying only which file failed would
    leave the reader to find the offending entry by hand.
    """
    return source if json_path == "$" else "%s %s" % (source, json_path)


def split_evidence_document(
    document: Any,
    source: str | None = None,
) -> list[tuple[str, dict]]:
    """Return ``(json_path, reference)`` pairs for one reference document.

    Accepts either shipped shape — a single ``cer_reference``, or an
    evidence container holding an array of them — and reports the JSON path
    of every reference it found, so callers can name exactly which entry of
    a container they are talking about.

    Refuses anything else loudly: an unrecognised file is never guessed at.
    """
    where = source or "document"

    if is_evidence_container(document):
        found: list[tuple[str, dict]] = []
        for index, entry in enumerate(document[EVIDENCE_CONTAINER_ARRAY]):
            json_path = "$.%s[%d]" % (EVIDENCE_CONTAINER_ARRAY, index)
            if not isinstance(entry, Mapping):
                raise EvidenceDocumentShapeError(
                    "%s is a %s, not a cer_reference object: every entry in "
                    "an evidence container's %r array is a full "
                    "cer_reference document"
                    % (
                        locate_reference(where, json_path),
                        type(entry).__name__,
                        EVIDENCE_CONTAINER_ARRAY,
                    )
                )
            found.append((json_path, dict(entry)))
        return found

    if isinstance(document, Mapping) and DISCRIMINATOR in document:
        return [("$", dict(document))]

    raise EvidenceDocumentShapeError(
        "%s is neither a cer_reference nor an evidence container. A "
        "cer_reference declares %s; an evidence container "
        "(strategies/<id>/<version>/evidence.json) declares no %s and holds "
        "its references in a %r array. This document does neither."
        % (where, DISCRIMINATOR, DISCRIMINATOR, EVIDENCE_CONTAINER_ARRAY)
    )


def read_reference_documents(
    path: str | os.PathLike,
) -> list[tuple[str, dict]]:
    """Read a reference file in either shape, without validating it."""
    return split_evidence_document(read_json_file(path), source=str(path))


def validate_reference_file(
    path: str | os.PathLike,
) -> list[tuple[str, dict]]:
    """Validate every ``cer_reference`` in a file, in either shipped shape.

    Returns the ``(json_path, reference)`` pairs it validated. A failure
    names the file AND the reference inside it, so a container with one bad
    entry says which entry and which field.
    """
    found = read_reference_documents(path)
    for json_path, reference in found:
        validate_reference(reference, source=locate_reference(str(path), json_path))
    return found


class EvidenceReader:
    """THE SEAM between HSA and CER.

    Three read methods, no writes. A live CER client implements this and
    ``open_evidence_reader()`` returns it; nothing else in HSA changes.
    Deliberately not an abstraction framework: this is the whole interface.
    """

    #: What ``source`` value the references from this reader carry.
    source: str = SOURCE_CONTRACT_FIXTURE

    def references(self) -> list[dict]:
        """Every reference this reader can see, validated."""
        raise NotImplementedError

    def references_for(
        self,
        strategy_id: str,
        strategy_version: str | None = None,
    ) -> list[dict]:
        """References anchored to one strategy, optionally one version."""
        raise NotImplementedError

    def reference(self, evidence_id: str) -> dict:
        """One reference by its CER ``evidence_id``."""
        raise NotImplementedError


class FixtureEvidenceReader(EvidenceReader):
    """Reads CER references from contract fixtures on disk.

    Read-only by construction: it opens files, validates them against the
    frozen contract and returns dicts. It writes nothing, indexes nothing to
    disk and caches nothing beyond the life of the object, so it cannot
    become the parallel evidence store PID line 181 forbids.
    """

    source = SOURCE_CONTRACT_FIXTURE

    def __init__(self, directory: str | os.PathLike | None = None) -> None:
        self.directory = Path(directory) if directory is not None else fixtures_dir()
        if not self.directory.is_dir():
            raise FixtureUnavailableError(
                "CER fixture directory not found: %s" % self.directory
            )

    def __repr__(self) -> str:
        return "FixtureEvidenceReader(%s)" % self.directory

    def paths(self) -> list[Path]:
        """Fixture files, in a stable order."""
        return sorted(self.directory.glob("*.json"))

    def _load(self) -> Iterator[tuple[str, dict]]:
        for path in self.paths():
            for json_path, document in read_reference_documents(path):
                location = locate_reference(str(path), json_path)
                validate_reference(document, source=location)
                if not is_fixture(document):
                    raise CerError(
                        "%s declares source %r but lives in the fixture "
                        "directory; a fixture must declare %s so it can be "
                        "found and replaced when CER goes live (PID line 181)"
                        % (location, document.get("source"), SOURCE_CONTRACT_FIXTURE)
                    )
                yield location, dict(document)

    def items(self) -> list[tuple[str, dict]]:
        """Reference locations paired with their validated documents.

        One entry per REFERENCE, not per file: a fixture directory holding
        evidence containers yields every reference inside them, each labelled
        with the file and the JSON path it came from.
        """
        return list(self._load())

    def references(self) -> list[dict]:
        return [document for _, document in self._load()]

    def references_for(
        self,
        strategy_id: str,
        strategy_version: str | None = None,
    ) -> list[dict]:
        found = [
            document
            for document in self.references()
            if document.get("strategy_id") == strategy_id
            and (
                strategy_version is None
                or document.get("strategy_version") == strategy_version
            )
        ]
        return found

    def reference(self, evidence_id: str) -> dict:
        for document in self.references():
            if document.get("evidence_id") == evidence_id:
                return document
        raise EvidenceNotFoundError(
            "no CER reference with evidence_id %r in %s. HSA does not "
            "fabricate evidence: while CER is not live, only fixtures "
            "resolve (PID line 181)." % (evidence_id, self.directory)
        )


def open_evidence_reader(
    directory: str | os.PathLike | None = None,
) -> EvidenceReader:
    """Return the evidence reader HSA should use.

    THE SEAM. Today this is always a ``FixtureEvidenceReader``, because CER
    is not live. When it is, this function chooses a live client from
    externally supplied connection details and returns it instead; callers
    are unaffected because they only ever see ``EvidenceReader``.
    """
    return FixtureEvidenceReader(directory)


def group_by_reference_type(
    references: Sequence[Mapping],
) -> dict[str, list[Mapping]]:
    """Group references by ``reference_type``, in canonical order.

    Only types actually present appear, so an empty group is never mistaken
    for evidence that exists but is empty.
    """
    grouped: dict[str, list[Mapping]] = {}
    for reference_type in reference_types():
        matching = [
            reference
            for reference in references
            if reference.get("reference_type") == reference_type
        ]
        if matching:
            grouped[reference_type] = matching
    return grouped
