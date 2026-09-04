"""Tests for ``hsa.semantics`` and the ``hsa chain`` command.

Every check in ``hsa.semantics.CHECKS`` has both a passing and a failing case
here, and every failing case pins the JSON path the finding reports — a check
that fires on the right document but points at the wrong field sends whoever
reads it to fix the wrong thing.

The starting documents are W1's fixtures under ``tests/fixtures/valid``, each
deep-copied and then broken in exactly one way, so a failing test names one
cause rather than a pile of them.

``hsa chain`` is exercised here too, by calling the command module directly.
It is not in ``COMMANDS`` yet: the PL wires the registry centrally so four
parallel work items do not collide on one file. These tests therefore drive
``add_arguments``/``run`` through the module contract, which is what the
registry line will do once it lands.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import pytest

from hsa.commands import chain as chain_command
from hsa.contracts import validate_document
from hsa.errors import ContractError, DocumentInvalidError, SchemaLoadError
from hsa.semantics import (
    CHECKS,
    Catalogue,
    Finding,
    check_chain,
    check_document,
    check_package,
    raise_if_invalid,
    timeframe_minutes,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOGUE_DIR = REPO_ROOT / "catalogue" / "atomic"


@pytest.fixture
def catalogue() -> Catalogue:
    return Catalogue.from_directory(CATALOGUE_DIR)


@pytest.fixture
def chain_doc(valid_doc):
    """The valid CONTEXT_TRIGGER chain, deep-copied so a test may break it."""
    return copy.deepcopy(valid_doc("chain"))


@pytest.fixture
def sequence_doc(valid_doc):
    return copy.deepcopy(valid_doc("chain_sequence"))


@pytest.fixture
def package_doc(valid_doc):
    return copy.deepcopy(valid_doc("strategy_package"))


def _checks(findings) -> set[str]:
    return {finding.check for finding in findings}


def _paths(findings, check: str) -> list[str]:
    return [finding.path for finding in findings if finding.check == check]


def _only(findings, check: str) -> Finding:
    """The single finding for ``check``, asserting nothing else fired."""
    assert _checks(findings) == {check}, "expected only %s, got %r" % (
        check,
        _checks(findings),
    )
    assert len(findings) == 1
    return findings[0]


# --- the fixtures are genuinely clean ----------------------------------------


def test_valid_chain_fixture_has_no_semantic_findings(chain_doc, catalogue):
    """The passing case for every chain check at once."""
    assert check_chain(chain_doc, catalogue=catalogue) == []


def test_valid_sequence_fixture_has_no_semantic_findings(sequence_doc, catalogue):
    """Includes the legitimate use of ``optional`` on a SEQUENCE step."""
    assert check_chain(sequence_doc, catalogue=catalogue) == []


def test_valid_package_fixture_has_no_semantic_findings(package_doc, catalogue):
    """The passing case for every package check at once."""
    assert check_package(package_doc, catalogue=catalogue) == []


def test_catalogue_is_optional_and_omitting_it_skips_resolution(chain_doc):
    chain_doc["inputs"][0]["strategy_id"] = "not_in_any_catalogue"
    assert check_chain(chain_doc) == []


# --- chain.input_id_unique ---------------------------------------------------


def test_duplicate_input_id_is_reported(chain_doc, catalogue):
    chain_doc["inputs"][1]["input_id"] = chain_doc["inputs"][0]["input_id"]
    finding = _only(check_chain(chain_doc, catalogue=catalogue), "chain.input_id_unique")
    assert finding.path == "$.inputs[1].input_id"
    assert "htf_context" in finding.message


def test_distinct_input_ids_are_accepted(chain_doc, catalogue):
    assert "chain.input_id_unique" not in _checks(
        check_chain(chain_doc, catalogue=catalogue)
    )


# --- chain.sequence_index_contiguous / misplaced -----------------------------


def test_sequence_indices_with_a_gap_are_reported(sequence_doc, catalogue):
    sequence_doc["inputs"][1]["sequence_index"] = 3
    finding = _only(
        check_chain(sequence_doc, catalogue=catalogue),
        "chain.sequence_index_contiguous",
    )
    assert finding.path == "$.inputs"
    assert "[1, 3]" in finding.message


def test_duplicate_sequence_indices_are_reported(sequence_doc, catalogue):
    sequence_doc["inputs"][1]["sequence_index"] = 1
    finding = _only(
        check_chain(sequence_doc, catalogue=catalogue),
        "chain.sequence_index_contiguous",
    )
    assert finding.path == "$.inputs"


def test_contiguous_sequence_indices_are_accepted(sequence_doc, catalogue):
    assert "chain.sequence_index_contiguous" not in _checks(
        check_chain(sequence_doc, catalogue=catalogue)
    )


def test_sequence_index_on_a_non_sequence_chain_is_reported(chain_doc, catalogue):
    chain_doc["inputs"][1]["sequence_index"] = 2
    finding = _only(
        check_chain(chain_doc, catalogue=catalogue), "chain.sequence_index_misplaced"
    )
    assert finding.path == "$.inputs[1].sequence_index"
    assert "CONTEXT_TRIGGER" in finding.message


def test_no_sequence_index_on_a_non_sequence_chain_is_accepted(chain_doc, catalogue):
    assert "chain.sequence_index_misplaced" not in _checks(
        check_chain(chain_doc, catalogue=catalogue)
    )


# --- chain.optional_input ----------------------------------------------------


def test_sole_input_may_not_be_optional(chain_doc, catalogue):
    chain_doc["primitive"] = "ALL"
    chain_doc["inputs"] = [chain_doc["inputs"][0]]
    chain_doc["inputs"][0]["optional"] = True
    chain_doc["timeframe_roles"] = {"CONTEXT": "4H"}
    finding = _only(check_chain(chain_doc, catalogue=catalogue), "chain.optional_input")
    assert finding.path == "$.inputs[0].optional"
    assert "sole cause of a match" in finding.message


def test_all_inputs_optional_is_reported(chain_doc, catalogue):
    chain_doc["primitive"] = "ALL"
    for item in chain_doc["inputs"]:
        item["optional"] = True
    finding = _only(check_chain(chain_doc, catalogue=catalogue), "chain.optional_input")
    assert finding.path == "$.inputs"
    assert "every input" in finding.message


def test_optional_input_under_any_is_reported(chain_doc, catalogue):
    """Under ANY one match is sufficient, so an optional input can be it."""
    chain_doc["primitive"] = "ANY"
    chain_doc["inputs"][1]["optional"] = True
    finding = _only(check_chain(chain_doc, catalogue=catalogue), "chain.optional_input")
    assert finding.path == "$.inputs[1].optional"
    assert "ANY" in finding.message


def test_optional_context_input_is_reported(chain_doc, catalogue):
    chain_doc["inputs"][0]["optional"] = True
    finding = _only(check_chain(chain_doc, catalogue=catalogue), "chain.optional_input")
    assert finding.path == "$.inputs[0].optional"
    assert "CONTEXT" in finding.message


def test_optional_trigger_input_is_reported(chain_doc, catalogue):
    chain_doc["inputs"][1]["optional"] = True
    finding = _only(check_chain(chain_doc, catalogue=catalogue), "chain.optional_input")
    assert finding.path == "$.inputs[1].optional"
    assert "TRIGGER" in finding.message


def test_optional_step_beside_a_required_one_is_accepted(sequence_doc, catalogue):
    """PID line 242's optional lower-timeframe trigger, the intended use."""
    assert sequence_doc["inputs"][1]["optional"] is True
    assert "chain.optional_input" not in _checks(
        check_chain(sequence_doc, catalogue=catalogue)
    )


