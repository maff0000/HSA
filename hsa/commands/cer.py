"""``hsa cer`` — inspect and validate CER references, evidence and lineage.

CER owns evidence; HSA points at it (PID lines 160-181). This command is a
read-only window onto what HSA's documents CLAIM about CER evidence, and a
contract check on those claims. It never writes anything.

While CER is not live the references resolve from contract fixtures in
``contracts/fixtures/cer/``, every one of which declares
``source: CONTRACT_FIXTURE``. Output always says which, because a fixture
being mistaken for live evidence is the failure this labelling exists to
prevent (PID line 181).

Actions:

    hsa cer list      references visible to the evidence reader
    hsa cer show      one reference, by CER evidence_id
    hsa cer validate  check reference documents against the frozen contract,
                      whether a single cer_reference or an inventory
                      evidence.json container holding an array of them
    hsa cer lineage   version lineage and evidence for one strategy's packages

Exit codes are owned by ``hsa.cli``, not here: this module raises the typed
errors and returns 0.
"""

from __future__ import annotations

import argparse
from typing import Iterable, Mapping, Sequence

from hsa.cer import (
    EVIDENCE_CONTAINER_ARRAY,
    FIXTURES_DIR_ENV,
    CerError,
    SOURCE_CONTRACT_FIXTURE,
    SOURCES,
    EvidenceReader,
    group_by_reference_type,
    is_fixture,
    open_evidence_reader,
    reference_types,
    validate_reference_file,
)
from hsa.contracts import read_json_file
from hsa.versioning import lineage

NAME = "cer"
HELP = "inspect and validate CER references, evidence and version lineage"

_HANDLER = "_cer_handler"

#: What ``supports`` values a reference may declare (PID line 179).
_SUPPORTS = ("PROMOTION", "REVISION", "REJECTION", "INFORMATIONAL")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fixtures",
        dest="fixtures",
        metavar="<dir>",
        default=None,
        help=(
            "CER fixture directory to read from. Defaults to $%s, then to "
            "contracts/fixtures/cer in the checkout." % FIXTURES_DIR_ENV
        ),
    )
    actions = parser.add_subparsers(dest="cer_action", metavar="<action>")
    actions.required = True

    listing = actions.add_parser(
        "list",
        help="list CER references the evidence reader can see",
        description="List CER references, optionally filtered.",
    )
    listing.add_argument(
        "--strategy",
        metavar="<strategy_id>",
        default=None,
        help="only references anchored to this strategy",
    )
    listing.add_argument(
        "--strategy-version",
        metavar="<semver>",
        default=None,
        help="only references anchored to this version (needs --strategy)",
    )
    listing.add_argument(
        "--type",
        dest="reference_type",
        metavar="<type>",
        default=None,
        help="only references of this reference_type",
    )
    listing.add_argument(
        "--supports",
        metavar="<decision>",
        choices=_SUPPORTS,
        default=None,
        help="only references supporting this decision: %s" % ", ".join(_SUPPORTS),
    )
    listing.set_defaults(**{_HANDLER: _run_list})

    show = actions.add_parser(
        "show",
        help="show one CER reference by evidence_id",
        description="Show a single CER reference in full.",
    )
    show.add_argument(
        "evidence_id",
        metavar="<evidence_id>",
        help="the CER evidence_id to resolve (opaque to HSA)",
    )
    show.set_defaults(**{_HANDLER: _run_show})

    validate = actions.add_parser(
        "validate",
        help="validate cer_reference documents against the frozen contract",
        description=(
            "Validate CER references. A named file may be a single "
            "cer_reference document or an inventory evidence container "
            "(strategies/<id>/<version>/evidence.json), which holds a "
            "%r array of full cer_reference documents; every reference in "
            "it is validated and reported by its JSON path. With no paths, "
            "every fixture in the fixture directory is validated and checked "
            "for its CONTRACT_FIXTURE label." % EVIDENCE_CONTAINER_ARRAY
        ),
    )
    validate.add_argument(
        "paths",
        metavar="<file>",
        nargs="*",
        help=(
            "cer_reference documents, or evidence.json containers holding "
            "them"
        ),
    )
    validate.set_defaults(**{_HANDLER: _run_validate})

    lineage_parser = actions.add_parser(
        "lineage",
        help="show version lineage and evidence for a strategy's packages",
        description=(
            "Show the version lineage across strategy_package documents for "
            "one strategy, with the CER evidence anchored to each version."
        ),
    )
    lineage_parser.add_argument(
        "paths",
        metavar="<package.json>",
        nargs="+",
        help="strategy_package documents, one per version",
    )
    lineage_parser.add_argument(
        "--no-evidence",
        action="store_true",
        help="show lineage only, without resolving CER evidence",
    )
    lineage_parser.set_defaults(**{_HANDLER: _run_lineage})


def run(args: argparse.Namespace) -> int:
    handler = getattr(args, _HANDLER)
    return handler(args)


def _reader(args: argparse.Namespace) -> EvidenceReader:
    return open_evidence_reader(args.fixtures)


def _source_note(reader: EvidenceReader) -> str:
    if reader.source == SOURCE_CONTRACT_FIXTURE:
        return (
            "source: CONTRACT_FIXTURE — CER is not live; these are contract "
            "fixtures standing in for it (PID line 181). Nothing here has "
            "been checked against real evidence."
        )
    return "source: %s — resolved in CER." % reader.source


