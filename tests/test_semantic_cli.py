"""The semantic layer must be reachable from the command line.

THE DEFECT THIS FILE EXISTS FOR. ``hsa validate`` used to be structural only.
The entire ``hsa.semantics`` layer was reachable from the CLI through exactly
one door — ``hsa chain`` — and that door refused a ``strategy_package``
outright. So the one artifact the PID says FORGE implements from (line 148:
*HSA must produce enough precision that FORGE implements the specification
rather than inventing trading logic*) was the one artifact with no
single-command full validation.

Taking the shipped, governed ``gold_context_breakout`` package and swapping
its CONTEXT and TRIGGER timeframes — putting the 4H *context* on 5M and the 5M
*trigger* on 4H, which is a strategically inverted strategy and not a typo —
produced::

    pkg.json: valid strategy_package
    EXIT=0

while ``hsa.semantics.check_package`` on the identical file returned three
findings. Two acceptance Engineers found this independently and the PL
reproduced it directly. ``test_the_pl_reproduction_now_fails_from_the_cli``
below is that exact reproduction, kept as a regression.

WHAT IS PINNED HERE, deliberately, because each is a way the gap could
silently reopen:

  * a semantically inverted package fails from the CLI, at exit 1;
  * a clean governed package still passes;
  * the mutation is *purely* semantic — ``--structural-only`` still passes it,
    so the failure above is the semantic layer running and nothing else;
  * a check that cannot run is never reported as a check that passed;
  * exit codes stay the four ``hsa.cli`` already owns — no new code invented.

The governed packages under ``strategies/`` are read and deep-copied, never
written. Mutants live in ``tmp_path``.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from hsa.cli import EXIT_ERROR, EXIT_INVALID, EXIT_OK, main
from hsa.commands import validate as validate_command
from hsa.contracts import validate_document
from hsa.semantics import CATALOGUE_DEPENDENT_CHECKS, SEMANTIC_KINDS, check_package

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOGUE_DIR = REPO_ROOT / "catalogue" / "atomic"
GOVERNED_PACKAGE = REPO_ROOT / "strategies" / "gold_context_breakout" / "1.0.0" / "package.json"


def _load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write(tmp_path: Path, name: str, document) -> str:
    target = tmp_path / name
    target.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return str(target)


@pytest.fixture
def governed_package():
    """The shipped, promoted package — deep-copied so a test may break it."""
    return copy.deepcopy(_load(GOVERNED_PACKAGE))


def _swap_context_and_trigger_timeframes(package) -> None:
    """The PL's mutation, exactly: put the context on 5M and the trigger on 4H.

    The role *model* is left alone, which is what the PL did, so this also
    trips the role-mapping check. That is the reproduction as reported.
    """
    for item in package["chain"]["inputs"]:
        if item["timeframe_role"] == "CONTEXT":
            item["timeframe"] = "5M"
        elif item["timeframe_role"] == "TRIGGER":
            item["timeframe"] = "4H"


# --- the regression -----------------------------------------------------------


def test_the_pl_reproduction_now_fails_from_the_cli(
    tmp_path, governed_package, capsys
):
    """The exact defect: inverted package, one command, non-zero exit."""
    _swap_context_and_trigger_timeframes(governed_package)
    path = _write(tmp_path, "pl_mutated_pkg.json", governed_package)

    assert main(["validate", path]) == EXIT_INVALID

    err = capsys.readouterr().err
    assert "is not a valid strategy_package" in err
    assert "$.chain.inputs[0].timeframe" in err
    # The message the PL saw from check_package, now reaching the terminal.
    assert "CONTEXT input 'htf_cross_context' runs on 5M" in err
    assert "lower timeframe than TRIGGER input" in err


def test_the_pl_reproduction_is_purely_semantic(tmp_path, governed_package):
    """Proves the failure above is the semantic layer and not a schema break.

    If the inverted document were structurally invalid, this repair would be
    unnecessary and the regression above would prove nothing.
    """
    _swap_context_and_trigger_timeframes(governed_package)
    assert validate_document(governed_package) == "strategy_package"

    path = _write(tmp_path, "pl_mutated_pkg.json", governed_package)
    assert main(["validate", "--structural-only", path]) == EXIT_OK


def test_the_cli_reports_every_finding_check_package_reports(
    tmp_path, governed_package, capsys
):
    """No finding is dropped between the library and the terminal."""
    _swap_context_and_trigger_timeframes(governed_package)
    path = _write(tmp_path, "pl_mutated_pkg.json", governed_package)

    from hsa.semantics import Catalogue

    expected = check_package(
        governed_package, catalogue=Catalogue.from_directory(CATALOGUE_DIR)
    )
    assert len(expected) == 3

    assert main(["validate", path]) == EXIT_INVALID
    err = capsys.readouterr().err
    assert "(3 problems)" in err
    for finding in expected:
        assert finding.message in err


def test_a_self_consistent_but_inverted_package_still_fails(
    tmp_path, governed_package, capsys
):
    """The nastier case: the document agrees with itself and is still nonsense.

    Swapping the role model too silences the role-mapping check, leaving only
    the one finding that says the strategy is inverted. A validator that
    passed this would be passing a coherent specification of a strategy that
    cannot mean anything.
    """
    _swap_context_and_trigger_timeframes(governed_package)
    inverted_roles = {"CONTEXT": "5M", "TRIGGER": "4H"}
    governed_package["timeframe_roles"] = dict(inverted_roles)
    governed_package["chain"]["timeframe_roles"] = dict(inverted_roles)
    path = _write(tmp_path, "consistently_inverted.json", governed_package)

    assert validate_document(governed_package) == "strategy_package"
    assert main(["validate", path]) == EXIT_INVALID

    err = capsys.readouterr().err
    assert "(1 problem)" in err
    assert "must be strictly the higher of the two" in err


def test_the_governed_packages_still_pass(capsys):
    """The repair must not fail the strategies HSA actually ships."""
    for package in sorted((REPO_ROOT / "strategies").glob("*/*/package.json")):
        assert main(["validate", str(package)]) == EXIT_OK, package
        out = capsys.readouterr().out
        assert "valid strategy_package, structurally and semantically" in out


# --- semantics are the default ------------------------------------------------


def test_semantics_run_by_default_with_no_flag_at_all(tmp_path, governed_package):
    """The whole point: the default mode is the correct mode.

    A validator whose default silently passes an inverted strategy trains its
    caller to trust a check that is not happening. Opt-in semantics would have
    left this gap open for everyone who did not know the flag existed — which
    is what happened to two acceptance Engineers independently.
    """
    _swap_context_and_trigger_timeframes(governed_package)
    path = _write(tmp_path, "no_flags.json", governed_package)
    assert main(["validate", path]) == EXIT_INVALID


@pytest.mark.parametrize("kind", SEMANTIC_KINDS)
def test_every_semantic_kind_is_checked_by_default(tmp_path, valid_doc, kind):
    """Both kinds with semantic rules must reach them from the CLI."""
    document = copy.deepcopy(valid_doc(kind))
    chain = document["chain"] if kind == "strategy_package" else document
    chain["inputs"][1]["input_id"] = chain["inputs"][0]["input_id"]
    path = _write(tmp_path, "duplicate_handles.json", document)

    assert validate_document(document) == kind
    assert main(["validate", path]) == EXIT_INVALID


def test_structural_only_is_the_escape_hatch(valid_path, capsys):
    assert main(["validate", "--structural-only", str(valid_path("chain"))]) == EXIT_OK
    captured = capsys.readouterr()
    assert "valid chain (structural only; semantic checks did not run)" in captured.out
    assert "the semantic checks did not run" in captured.err


def test_structural_only_says_so_even_when_quiet(valid_path, capsys):
    """--quiet drops the success line. It must not drop "this did not run"."""
    assert (
        main(["validate", "--structural-only", "--quiet", str(valid_path("chain"))])
        == EXIT_OK
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "the semantic checks did not run" in captured.err


def test_a_kind_with_no_semantic_rules_says_so_rather_than_implying_a_check(
    valid_path, capsys
):
    """Silence would read as "semantically checked". It was not; there is
    nothing to check, and that is a different statement."""
    assert main(["validate", str(valid_path("atomic_strategy"))]) == EXIT_OK
    out = capsys.readouterr().out
    assert "valid atomic_strategy" in out
    assert "no semantic checks are defined for this kind" in out


def test_semantic_failure_uses_the_existing_invalid_exit_code(
    tmp_path, governed_package
):
    """Exit 1 is "read but failed validation". No new code is invented."""
    _swap_context_and_trigger_timeframes(governed_package)
    path = _write(tmp_path, "inverted.json", governed_package)
    assert main(["validate", path]) == EXIT_INVALID == 1


def test_structural_failure_still_beats_semantic_failure(invalid_path, capsys):
    """Structural first, semantic second: a schema break reports as a schema
    break, not as a pile of confusing semantic noise."""
    assert main(["validate", str(invalid_path("chain"))]) == EXIT_INVALID
    err = capsys.readouterr().err
    assert "$.primitive" in err
    assert "semantic/" not in err


# --- degrading honestly -------------------------------------------------------


def test_missing_catalogue_fails_loudly_rather_than_passing(
    monkeypatch, tmp_path, valid_path, capsys
):
    """The exact failure mode this repair exists to remove."""
    monkeypatch.setenv("HSA_CATALOGUE_DIR", str(tmp_path / "does_not_exist"))
    code = main(["validate", str(valid_path("strategy_package"))])

    assert code == EXIT_ERROR
    assert code != EXIT_OK
    err = capsys.readouterr().err
    assert "needs the atomic strategy catalogue" in err
    assert "not silently skipped" in err
    for check in CATALOGUE_DEPENDENT_CHECKS:
        assert check in err


def test_an_explicit_catalogue_directory_that_is_absent_also_fails_loudly(
    tmp_path, valid_path, capsys
):
    code = main(
        [
            "validate",
            "--catalogue",
            str(tmp_path / "nope"),
            str(valid_path("strategy_package")),
        ]
    )
    assert code == EXIT_ERROR
    assert "not silently skipped" in capsys.readouterr().err


def test_no_catalogue_names_the_check_it_did_not_run(tmp_path, valid_doc, capsys):
    """Running without the catalogue is allowed. Pretending it was complete
    is not: the skipped check is named, on stderr, by id."""
    document = copy.deepcopy(valid_doc("strategy_package"))
    document["chain"]["inputs"][0]["strategy_id"] = "no_such_strategy"
    document["atomic_strategies"][0]["strategy_id"] = "no_such_strategy"
    path = _write(tmp_path, "unresolvable.json", document)

    assert main(["validate", "--no-catalogue", path]) == EXIT_OK
    captured = capsys.readouterr()
    assert "catalogue resolution skipped" in captured.out
    for check in CATALOGUE_DEPENDENT_CHECKS:
        assert check in captured.err
    assert "did not run" in captured.err


def test_no_catalogue_still_runs_the_checks_that_do_not_need_one(
    tmp_path, governed_package
):
    """Degrading is not the same as giving up: the inverted strategy is still
    caught without a catalogue, because that check never needed one."""
    _swap_context_and_trigger_timeframes(governed_package)
    path = _write(tmp_path, "inverted.json", governed_package)
    assert main(["validate", "--no-catalogue", path]) == EXIT_INVALID


def test_no_catalogue_note_survives_quiet(valid_path, capsys):
    assert (
        main(["validate", "--no-catalogue", "--quiet", str(valid_path("chain"))])
        == EXIT_OK
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "did not run" in captured.err


def test_an_explicit_catalogue_directory_is_honoured(valid_path, capsys):
    assert (
        main(
            [
                "validate",
                "--catalogue",
                str(CATALOGUE_DIR),
                str(valid_path("strategy_package")),
            ]
        )
        == EXIT_OK
    )
    assert str(CATALOGUE_DIR) in capsys.readouterr().out


def test_an_empty_catalogue_reports_unresolved_references_not_a_pass(
    tmp_path, valid_path, capsys
):
    """An empty directory is a real catalogue holding nothing, so references
    genuinely do not resolve. That is a finding, not a skip."""
    empty = tmp_path / "empty_catalogue"
    empty.mkdir()
    code = main(
        ["validate", "--catalogue", str(empty), str(valid_path("strategy_package"))]
    )
    assert code == EXIT_INVALID
    assert "no catalogue entry for strategy_id" in capsys.readouterr().err


# --- the command surface ------------------------------------------------------


def test_validate_still_satisfies_the_module_contract():
    assert validate_command.NAME == "validate"
    assert isinstance(validate_command.HELP, str) and validate_command.HELP
    assert callable(validate_command.add_arguments)
    assert callable(validate_command.run)


def test_the_new_flags_are_documented_in_help(capsys):
    with pytest.raises(SystemExit):
        main(["validate", "--help"])
    out = capsys.readouterr().out
    for flag in ("--structural-only", "--catalogue", "--no-catalogue"):
        assert flag in out


def test_no_new_command_was_added():
    """The gap is closed by extending a command, not by growing the CLI."""
    from hsa.commands import COMMANDS

    assert set(COMMANDS) == {"validate", "boot", "intake", "chain", "cer"}


# --- end to end through a real process ----------------------------------------


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "hsa.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_process_exit_code_one_for_a_semantically_inverted_package(
    tmp_path, governed_package
):
    """Not simulated: the shipped command, a real process, a real exit code."""
    _swap_context_and_trigger_timeframes(governed_package)
    path = _write(tmp_path, "pl_mutated_pkg.json", governed_package)

    result = _run("validate", path)
    assert result.returncode == 1, result.stdout
    assert "lower timeframe than TRIGGER input" in result.stderr


def test_process_exit_code_zero_for_the_governed_package():
    result = _run("validate", str(GOVERNED_PACKAGE.relative_to(REPO_ROOT)))
    assert result.returncode == 0, result.stderr
    assert "valid strategy_package, structurally and semantically" in result.stdout


def test_process_hsa_chain_accepts_the_governed_package():
    result = _run("chain", str(GOVERNED_PACKAGE.relative_to(REPO_ROOT)))
    assert result.returncode == 0, result.stderr
    assert "its embedded chain is valid" in result.stdout
    assert "CONTEXT_TRIGGER(" in result.stdout
    assert "were NOT run here" in result.stderr


def test_process_hsa_chain_and_hsa_validate_agree_on_a_chain_document():
    """Two doors onto one semantic layer must not give two answers."""
    fixture = "tests/fixtures/valid/chain.json"
    assert _run("validate", fixture).returncode == _run("chain", fixture).returncode == 0
