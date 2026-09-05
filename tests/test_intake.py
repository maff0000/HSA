"""The intake pipeline and the ``hsa intake`` command — PID lines 99-120.

Acceptance criterion 2 (PID line 251) is "ingest a realistic raw strategy
description". These tests drive the real fixtures in
``tests/fixtures/intake`` end to end, through the same code path the CLI
uses, and check the two structured outcomes rather than any prose.

The boundary between those outcomes is tested separately in
``tests/test_ambiguity.py``; this file is about the mechanics — reading a
request, building documents, and reporting the result.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from hsa.cli import EXIT_ERROR, EXIT_OK, main
from hsa.commands import COMMANDS
from hsa.commands import intake as intake_command
from hsa.contracts import validate_document
from hsa.errors import HSAError, MissingDiscriminatorError
from hsa.intake import (
    DRAFT_DISCRIMINATOR,
    DRAFT_MARKER,
    OUTCOME_DRAFT,
    OUTCOME_NOT_SUFFICIENTLY_DEFINED,
    SOURCE_TYPES,
    build_request,
    intake,
    load_lexicon,
    read_request,
    utc_now,
)
from hsa.intake.documents import NOT_YET_SPECIFIED
from hsa.intake.errors import IntakeError, IntakeRequestError
from hsa.intake.request import derive_intake_id

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "intake"
STAMP = "2026-09-04T00:00:00Z"


@pytest.fixture(scope="module")
def lexicon():
    return load_lexicon()


@pytest.fixture
def registered(monkeypatch):
    """Wire ``intake`` into the registry for the duration of a test.

    The PL wires ``hsa/commands/__init__.py`` centrally, so this work item
    does not edit it. Injecting the module at runtime proves the command
    satisfies the registry contract without touching a shared file — the
    same technique ``tests/test_cli.py`` uses for its throwaway command.
    """
    monkeypatch.setitem(COMMANDS, "intake", intake_command)
    return intake_command


def _result(name: str, source_type: str | None = None, lex=None):
    request = read_request(FIXTURES / name, source_type=source_type)
    return intake(request, lexicon=lex, generated_at_utc=STAMP)


# --- the command module contract ---------------------------------------------


def test_intake_satisfies_the_command_module_contract():
    """``hsa/commands/__init__.py`` documents exactly this shape."""
    assert intake_command.NAME == "intake"
    assert isinstance(intake_command.HELP, str) and intake_command.HELP
    assert callable(intake_command.add_arguments)
    assert callable(intake_command.run)
    assert Path(intake_command.__file__).name == "intake.py"


def test_intake_does_not_edit_the_shared_registry():
    """This work item added a module; the PL added the registry line.

    Asserted the line was still commented while W2C was outstanding; now
    asserts the PL wired it, which is the same contract on the far side of
    integration.
    """
    registry = Path(intake_command.__file__).parent / "__init__.py"
    text = registry.read_text(encoding="utf-8")
    assert '"intake": _intake,' in text


# --- reading a raw strategy description --------------------------------------


def test_every_pid_intake_source_is_accepted():
    """PID lines 102-108 name six sources; all six must be usable."""
    assert set(SOURCE_TYPES) == {
        "MATT_OBSERVATION",
        "TRADER_EXPLANATION",
        "REPORT_OR_BOOK",
        "VIDEO_DERIVED",
        "EXTERNAL_STRATEGY",
        "EXISTING_SPECIFICATION",
    }
    for source_type in SOURCE_TYPES:
        request = build_request("a large wick appears", source_type, "unit test")
        assert request["source_type"] == source_type


def test_raw_text_requires_an_explicit_source_type():
    """Provenance is mandatory and is never inferred from the text."""
    with pytest.raises(IntakeRequestError, match="--source-type is required"):
        read_request(FIXTURES / "example_b_rejection_wick_sequence.txt")


def test_a_structured_request_carries_its_own_provenance():
    request = read_request(FIXTURES / "existing_specification.json")
    assert request["source_type"] == "EXISTING_SPECIFICATION"
    assert request["intake_id"] == "intake_legacy_wick_reversal"
    assert request["source_reference"] == "HELIOS legacy spec sheet v0.3, section 2"
    assert request["notes"]


def test_an_empty_description_is_an_error_not_a_refusal():
    """There is nothing to be ambiguous about, so refusing would be a lie."""
    with pytest.raises(IntakeRequestError, match="nothing to analyse"):
        read_request(FIXTURES / "empty.txt", source_type="MATT_OBSERVATION")


def test_a_missing_file_raises_a_typed_error(tmp_path):
    with pytest.raises(IntakeRequestError, match="no such file"):
        read_request(tmp_path / "absent.txt", source_type="MATT_OBSERVATION")


def test_a_bad_source_type_is_rejected():
    with pytest.raises(IntakeRequestError, match="unknown source_type"):
        build_request("text", "GUESSED_FROM_VIBES", "unit test")


def test_intake_ids_are_deterministic_and_contract_shaped():
    """A refusal and the resubmission answering it must be tie-able."""
    first = derive_intake_id("notes/london_wick.txt", "same text")
    second = derive_intake_id("notes/london_wick.txt", "same text")
    assert first == second
    assert derive_intake_id("notes/london_wick.txt", "other text") != first
    import re

    assert re.match(r"^[a-z][a-z0-9_]{2,63}$", first)


def test_a_malformed_intake_id_is_refused():
    with pytest.raises(IntakeRequestError, match="does not match the contract"):
        build_request("a large wick", "MATT_OBSERVATION", "unit test", intake_id="No")


# --- outcome one: the draft --------------------------------------------------


def test_a_well_specified_description_produces_a_draft():
    result = _result("well_specified_wick_sequence.txt", "MATT_OBSERVATION")
    assert result.outcome == OUTCOME_DRAFT
    assert result.sufficiently_defined
    assert result.document["resolved_terms"] == []
    assert result.document["advisory_items"] == []


def test_a_draft_records_the_source_verbatim_and_its_provenance():
    result = _result("example_b_rejection_wick_sequence.txt", "TRADER_EXPLANATION")
    document = result.document
    assert document["raw_description"] == result.request["text"]
    provenance = document["provenance"]
    assert provenance["source_type"] == "TRADER_EXPLANATION"
    assert provenance["source_reference"].endswith(
        "example_b_rejection_wick_sequence.txt"
    )
    assert provenance["ingested_at_utc"].endswith("Z")


def test_a_draft_is_deliberately_not_a_governed_contract_kind():
    """It declares $hsa_intake, not $hsa_kind, and says why.

    Intake cannot produce a strategy_package without inventing atomic
    decomposition, a chain and test cases. Emitting something that looked
    like a governed package would be worse than emitting a draft.
    """
    result = _result("example_b_rejection_wick_sequence.txt", "TRADER_EXPLANATION")
    document = result.document
    assert document[DRAFT_DISCRIMINATOR] == DRAFT_MARKER
    assert "$hsa_kind" not in document
    with pytest.raises(MissingDiscriminatorError):
        validate_document(document)


def test_a_draft_names_every_package_field_it_did_not_supply():
    """A missing section must read as an obligation, not an oversight."""
    result = _result("example_b_rejection_wick_sequence.txt", "TRADER_EXPLANATION")
    outstanding = {
        entry["field"] for entry in result.document["not_yet_specified"]
    }
    assert {
        "atomic_strategies",
        "chain",
        "timeframe_roles",
        "deterministic_test_cases",
        "acceptance_criteria",
        "cer_references",
    } <= outstanding
    for entry in result.document["not_yet_specified"]:
        assert entry["obligation"].strip()


def test_draft_parameters_drop_into_a_governed_atomic_strategy(valid_doc):
    """The parts intake DOES produce conform to the frozen contract.

    Proven the only way that counts: embed them in a real atomic strategy
    document and validate it against the frozen schema.
    """
    result = _result("example_b_rejection_wick_sequence.txt", "TRADER_EXPLANATION")
    atomic = copy.deepcopy(valid_doc("atomic_strategy"))
    atomic["parameters"] = result.document["parameters"]
    atomic["required_hermes_fields"] = result.document["required_hermes_fields"]
    assert validate_document(atomic) == "atomic_strategy"


def test_draft_provenance_drops_into_a_governed_strategy_package(valid_doc):
    result = _result("existing_specification.json")
    package = copy.deepcopy(valid_doc("strategy_package"))
    package["provenance"] = result.document["provenance"]
    assert validate_document(package) == "strategy_package"


def test_the_structured_request_form_produces_a_draft():
    result = _result("existing_specification.json")
    assert result.sufficiently_defined
    assert result.document["intake_id"] == "intake_legacy_wick_reversal"
    assert result.document["title"].startswith("15m wick-rejection reversal")
    assert result.document["provenance"]["notes"]


# --- outcome two: the refusal ------------------------------------------------


def test_a_refusal_is_a_document_not_an_exception():
    """PID line 39 compliance is a result, not a failure."""
    result = _result("near_resistance_pullback.txt", "TRADER_EXPLANATION")
    assert result.outcome == OUTCOME_NOT_SUFFICIENTLY_DEFINED
    assert result.sufficiently_defined is False
    assert result.document["result"] == "STRATEGY_NOT_SUFFICIENTLY_DEFINED"
    assert validate_document(result.document) == "not_sufficiently_defined"


def test_a_refusal_carries_the_intake_id_and_utc_timestamp():
    result = _result("near_resistance_pullback.txt", "TRADER_EXPLANATION")
    assert result.document["intake_id"] == result.request["intake_id"]
    assert result.document["generated_at_utc"] == STAMP


def test_utc_now_is_contract_shaped_and_utc():
    """UTC is canonical for anything persisted (PID line 225)."""
    stamp = utc_now()
    assert stamp.endswith("Z")
    validate_document(
        {
            "$hsa_kind": "not_sufficiently_defined",
            "result": "STRATEGY_NOT_SUFFICIENTLY_DEFINED",
            "intake_id": "intake_stamp_check",
            "generated_at_utc": stamp,
            "provenance": {
                "source_type": "MATT_OBSERVATION",
                "source_reference": "unit test",
                "ingested_at_utc": stamp,
            },
            "unresolved_items": [
                {
                    "item_id": "placeholder",
                    "source_language": "x",
                    "why_unresolved": "y",
                    "blocks": ["PARAMETER_DEFINITION"],
                    "severity": "BLOCKING",
                    "resolution_needed": {
                        "kind": "HUMAN_DECISION",
                        "description": "z",
                        "responsible": "MATT",
                    },
                }
            ],
        }
    )


def test_building_a_refusal_with_nothing_unresolved_is_refused(lexicon):
    """A refusal with nothing unresolved would be a contradiction."""
    from hsa.intake.analyser import analyse
    from hsa.intake.documents import build_not_sufficiently_defined

    request = build_request("bar closes above 1.2345", "MATT_OBSERVATION", "unit test")
    analysis = analyse(request["text"], lexicon)
    with pytest.raises(IntakeError, match="contradiction"):
        build_not_sufficiently_defined(analysis, request, STAMP)


# --- the CLI -----------------------------------------------------------------


def test_cli_exits_zero_and_prints_the_draft(registered, capsys):
    path = FIXTURES / "example_b_rejection_wick_sequence.txt"
    code = main(["intake", str(path), "--source-type", "TRADER_EXPLANATION"])
    assert code == EXIT_OK
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert document["result"] == OUTCOME_DRAFT
    assert "STRATEGY_INTAKE_DRAFT" in captured.err
    assert "large_wick" in captured.err
    assert "PROVISIONAL" in captured.err
    assert "docs/AMBIGUITY-POLICY.md" in captured.err


def test_cli_exits_four_on_refusal_and_says_it_is_correct(registered, capsys):
    """Refusal must be distinguishable from failure without parsing text."""
    path = FIXTURES / "near_resistance_pullback.txt"
    code = main(["intake", str(path), "--source-type", "TRADER_EXPLANATION"])
    assert code == intake_command.EXIT_NOT_SUFFICIENTLY_DEFINED == 4
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert validate_document(document) == "not_sufficiently_defined"
    assert "CORRECT, SUCCESSFUL HSA outcome, not a failure" in captured.err
    assert "near_resistance" in captured.err
    assert "needs HUMAN_DECISION from MATT" in captured.err


def test_cli_refusal_code_is_distinct_from_every_w1_code(registered):
    from hsa import cli

    assert intake_command.EXIT_NOT_SUFFICIENTLY_DEFINED not in (
        cli.EXIT_OK,
        cli.EXIT_INVALID,
        cli.EXIT_USAGE,
        cli.EXIT_ERROR,
    )


def test_cli_writes_to_a_file_when_asked(registered, tmp_path, capsys):
    out = tmp_path / "nested" / "result.json"
    path = FIXTURES / "all_five_pid_phrases.txt"
    code = main(
        ["intake", str(path), "--source-type", "VIDEO_DERIVED", "--out", str(out)]
    )
    assert code == 4
    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(out) in captured.err
    document = json.loads(out.read_text(encoding="utf-8"))
    assert validate_document(document) == "not_sufficiently_defined"


def test_cli_quiet_suppresses_only_the_report(registered, capsys):
    path = FIXTURES / "well_specified_wick_sequence.txt"
    code = main(
        ["intake", str(path), "--source-type", "MATT_OBSERVATION", "--quiet"]
    )
    assert code == EXIT_OK
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["result"] == OUTCOME_DRAFT


def test_cli_missing_file_exits_three(registered, tmp_path, capsys):
    code = main(
        ["intake", str(tmp_path / "absent.txt"), "--source-type", "MATT_OBSERVATION"]
    )
    assert code == EXIT_ERROR
    assert "no such file" in capsys.readouterr().err


def test_cli_accepts_an_alternative_lexicon(registered, capsys):
    """A reviewer can run a candidate lexicon without editing the shipped one."""
    path = FIXTURES / "near_resistance_pullback.txt"
    code = main(
        [
            "intake",
            str(path),
            "--source-type",
            "TRADER_EXPLANATION",
            "--lexicon",
            str(FIXTURES / "lexicon_advisory.json"),
        ]
    )
    assert code == EXIT_OK
    document = json.loads(capsys.readouterr().out)
    assert document["result"] == OUTCOME_DRAFT
    assert document["advisory_items"][0]["item_id"] == "near_resistance"


def test_cli_reports_a_broken_lexicon_as_an_error(registered, tmp_path, capsys):
    broken = tmp_path / "broken.json"
    broken.write_text("{ not json", encoding="utf-8")
    code = main(
        [
            "intake",
            str(FIXTURES / "well_specified_wick_sequence.txt"),
            "--source-type",
            "MATT_OBSERVATION",
            "--lexicon",
            str(broken),
        ]
    )
    assert code == EXIT_ERROR
    assert "not valid JSON" in capsys.readouterr().err


def test_every_intake_error_is_an_hsa_error():
    """So hsa/cli.py maps them without any change to its exit-code table."""
    assert issubclass(IntakeError, HSAError)
    assert issubclass(IntakeRequestError, HSAError)


# --- a citation is a claim, and a wrong one ships in product output -----------

#: What each ``not_yet_specified`` field IS, stated here independently of the
#: code, in the PID's own words. The code says which PID line it cites; PID.md
#: decides whether that line says this. Six of these citations were off by one
#: — ``chain`` cited 134 (semantic timeframe roles) for the chain definition on
#: 135, and the shift ran through direction, timing, persistence, expiry and
#: state semantics — and every draft HSA emitted carried them, so a reader
#: following the reference landed on the wrong obligation.
NOT_YET_SPECIFIED_MEANS = {
    "atomic_strategies": "atomic strategy definitions",
    "chain": "chain definition",
    # This one cites the section that DEFINES the roles (PID lines 84-97),
    # not the bullet that lists the field, because the obligation names the
    # four roles themselves. Both readings are honest; the citation has to
    # match the one the obligation actually makes.
    "timeframe_roles": "semantic roles",
    "direction_semantics": "direction semantics",
    "timing": "timing/persistence/expiry",
    "persistence": "timing/persistence/expiry",
    "expiry": "timing/persistence/expiry",
    "state_semantics": "state semantics",
    "invalidation_conditions": "invalidation/validity conditions",
    "validity_conditions": "invalidation/validity conditions",
    "output_contract": "expected output contract",
    "deterministic_test_cases": "deterministic test cases",
    "evidence_requirements": "backtest/evidence requirements",
    "acceptance_criteria": "acceptance/rejection criteria",
    "rejection_criteria": "acceptance/rejection criteria",
    "cer_references": "CER identity/evidence references",
}


def _pid_lines():
    root = Path(__file__).resolve().parent.parent
    return (root / "PID.md").read_text(encoding="utf-8").splitlines()


def _cited_span(text: str) -> tuple[int, int]:
    """The one PID line span a description cites, as (first, last), 1-based."""
    found = re.findall(r"PID lines? (\d+)(?:\s*-\s*(\d+))?", text)
    assert len(found) == 1, "expected exactly one PID citation in %r" % text
    first, last = found[0]
    return int(first), int(last or first)


def test_every_pid_citation_a_draft_emits_points_at_what_it_claims():
    """The cited line must actually say the thing the obligation names.

    This ships to a reader: ``not_yet_specified`` is in every draft, and its
    whole purpose is to make an unsupplied section read as an obligation with a
    reference. A reference that lands on the wrong bullet is worse than none,
    because it reads as precision.
    """
    lines = _pid_lines()
    assert set(NOT_YET_SPECIFIED_MEANS) == {
        field for field, _obligation in NOT_YET_SPECIFIED
    }, "this table and the emitted list have diverged"

    for field, obligation in NOT_YET_SPECIFIED:
        first, last = _cited_span(obligation)
        expected = NOT_YET_SPECIFIED_MEANS[field]
        cited = " ".join(lines[first - 1 : last])
        assert expected.lower() in cited.lower(), (
            "%s cites PID line(s) %d-%d, which say %r, not %r"
            % (field, first, last, cited.strip(), expected)
        )
