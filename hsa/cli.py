"""``hsa`` command line entrypoint.

A plain ``argparse`` CLI. Subcommands come from the static registry in
``hsa.commands``; this module discovers nothing dynamically and holds no
per-command knowledge, so adding a command never edits this file.

Exit codes are owned here, in one place, so every command reports failure
the same way:

    0  success
    1  the document was read but failed contract validation
    2  usage error (argparse)
    3  any other deliberate HSA error, e.g. unreadable file, unknown kind
    4  STRATEGY_NOT_SUFFICIENTLY_DEFINED (hsa intake)

Code 4 is not a failure. It is HSA correctly refusing to guess an
ambiguous trading rule (PID lines 39, 120), and a caller must be able to
tell that refusal apart from an error. Commands return it directly from
``run``; ``main`` passes an int through unchanged.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from hsa import __version__
from hsa.commands import COMMANDS
from hsa.errors import DocumentInvalidError, HSAError

__all__ = ["main", "build_parser", "EXIT_OK", "EXIT_INVALID", "EXIT_USAGE", "EXIT_ERROR"]

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_ERROR = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hsa",
        description=(
            "HELIOS Strategy Architect: governed strategy-engineering "
            "contracts and tooling."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version="hsa %s" % __version__,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    for name, module in COMMANDS.items():
        subparser = subparsers.add_parser(
            name,
            help=module.HELP,
            description=module.__doc__,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        module.add_arguments(subparser)
        subparser.set_defaults(_run=module.run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    run = getattr(args, "_run", None)
    if run is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE

    try:
        return run(args)
    except DocumentInvalidError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    except HSAError as exc:
        print("hsa: %s" % exc, file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