def test_optional_under_all_beside_a_required_input_is_accepted(chain_doc, catalogue):
    chain_doc["primitive"] = "ALL"
    chain_doc["inputs"][1]["optional"] = True
    assert "chain.optional_input" not in _checks(
        check_chain(chain_doc, catalogue=catalogue)
    )


# --- chain.reference_resolves ------------------------------------------------


def test_unknown_strategy_id_is_reported(chain_doc, catalogue):
    chain_doc["inputs"][1]["strategy_id"] = "no_such_strategy"
    finding = _only(
        check_chain(chain_doc, catalogue=catalogue), "chain.reference_resolves"
    )
    assert finding.path == "$.inputs[1].strategy_id"
    assert "no catalogue entry" in finding.message


def test_unknown_version_of_a_known_strategy_is_reported(chain_doc, catalogue):
    chain_doc["inputs"][1]["strategy_version"] = "9.9.9"
    finding = _only(
        check_chain(chain_doc, catalogue=catalogue), "chain.reference_resolves"
    )
    assert finding.path == "$.inputs[1].strategy_version"
    assert "1.0.0" in finding.message and "9.9.9" in finding.message


def test_resolvable_references_are_accepted(chain_doc, catalogue):
    assert "chain.reference_resolves" not in _checks(
        check_chain(chain_doc, catalogue=catalogue)
    )


