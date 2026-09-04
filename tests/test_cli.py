"""Tests for the ``hsa`` CLI skeleton and the ``validate`` command."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from hsa.cli import (
    EXIT_ERROR,
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    build_parser,
    main,
)
from hsa.commands import COMMANDS
from hsa.contracts import KINDS

REPO_ROOT = Path(__file__).resolve().parent.parent


# --- the registry layout -----------------------------------------------------


def test_every_registered_command_satisfies_the_module_contract():
    """Adding a command must stay: one new file, one new registry line."""
    for name, module in COMMANDS.items():
        assert module.NAME == name
        assert isinstance(module.HELP, str) and module.HELP
        assert callable(module.add_arguments)
        assert callable(module.run)


def test_command_modules_do_not_share_a_file():
    """Parallel work items each own one module file, so they cannot collide."""
    files = [module.__file__ for module in COMMANDS.values()]
    assert len(files) == len(set(files))
    for name, module in COMMANDS.items():
        assert Path(module.__file__).name == name + ".py"


def test_validate_is_registered():
    assert "validate" in COMMANDS


def test_all_five_hsa_v1_commands_are_registered():
    """The placeholder contract is fulfilled: every v1 command is wired.

    This replaced an earlier test asserting the placeholder lines were still
    commented out. That assertion was correct only while the work items were
    outstanding; once the PL wired the registry, testing for the absence
    marker would have been testing that the work had NOT been done.
    """
    assert set(COMMANDS) == {"validate", "boot", "intake", "chain", "cer"}


def test_every_registered_command_is_reachable_from_the_cli():
    """A registered module is not enough — argparse must expose it."""
    parser = build_parser()
    subparsers = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(subparsers) == 1
    choices = subparsers[0].choices
    assert set(choices) == set(COMMANDS)
    for name, subparser in choices.items():
        assert subparser.get_default("_run") is COMMANDS[name].run


def test_cli_picks_up_any_module_satisfying_the_registry_contract(
    monkeypatch, capsys
):
    """Proves the extension point: one module plus one registry line.

    Four work items each add exactly one command module. This test adds one
    at runtime without touching hsa/cli.py, which is the whole claim.
    """
    module = types.ModuleType("hsa.commands.smoke")
    module.NAME = "smoke"
    module.HELP = "throwaway command proving the registry extension point"

    def add_arguments(parser):
        parser.add_argument("--value", default="ok")

    def run(args):
        print("smoke:%s" % args.value)
        return 0

    module.add_arguments = add_arguments
    module.run = run

    monkeypatch.setitem(COMMANDS, "smoke", module)
    assert main(["smoke", "--value", "wired"]) == EXIT_OK
    assert "smoke:wired" in capsys.readouterr().out


# --- exit codes --------------------------------------------------------------


def test_valid_document_exits_zero(valid_path, capsys):
    code = main(["validate", str(valid_path("strategy_package"))])
    assert code == EXIT_OK
    assert "valid strategy_package" in capsys.readouterr().out


def test_quiet_suppresses_the_success_line(valid_path, capsys):
    code = main(["validate", "--quiet", str(valid_path("chain"))])
    assert code == EXIT_OK
    assert capsys.readouterr().out == ""


def test_invalid_document_exits_one_with_the_failing_path(invalid_path, capsys):
    code = main(["validate", str(invalid_path("atomic_strategy"))])
    assert code == EXIT_INVALID
    err = capsys.readouterr().err
    assert "$.parameters[0]" in err
    assert "units" in err


def test_chain_of_chain_document_exits_one(invalid_path, capsys):
    code = main(["validate", str(invalid_path("chain_of_chain"))])
    assert code == EXIT_INVALID
    assert "$.inputs[0]" in capsys.readouterr().err


def test_explicit_schema_flag_is_honoured(valid_path, capsys):
    code = main(
        ["validate", "--schema", "atomic_strategy", str(valid_path("chain"))]
    )
    assert code == EXIT_INVALID
    assert "atomic_strategy" in capsys.readouterr().err


def test_missing_file_exits_three(tmp_path, capsys):
    code = main(["validate", str(tmp_path / "absent.json")])
    assert code == EXIT_ERROR
    assert "no such file" in capsys.readouterr().err


def test_malformed_json_exits_three(tmp_path, capsys):
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    code = main(["validate", str(broken)])
    assert code == EXIT_ERROR
    assert "not valid JSON" in capsys.readouterr().err


def test_document_without_a_discriminator_exits_three(tmp_path, capsys):
    document = tmp_path / "anonymous.json"
    document.write_text(json.dumps({"title": "no kind"}), encoding="utf-8")
    code = main(["validate", str(document)])
    assert code == EXIT_ERROR
    assert "$hsa_kind" in capsys.readouterr().err


def test_no_subcommand_exits_usage(capsys):
    assert main([]) == EXIT_USAGE
    assert "usage: hsa" in capsys.readouterr().err


def test_unknown_subcommand_exits_usage():
    with pytest.raises(SystemExit) as caught:
        main(["nope"])
    assert caught.value.code == EXIT_USAGE


def test_unknown_schema_name_exits_usage(valid_path):
    with pytest.raises(SystemExit) as caught:
        main(["validate", "--schema", "backtest", str(valid_path("chain"))])
    assert caught.value.code == EXIT_USAGE


def test_schema_flag_offers_exactly_the_known_kinds(capsys):
    with pytest.raises(SystemExit):
        main(["validate", "--help"])
    out = capsys.readouterr().out
    for kind in KINDS:
        assert kind in out


# --- end to end through a real process ---------------------------------------


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "hsa.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_process_exit_code_zero_for_a_valid_document():
    result = _run("validate", "tests/fixtures/valid/atomic_strategy.json")
    assert result.returncode == 0, result.stderr
    assert "valid atomic_strategy" in result.stdout


def test_process_exit_code_one_for_an_invalid_document():
    result = _run("validate", "tests/fixtures/invalid/chain.json")
    assert result.returncode == 1
    assert "$.primitive" in result.stderr
