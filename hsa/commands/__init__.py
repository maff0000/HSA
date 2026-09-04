"""The HSA subcommand registry.

ADDING A COMMAND — the whole layout exists to make this two edits, in two
places, with no shared file to collide on:

  1. add exactly ONE new module ``hsa/commands/<name>.py``
  2. add exactly ONE line to ``COMMANDS`` below (uncomment the placeholder)

Command modules never share a file, so separate work items can add separate
commands without touching each other's code. ``hsa/cli.py`` reads this
registry and needs no change at all.

MODULE CONTRACT — every command module must define:

    NAME: str                         the subcommand name, matching its key
    HELP: str                         one-line help shown by ``hsa --help``
    add_arguments(parser) -> None     register argparse arguments
    run(args) -> int                  do the work, return an exit code

``run`` should raise the typed errors from ``hsa.errors``; ``hsa.cli`` owns
the mapping from exception type to process exit code, so commands do not
each invent their own. See ``hsa/commands/validate.py`` as the reference
implementation.

This is a plain static dict on purpose. No plugin system, no entry-point
scanning, no dynamic import by name: PID line 228 says do not build a custom
orchestration platform when standard CLI mechanisms suffice.
"""

from __future__ import annotations

from types import ModuleType

from hsa.commands import validate as _validate

# All five HSA v1 commands. Each work item contributed exactly one module
# file; the PL wired the registry centrally so parallel Engineers never
# shared this file.
from hsa.commands import boot as _boot
from hsa.commands import intake as _intake
from hsa.commands import chain as _chain
from hsa.commands import cer as _cer

#: Subcommand name -> command module. Order is the order shown in --help.
COMMANDS: dict[str, ModuleType] = {
    "validate": _validate,
    "boot": _boot,
    "intake": _intake,
    "chain": _chain,
    "cer": _cer,
}

__all__ = ["COMMANDS"]