# --- chain.context_trigger_timeframes ----------------------------------------


def test_context_below_trigger_is_reported(chain_doc, catalogue):
    chain_doc["inputs"][0]["timeframe"] = "1M"
    chain_doc["timeframe_roles"]["CONTEXT"] = "1M"
    finding = _only(
        check_chain(chain_doc, catalogue=catalogue), "chain.context_trigger_timeframes"
    )
    assert finding.path == "$.inputs[0].timeframe"
    assert "lower timeframe" in finding.message


def test_context_equal_to_trigger_is_reported(chain_doc, catalogue):
    chain_doc["inputs"][0]["timeframe"] = "5M"
    chain_doc["timeframe_roles"]["CONTEXT"] = "5M"
    finding = _only(
        check_chain(chain_doc, catalogue=catalogue), "chain.context_trigger_timeframes"
    )
    assert finding.path == "$.inputs[0].timeframe"
    assert "the same timeframe" in finding.message


def test_context_above_trigger_is_accepted(chain_doc, catalogue):
    assert "chain.context_trigger_timeframes" not in _checks(
        check_chain(chain_doc, catalogue=catalogue)
    )


@pytest.mark.parametrize(
    "context,trigger",
    [("1D", "4H"), ("4H", "15M"), ("1W", "1D"), ("1H", "1M")],
)
def test_higher_context_timeframes_are_accepted(chain_doc, catalogue, context, trigger):
    chain_doc["inputs"][0]["timeframe"] = context
    chain_doc["inputs"][1]["timeframe"] = trigger
    chain_doc["timeframe_roles"] = {"CONTEXT": context, "TRIGGER": trigger}
    assert check_chain(chain_doc, catalogue=catalogue) == []


def test_timeframe_minutes_reads_m_as_minutes():
    """PID line 95 writes 1H/15M/5M/1M, so M is minutes and never months."""
    assert timeframe_minutes("1M") == 1
    assert timeframe_minutes("15M") == 15
    assert timeframe_minutes("1H") == 60
    assert timeframe_minutes("4H") == 240
    assert timeframe_minutes("1D") == 1440
    assert timeframe_minutes("1W") == 10080
    assert timeframe_minutes("15M") < timeframe_minutes("1H")
    assert timeframe_minutes("nonsense") is None
    assert timeframe_minutes(None) is None


# --- chain.timeframe_role_mapping --------------------------------------------


def test_input_timeframe_disagreeing_with_the_role_model_is_reported(
    chain_doc, catalogue
):
    chain_doc["timeframe_roles"]["CONTEXT"] = "1D"
    finding = _only(
        check_chain(chain_doc, catalogue=catalogue), "chain.timeframe_role_mapping"
    )
    assert finding.path == "$.inputs[0].timeframe"
    assert "1D" in finding.message and "4H" in finding.message


def test_role_missing_from_the_role_model_is_reported(chain_doc, catalogue):
    chain_doc["inputs"][1]["timeframe_role"] = "CONFIRMATION"
    findings = check_chain(chain_doc, catalogue=catalogue)
    paths = _paths(findings, "chain.timeframe_role_mapping")
    assert paths == ["$.inputs[1].timeframe_role"]


def test_agreeing_role_model_is_accepted(chain_doc, catalogue):
    assert "chain.timeframe_role_mapping" not in _checks(
        check_chain(chain_doc, catalogue=catalogue)
    )


# --- package.chain_agreement -------------------------------------------------


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("timing", "evaluation_timeframe", "1H"),
        ("persistence", "persist_for_bars", 99),
        ("expiry", "expires_after_bars", 99),
        ("state_semantics", "initial_state", "SOMETHING_ELSE"),
        ("direction_semantics", "inversion_allowed", True),
        ("timeframe_roles", "CONTEXT", "1D"),
    ],
)
def test_chain_contradicting_the_package_is_reported(
    package_doc, catalogue, section, key, value
):
    """W1 flagged this as a real unenforced gap; the package level wins."""
    package_doc["chain"][section][key] = value
    findings = check_package(package_doc, catalogue=catalogue)
    paths = _paths(findings, "package.chain_agreement")
    assert paths == ["$.chain.%s.%s" % (section, key)]
    message = next(
        f.message for f in findings if f.check == "package.chain_agreement"
    )
    assert "authoritative" in message or "governed statement" in message