def _line(reference: Mapping) -> str:
    identities = " ".join(
        "%s=%s" % (field, reference[field])
        for field in ("experiment_id", "run_id", "evidence_id", "artifact_id")
        if field in reference
    )
    return "  %-22s %-14s %s\n      %s\n      %s" % (
        reference["reference_type"],
        reference.get("supports", "-"),
        "%s %s" % (reference["strategy_id"], reference["strategy_version"]),
        identities,
        reference.get("summary", "(no summary)"),
    )


def _print_group(references: Sequence[Mapping]) -> None:
    for reference_type, group in group_by_reference_type(references).items():
        print("%s (%d)" % (reference_type, len(group)))
        for reference in group:
            print(_line(reference))


def _run_list(args: argparse.Namespace) -> int:
    reader = _reader(args)
    if args.strategy:
        references: Iterable[Mapping] = reader.references_for(
            args.strategy, args.strategy_version
        )
    else:
        references = reader.references()

    if args.reference_type:
        known = reference_types()
        if args.reference_type not in known:
            raise CerError(
                "no such reference_type %r; the canonical types are %s "
                "(PID lines 175-179)" % (args.reference_type, ", ".join(known))
            )
        references = [
            reference
            for reference in references
            if reference["reference_type"] == args.reference_type
        ]
    if args.supports:
        references = [
            reference
            for reference in references
            if reference.get("supports") == args.supports
        ]

    references = list(references)
    print(_source_note(reader))
    print("%d reference%s" % (len(references), "" if len(references) == 1 else "s"))
    if not references:
        print("  (none matched)")
        return 0
    print("")
    _print_group(references)
    return 0


def _run_show(args: argparse.Namespace) -> int:
    reader = _reader(args)
    reference = reader.reference(args.evidence_id)
    print(_source_note(reader))
    print("")
    for key in (
        "strategy_id",
        "strategy_version",
        "experiment_id",
        "run_id",
        "evidence_id",
        "artifact_id",
        "reference_type",
        "supports",
        "source",
        "recorded_at_utc",
        "summary",
    ):
        if key in reference:
            print("%-18s %s" % (key, reference[key]))
    return 0


def _source_note_for(label: object) -> str:
    if label in SOURCES:
        return ""
    return "  <- unexpected source, expected one of %s" % ", ".join(SOURCES)


def _run_validate(args: argparse.Namespace) -> int:
    if args.paths:
        for path in args.paths:
            # Either shipped shape: one cer_reference, or an inventory
            # evidence container holding an array of them. A failure names
            # the file AND the reference inside it.
            found = validate_reference_file(path)
            if len(found) == 1 and found[0][0] == "$":
                document = found[0][1]
                label = document.get("source")
                print(
                    "%s: valid cer_reference (%s)%s"
                    % (path, label, _source_note_for(label))
                )
                continue
            print(
                "%s: valid evidence container, %d reference%s"
                % (path, len(found), "" if len(found) == 1 else "s")
            )
            for json_path, document in found:
                label = document.get("source")
                print(
                    "  %s: valid cer_reference (%s, %s)%s"
                    % (
                        json_path,
                        document["reference_type"],
                        label,
                        _source_note_for(label),
                    )
                )
        return 0

    reader = _reader(args)
    items = getattr(reader, "items", None)
    if items is None:
        print("%s exposes no fixture files to validate" % reader)
        return 0
    # Loading is what validates: the reader refuses any fixture that fails
    # the contract or is not labelled CONTRACT_FIXTURE.
    loaded = items()
    for location, reference in loaded:
        print(
            "%s: valid cer_reference (%s, %s)"
            % (
                location,
                reference["reference_type"],
                "fixture" if is_fixture(reference) else reference["source"],
            )
        )
    # Counted in references, not files: a fixture directory may hold
    # evidence containers, and one container file carries many references.
    print(
        "%d reference%s valid and labelled %s"
        % (
            len(loaded),
            "" if len(loaded) == 1 else "s",
            SOURCE_CONTRACT_FIXTURE,
        )
    )
    return 0


def _run_lineage(args: argparse.Namespace) -> int:
    packages = [read_json_file(path) for path in args.paths]
    links = lineage(packages)
    strategy_id = links[0].strategy_id if links else "(none)"

    print("strategy_id %s — %d version%s" % (strategy_id, len(links), "" if len(links) == 1 else "s"))
    print("")

    reader = None if args.no_evidence else _reader(args)
    for link in links:
        origin = (
            "supersedes %s — %s" % (link.supersedes_version, link.rationale)
            if link.supersedes_version
            else "original version, supersedes nothing"
        )
        print("%s  [%s]" % (link.strategy_version, link.status))
        print("  %s" % origin)
        if reader is not None:
            references = reader.references_for(strategy_id, link.strategy_version)
            if not references:
                print("  evidence: none anchored to this version")
            else:
                for reference in references:
                    print(
                        "  evidence: %-22s %-14s %s"
                        % (
                            reference["reference_type"],
                            reference.get("supports", "-"),
                            reference.get("summary", ""),
                        )
                    )
        print("")

    if reader is not None:
        print(_source_note(reader))
    return 0
