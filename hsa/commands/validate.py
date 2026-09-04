"""``hsa validate`` — validate a JSON document against its HSA contract.

Reference implementation of the command module contract described in
``hsa/commands/__init__.py``.
"""

from __future__ import annotations

import argparse

from hsa.contracts import DISCRIMINATOR, KINDS, read_json_file, validate_document

NAME = "validate"
HELP = "validate a JSON document against its HSA contract schema"


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
        "-q",
        "--quiet",
        action="store_true",
        help="suppress the success line; errors are still reported",
    )


def run(args: argparse.Namespace) -> int:
    document = read_json_file(args.path)
    kind = validate_document(document, kind=args.kind, source=args.path)
    if not args.quiet:
        print("%s: valid %s" % (args.path, kind))
    return 0