def test_chain_omitting_a_package_declaration_is_reported(package_doc, catalogue):
    del package_doc["chain"]["persistence"]["re_arm_rule"]
    findings = check_package(package_doc, catalogue=catalogue)
    assert _paths(findings, "package.chain_agreement") == [
        "$.chain.persistence.re_arm_rule"
    ]


def test_chain_declaring_what_the_package_does_not_is_reported(package_doc, catalogue):
    del package_doc["persistence"]["re_arm_rule"]
    findings = check_package(package_doc, catalogue=catalogue)
    assert _paths(findings, "package.chain_agreement") == [
        "$.chain.persistence.re_arm_rule"
    ]


def test_agreeing_package_and_chain_are_accepted(package_doc, catalogue):
    assert "package.chain_agreement" not in _checks(
        check_package(package_doc, catalogue=catalogue)
    )


# --- package.chain_inputs_embedded -------------------------------------------


def test_chain_input_not_embedded_in_the_package_is_reported(package_doc, catalogue):
    package_doc["chain"]["inputs"][1]["strategy_id"] = "rejection_wick"
    findings = check_package(package_doc, catalogue=catalogue)
    assert _paths(findings, "package.chain_inputs_embedded") == ["$.chain.inputs[1]"]


def test_chain_input_at_an_unembedded_version_is_reported(package_doc, catalogue):
    package_doc["atomic_strategies"][1]["strategy_version"] = "2.0.0"
    findings = check_package(package_doc, catalogue=catalogue)
    assert _paths(findings, "package.chain_inputs_embedded") == ["$.chain.inputs[1]"]


def test_fully_embedded_chain_inputs_are_accepted(package_doc, catalogue):
    assert "package.chain_inputs_embedded" not in _checks(
        check_package(package_doc, catalogue=catalogue)
    )


# --- package.hermes_coverage -------------------------------------------------


def test_atomic_hermes_field_missing_from_the_package_is_reported(
    package_doc, catalogue
):
    package_doc["required_hermes_fields"] = [
        field
        for field in package_doc["required_hermes_fields"]
        if field["field"] != "ma.slow"
    ]
    findings = check_package(package_doc, catalogue=catalogue)
    paths = _paths(findings, "package.hermes_coverage")
    assert paths == ["$.atomic_strategies[0].required_hermes_fields[1]"]
    message = next(f.message for f in findings if f.check == "package.hermes_coverage")
    assert "ma.slow on 4H" in message


def test_atomic_hermes_field_on_the_wrong_timeframe_is_reported(package_doc, catalogue):
    package_doc["required_hermes_fields"][0]["timeframe"] = "1D"
    findings = check_package(package_doc, catalogue=catalogue)
    assert _paths(findings, "package.hermes_coverage") == [
        "$.atomic_strategies[0].required_hermes_fields[0]"
    ]


def test_package_entry_without_a_timeframe_covers_any_timeframe(package_doc, catalogue):
    del package_doc["required_hermes_fields"][0]["timeframe"]
    assert "package.hermes_coverage" not in _checks(
        check_package(package_doc, catalogue=catalogue)
    )


def test_full_hermes_coverage_is_accepted(package_doc, catalogue):
    assert "package.hermes_coverage" not in _checks(
        check_package(package_doc, catalogue=catalogue)
    )


# --- the public API ----------------------------------------------------------


def test_finding_renders_in_the_same_shape_as_a_structural_failure(chain_doc):
    """A caller must not have to branch on structural versus semantic.

    W1's ``DocumentInvalidError.failures`` entries carry exactly these keys.
    """
    chain_doc["inputs"][1]["input_id"] = chain_doc["inputs"][0]["input_id"]
    failure = check_chain(chain_doc)[0].as_failure()
    assert set(failure) == {"path", "message", "schema_path"}
    assert failure["schema_path"] == "semantic/chain.input_id_unique"

    with pytest.raises(DocumentInvalidError) as structural:
        validate_document({"$hsa_kind": "chain"})
    assert set(structural.value.failures[0]) == set(failure)


def test_raise_if_invalid_raises_w1s_typed_error(chain_doc):
    chain_doc["inputs"][1]["input_id"] = chain_doc["inputs"][0]["input_id"]
    findings = check_chain(chain_doc)
    with pytest.raises(DocumentInvalidError) as excinfo:
        raise_if_invalid(findings, "chain", source="somewhere.json")
    assert excinfo.value.kind == "chain"
    assert excinfo.value.json_path == "$.inputs[1].input_id"
    assert excinfo.value.source == "somewhere.json"


