"""``hsa validate`` — validate a JSON document against its HSA contract.

Two kinds of validation run, in this order, and by default both must pass:

  1. STRUCTURAL, via ``hsa.contracts`` — the document is a valid instance of
     its declared contract schema.
  2. SEMANTIC, via ``hsa.semantics`` — the cross-field rules JSON Schema
     cannot express, for the kinds that have them (``chain`` and
     ``strategy_package``): unique input handles, contiguous SEQUENCE
     ordering, an optional input that is never the sole cause of a match, a
     CONTEXT that genuinely sits above its TRIGGER and shares its chain with
     nothing but a TRIGGER, every referenced atomic resolving in the
     catalogue at the exact version pinned, and — for a package — that the
     package and its embedded chain say the same thing, that every atomic the
     chain names is embedded, and that HERMES needs are carried up.

WHY SEMANTICS ARE ON BY DEFAULT. They were previously reachable only through
``hsa chain``, and only for a standalone ``chain`` document. That left the
``strategy_package`` — the one artifact FORGE implements from (PID line 148)
— with no single-command full validation, and ``hsa validate`` reported a
package with its CONTEXT and TRIGGER timeframes swapped, a strategically
inverted document, as ``valid strategy_package`` with exit 0. A validator
whose default mode passes that is not a validator. ``--structural-only``
remains available for the narrower question of schema conformance, and says
plainly on success that the semantic half did not run.

DEGRADING HONESTLY. Reference resolution needs the atomic strategy catalogue.
If it cannot be loaded, this command fails loudly (exit 3) rather than
quietly passing a document it did not finish checking. ``--no-catalogue``
runs the checks that do not need it and names, on stderr, the check that
therefore did not run. A check that could not run is never reported as a
check that passed.

Reference implementation of the command module contract described in
``hsa/commands/__init__.py``. It raises the typed errors from ``hsa.errors``;
``hsa.cli`` owns the mapping from exception type to process exit code.
"""

from __future__ import annotations

import argparse
import sys

from hsa.contracts import DISCRIMINATOR, KINDS, read_json_file, validate_document
from hsa.errors import SchemaLoadError
from hsa.semantics import (
    CATALOGUE_DEPENDENT_CHECKS,
    CATALOGUE_DIR_ENV,
    SEMANTIC_KINDS,
    Catalogue,
    check_document,
    raise_if_invalid,
)

NAME = "validate"
HELP = "validate a JSON document against its HSA contract, structurally and semantically"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "path",
        metavar="<file>",
        help="path to the JSON document to validate",
    )
    parser.add_argument(
        "--schema",
        dest="kind",
        metavar="<name>",
        choices=KINDS,
        default=None,
        help=(
            "contract to validate against, one of: %s. Defaults to the %s "
            "declared by the document itself."
            % (", ".join(KINDS), DISCRIMINATOR)
        ),
    )
    parser.add_argument(
        "--structural-only",
        dest="structural_only",
        action="store_true",
        help=(
            "check schema conformance only and skip the semantic checks. The "
            "success line says the semantic half did not run."
        ),
    )
    parser.add_argument(
        "--catalogue",
        dest="catalogue",
        metavar="<dir>",
        default=None,
        help=(
            "atomic strategy catalogue directory used to resolve a chain's "
            "inputs. Defaults to catalogue/atomic in the checkout, or the %s "
            "environment variable when it is set." % CATALOGUE_DIR_ENV
        ),
    )
    parser.add_argument(
        "--no-catalogue",
        dest="no_catalogue",
        action="store_true",
        help=(
            "run the semantic checks that do not need the catalogue, and "
            "report which check was therefore not run"
        ),
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="suppress the success line; errors and skipped checks are still reported",
    )


def _load_catalogue(directory: str | None, path: str) -> Catalogue:
    """Load the catalogue, or fail loudly saying why validation cannot finish.

    Never returns an empty catalogue as a stand-in for a missing one: that
    would turn "I could not check the references" into "every reference is
    wrong", which is a different and equally dishonest answer.
    """
    try:
        return Catalogue.from_directory(directory)
    except SchemaLoadError as exc:
        raise SchemaLoadError(
            "semantic validation of %s needs the atomic strategy catalogue and "
            "it could not be loaded: %s. Pass --catalogue <dir>, set %s, or "
            "pass --no-catalogue to run the checks that do not need it (which "
            "leaves %s unrun). Semantic validation is not silently skipped."
            % (path, exc, CATALOGUE_DIR_ENV, ", ".join(CATALOGUE_DEPENDENT_CHECKS))
        ) from exc


def _note(text: str) -> None:
    """Report a check that did not run.

    Goes to stderr, and is not suppressed by ``--quiet``: quiet suppresses the
    success line, and "this check did not run" is a warning, not a success.
    """
    print("hsa validate: %s" % text, file=sys.stderr)


def run(args: argparse.Namespace) -> int:
    document = read_json_file(args.path)
    kind = validate_document(document, kind=args.kind, source=args.path)

    if args.structural_only:
        _note(
            "--structural-only: the semantic checks did not run for %s; drop "
            "the flag to run them" % args.path
        )
        if not args.quiet:
            print(
                "%s: valid %s (structural only; semantic checks did not run)"
                % (args.path, kind)
            )
        return 0

    if kind not in SEMANTIC_KINDS:
        if not args.quiet:
            print(
                "%s: valid %s (no semantic checks are defined for this kind; "
                "its schema is the whole contract)" % (args.path, kind)
            )
        return 0

    catalogue: Catalogue | None = None
    if args.no_catalogue:
        _note(
            "--no-catalogue: %s did not run for %s"
            % (", ".join(CATALOGUE_DEPENDENT_CHECKS), args.path)
        )
    else:
        catalogue = _load_catalogue(args.catalogue, args.path)

    findings = check_document(document, kind=kind, catalogue=catalogue)
    raise_if_invalid(findings, kind, source=args.path)

    if args.quiet:
        return 0

    if catalogue is None:
        # Never claim the semantic half outright when part of it was skipped:
        # the success line is what most callers read, and "semantically valid"
        # would report an unrun check as a check that passed.
        print(
            "%s: valid %s, structurally and semantically apart from %s "
            "(catalogue resolution skipped)"
            % (args.path, kind, ", ".join(CATALOGUE_DEPENDENT_CHECKS))
        )
    else:
        print(
            "%s: valid %s, structurally and semantically (atomic references "
            "resolved against %s)" % (args.path, kind, catalogue.source)
        )
    return 0
