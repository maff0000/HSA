"""``hsa intake`` — turn a raw strategy description into a structured outcome.

Reads a raw strategy description (PID lines 101-108) and produces exactly
one of two documents:

  * a draft strategy specification, in which every discretionary term the
    analyser recognised has been resolved onto a ratified measurement basis
    and declared as a bounded parameter with visible provenance; or

  * a STRATEGY_NOT_SUFFICIENTLY_DEFINED document (PID line 120), valid
    against the frozen contract, naming exactly what is unresolved and, per
    item, what evidence or decision is needed and who owes it.

REFUSAL IS A SUCCESSFUL OUTCOME, NOT A FAILURE. PID line 39 forbids HSA
from guessing ambiguous trading rules; refusing is how it complies, and it
is exactly as correct a result as a draft. It gets its own exit code so a
caller can tell refusal apart from failure without parsing text:

    0  a draft was produced — nothing recognised as discretionary is unruled
    4  STRATEGY_NOT_SUFFICIENTLY_DEFINED — a correct, governed refusal
    1  a document HSA emitted failed contract validation (a bug, not a refusal)
    2  usage error
    3  any other deliberate HSA error, e.g. an unreadable file

Codes 0-3 are owned by ``hsa/cli.py``. Code 4 is returned directly by this
command's ``run``, which ``hsa.cli.main`` passes through unchanged; it is
not an exception mapping, because a refusal is not an exception.

The document goes to stdout (or ``--out``); the human-readable report goes
to stderr, so ``hsa intake note.txt | jq`` works untouched.
"""

from __future__ import annotations

import argparse
import json
import sys

from hsa.intake import (
    OUTCOME_NOT_SUFFICIENTLY_DEFINED,
    SOURCE_TYPES,
    intake,
    load_lexicon,
    read_request,
    write_document,
)

NAME = "intake"
HELP = "ingest a raw strategy description and resolve or refuse its ambiguity"

#: Distinct code for the refusal outcome. Not an error code: it says the run
#: succeeded AND the answer was "not sufficiently defined".
EXIT_NOT_SUFFICIENTLY_DEFINED = 4


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "path",
        metavar="<file>",
        help=(
            "raw strategy description. A .json file is read as a structured "
            "intake request; any other file is read as raw text."
        ),
    )
    parser.add_argument(
        "--source-type",
        dest="source_type",
        metavar="<type>",
        choices=SOURCE_TYPES,
        default=None,
        help=(
            "intake source, one of: %s (PID lines 102-108). Required for raw "
            "text; a structured request may declare its own."
            % ", ".join(SOURCE_TYPES)
        ),
    )
    parser.add_argument(
        "--source-reference",
        dest="source_reference",
        metavar="<ref>",
        default=None,
        help="provenance reference for the source; defaults to the file path",
    )
    parser.add_argument(
        "--intake-id",
        dest="intake_id",
        metavar="<id>",
        default=None,
        help="override the derived intake id (^[a-z][a-z0-9_]{2,63}$)",
    )
    parser.add_argument(
        "--lexicon",
        dest="lexicon",
        metavar="<file>",
        default=None,
        help=(
            "declared lexicon to scan against; defaults to the shipped "
            "hsa/intake/lexicon.json (or $HSA_INTAKE_LEXICON)"
        ),
    )
    parser.add_argument(
        "-o",
        "--out",
        dest="out",
        metavar="<file>",
        default=None,
        help="write the resulting document here instead of stdout",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="suppress the human-readable report on stderr",
    )


def _flat(text: str) -> str:
    """Collapse whitespace for the terminal report.

    Display only. The emitted document keeps the source language exactly as
    it was written, line breaks included; squashing it there would stop it
    being verbatim.
    """
    return " ".join(str(text).split())