def test_raise_if_invalid_is_silent_when_there_is_nothing_to_report():
    assert raise_if_invalid([], "chain") is None


def test_check_document_dispatches_on_the_declared_kind(
    chain_doc, package_doc, catalogue
):
    chain_doc["inputs"][1]["input_id"] = chain_doc["inputs"][0]["input_id"]
    assert _checks(check_document(chain_doc, catalogue=catalogue)) == {
        "chain.input_id_unique"
    }
    assert check_document(package_doc, catalogue=catalogue) == []


def test_check_document_returns_empty_for_kinds_with_no_semantic_rules(valid_doc):
    assert check_document(valid_doc("atomic_strategy")) == []
    assert check_document(valid_doc("cer_reference")) == []


def test_every_declared_check_can_actually_fire(chain_doc, package_doc, catalogue):
    """CHECKS is a public surface; an id that never fires is a dead promise.

    Breaks a document once per check and collects what is emitted, so the
    union must be exactly CHECKS. An id added to the tuple without an
    implementation, or an implementation whose id was mistyped, fails here.
    """
    emitted: set[str] = set()

    def chain_variant(mutate):
        document = copy.deepcopy(chain_doc)
        mutate(document)
        return check_chain(document, catalogue=catalogue)

    def package_variant(mutate):
        document = copy.deepcopy(package_doc)
        mutate(document)
        return check_package(document, catalogue=catalogue)

    def set_duplicate_id(doc):
        doc["inputs"][1]["input_id"] = doc["inputs"][0]["input_id"]

    def make_sequence_with_a_gap(doc):
        doc["primitive"] = "SEQUENCE"
        doc["timing"]["sequence_window"] = {"max_bars": 12, "timeframe": "5M"}
        doc["inputs"][0]["sequence_index"] = 1
        doc["inputs"][1]["sequence_index"] = 5

    for mutate in (
        set_duplicate_id,
        make_sequence_with_a_gap,
        lambda doc: doc["inputs"][1].__setitem__("sequence_index", 2),
        lambda doc: doc["inputs"][1].__setitem__("optional", True),
        lambda doc: doc["inputs"][1].__setitem__("strategy_id", "no_such_strategy"),
        lambda doc: doc["inputs"][0].__setitem__("timeframe", "1M"),
        lambda doc: doc["timeframe_roles"].__setitem__("CONTEXT", "1D"),
    ):
        emitted.update(finding.check for finding in chain_variant(mutate))

    for mutate in (
        lambda doc: doc["chain"]["timing"].__setitem__("evaluation_timeframe", "1H"),
        lambda doc: doc["chain"]["inputs"][1].__setitem__("strategy_id", "rejection_wick"),
        lambda doc: doc.__setitem__(
            "required_hermes_fields", doc["required_hermes_fields"][:1]
        ),
    ):
        emitted.update(finding.check for finding in package_variant(mutate))

    assert emitted == set(CHECKS), "never fired: %r" % (set(CHECKS) - emitted)


def test_catalogue_api(catalogue):
    assert catalogue.get("golden_cross", "1.0.0")["strategy_id"] == "golden_cross"
    assert catalogue.get("golden_cross", "9.9.9") is None
    assert catalogue.get("no_such_strategy", "1.0.0") is None
    assert catalogue.versions("golden_cross") == ("1.0.0",)
    assert catalogue.versions("no_such_strategy") == ()
    assert "golden_cross" in catalogue.ids
    assert len(list(catalogue)) == len(catalogue)
    assert "Catalogue(" in repr(catalogue)


def test_empty_catalogue_resolves_nothing(chain_doc):
    findings = check_chain(chain_doc, catalogue=Catalogue.empty())
    assert _checks(findings) == {"chain.reference_resolves"}
    assert len(findings) == 2


def test_catalogue_from_a_missing_directory_fails_loudly(tmp_path):
    with pytest.raises(SchemaLoadError):
        Catalogue.from_directory(tmp_path / "nope")


def test_catalogue_rejects_an_entry_without_an_identity(tmp_path):
    (tmp_path / "broken.json").write_text('{"title": "no identity"}', encoding="utf-8")
    with pytest.raises(SchemaLoadError):
        Catalogue.from_directory(tmp_path)


def test_catalogue_rejects_unparseable_json(tmp_path):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SchemaLoadError):
        Catalogue.from_directory(tmp_path)


def test_semantic_checks_tolerate_a_structurally_broken_document():
    """Shape problems belong to the schema; this module must not duplicate them."""
    assert check_chain({"primitive": "SEQUENCE", "inputs": "not a list"}) == []
    assert check_chain("not a document") == []
    assert check_package({"chain": None}) == []