def _report(result, out_path, stream) -> None:
    document = result.document
    print(
        "hsa intake: %s (%s)" % (result.outcome, document["intake_id"]),
        file=stream,
    )
    if result.sufficiently_defined:
        resolved = document["resolved_terms"]
        print(
            "  Outcome: draft strategy specification. %d discretionary term(s) "
            "resolved onto a ratified measurement basis." % len(resolved),
            file=stream,
        )
        for entry in resolved:
            print(
                '    - %s: "%s" (%s)'
                % (entry["term_id"], _flat(entry["source_language"]), entry["location"]),
                file=stream,
            )
            print(
                "        basis: %s" % _flat(entry["measurement_basis"]),
                file=stream,
            )
            for name in entry["declared_parameters"]:
                param = next(
                    p for p in document["parameters"] if p["name"] == name
                )
                domain = param.get("allowed_range")
                if domain:
                    span = "%s..%s" % (domain["minimum"], domain["maximum"])
                else:
                    span = ", ".join(str(v) for v in param.get("allowed_values", []))
                print(
                    "        parameter %s = %s %s (allowed %s) — default is "
                    "PROVISIONAL pending CER evidence"
                    % (name, param["default"], param["units"], span),
                    file=stream,
                )
            print(
                "        ruled by %s per %s"
                % (
                    entry["resolution"]["ratified_by"],
                    entry["resolution"]["ruling_document"],
                ),
                file=stream,
            )
        advisory = document.get("advisory_items", [])
        if advisory:
            print(
                "  %d advisory item(s) carried with the draft, not blocking:"
                % len(advisory),
                file=stream,
            )
            for item in advisory:
                print(
                    '    - %s: "%s"' % (item["item_id"], _flat(item["source_language"])),
                    file=stream,
                )
        print(
            "  A clean scan is not proof the description is fully specified; "
            "see docs/AMBIGUITY-POLICY.md.",
            file=stream,
        )
    else:
        print(
            "  This is a CORRECT, SUCCESSFUL HSA outcome, not a failure. HSA "
            "must not guess ambiguous trading rules (PID line 39), so it "
            "refuses precisely and says what it needs (PID line 120).",
            file=stream,
        )
        blocking = result.blocking_items
        advisory = result.advisory_items
        print(
            "  %d blocking %s, %d advisory:"
            % (
                len(blocking),
                "ambiguity" if len(blocking) == 1 else "ambiguities",
                len(advisory),
            ),
            file=stream,
        )
        for item in blocking + advisory:
            print(
                '    - [%s] %s: "%s" (%s)'
                % (
                    item["severity"],
                    item["item_id"],
                    _flat(item["source_language"]),
                    item["location"],
                ),
                file=stream,
            )
            resolution = item["resolution_needed"]
            print(
                "        needs %s from %s: %s"
                % (
                    resolution["kind"],
                    resolution["responsible"],
                    _flat(resolution["description"]),
                ),
                file=stream,
            )
            print(
                "        blocks: %s" % ", ".join(item["blocks"]),
                file=stream,
            )
        print(
            "  Exit code %d means refusal. Exit 1 means a document failed "
            "contract validation; exit 3 means an error."
            % EXIT_NOT_SUFFICIENTLY_DEFINED,
            file=stream,
        )
    if out_path is not None:
        print("  Written to %s" % out_path, file=stream)


def run(args: argparse.Namespace) -> int:
    request = read_request(
        args.path,
        source_type=args.source_type,
        source_reference=args.source_reference,
        intake_id=args.intake_id,
    )
    lexicon = load_lexicon(args.lexicon) if args.lexicon else load_lexicon()
    result = intake(request, lexicon=lexicon)

    if args.out:
        written = write_document(result.document, args.out)
    else:
        written = None
        json.dump(result.document, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")

    if not args.quiet:
        _report(result, written, sys.stderr)

    if result.outcome == OUTCOME_NOT_SUFFICIENTLY_DEFINED:
        return EXIT_NOT_SUFFICIENTLY_DEFINED
    return 0