# --- the hsa chain command ---------------------------------------------------


def _parse(argv):
    parser = argparse.ArgumentParser()
    chain_command.add_arguments(parser)
    return parser.parse_args(argv)


def _write(tmp_path, name, document):
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return str(path)


def test_chain_command_satisfies_the_module_contract():
    """The contract in hsa/commands/__init__.py, which the PL will register."""
    assert chain_command.NAME == "chain"
    assert isinstance(chain_command.HELP, str) and chain_command.HELP
    assert callable(chain_command.add_arguments)
    assert callable(chain_command.run)


def test_chain_command_accepts_a_valid_chain(capsys, valid_path):
    assert chain_command.run(_parse([str(valid_path("chain"))])) == 0
    out = capsys.readouterr().out
    assert "valid chain, structurally and semantically" in out
    assert "CONTEXT_TRIGGER(htf_context@4H, ltf_trigger@5M)" in out
    # Composition is explained, not merely accepted (PID lines 70-80).
    for expected in ("composition", "inputs", "role model", "direction", "timing",
                     "state", "persistence", "expiry", "explanation", "provenance"):
        assert expected in out
    # Atomic references resolve to real catalogue entries.
    assert "golden_cross 1.0.0 — Moving average cross" in out
    assert "range_breakout 1.0.0 — Range breakout" in out


def test_chain_command_marks_an_optional_input_in_the_expression(capsys, valid_path):
    assert chain_command.run(_parse([str(valid_path("chain_sequence"))])) == 0
    assert "SEQUENCE(step_one@15M, step_two@5M?)" in capsys.readouterr().out


def test_chain_command_quiet_suppresses_the_explanation(capsys, valid_path):
    assert chain_command.run(_parse([str(valid_path("chain")), "--quiet"])) == 0
    assert capsys.readouterr().out == ""


def test_chain_command_rejects_a_structurally_invalid_chain(invalid_path):
    with pytest.raises(DocumentInvalidError):
        chain_command.run(_parse([str(invalid_path("chain"))]))


def test_chain_command_rejects_a_semantically_invalid_chain(tmp_path, chain_doc):
    """Structurally valid, semantically wrong: the whole point of this command."""
    chain_doc["inputs"][0]["timeframe"] = "1M"
    chain_doc["timeframe_roles"]["CONTEXT"] = "1M"
    path = _write(tmp_path, "inverted.json", chain_doc)

    assert validate_document(chain_doc) == "chain"  # hsa validate would pass it

    with pytest.raises(DocumentInvalidError) as excinfo:
        chain_command.run(_parse([path]))
    assert excinfo.value.json_path == "$.inputs[0].timeframe"
    assert "semantic/chain.context_trigger_timeframes" in [
        failure["schema_path"] for failure in excinfo.value.failures
    ]


def test_chain_command_reports_unresolved_references(tmp_path, chain_doc):
    chain_doc["inputs"][0]["strategy_id"] = "no_such_strategy"
    path = _write(tmp_path, "unresolved.json", chain_doc)
    with pytest.raises(DocumentInvalidError) as excinfo:
        chain_command.run(_parse([path]))
    assert excinfo.value.json_path == "$.inputs[0].strategy_id"


def test_chain_command_no_catalogue_skips_resolution(capsys, tmp_path, chain_doc):
    chain_doc["inputs"][0]["strategy_id"] = "no_such_strategy"
    path = _write(tmp_path, "unresolved.json", chain_doc)
    assert chain_command.run(_parse([path, "--no-catalogue"])) == 0
    assert "catalogue resolution skipped" in capsys.readouterr().out


def test_chain_command_honours_an_explicit_catalogue_directory(
    capsys, tmp_path, valid_path
):
    assert (
        chain_command.run(
            _parse([str(valid_path("chain")), "--catalogue", str(CATALOGUE_DIR)])
        )
        == 0
    )
    assert str(CATALOGUE_DIR) in capsys.readouterr().out

    with pytest.raises(DocumentInvalidError):
        chain_command.run(
            _parse([str(valid_path("chain")), "--catalogue", str(tmp_path)])
        )


def test_chain_command_refuses_a_document_of_another_kind(valid_path):
    with pytest.raises(ContractError) as excinfo:
        chain_command.run(_parse([str(valid_path("atomic_strategy"))]))
    assert "expects a chain document" in str(excinfo.value)
