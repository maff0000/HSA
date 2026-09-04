"""Tests for the frozen HSA contract set and its loader."""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from hsa.contracts import (
    DISCRIMINATOR,
    KINDS,
    contracts_dir,
    detect_kind,
    load_schema,
    read_json_file,
    schema_path,
    validate_document,
)
from hsa.errors import (
    DocumentInvalidError,
    DocumentReadError,
    MissingDiscriminatorError,
    UnknownKindError,
)

#: Every valid fixture, and the kind it must validate as.
VALID_FIXTURES = {
    "atomic_strategy": "atomic_strategy",
    "atomic_strategy_breakout": "atomic_strategy",
    "chain": "chain",
    "chain_sequence": "chain",
    "strategy_package": "strategy_package",
    "cer_reference": "cer_reference",
    "not_sufficiently_defined": "not_sufficiently_defined",
}

#: Every invalid fixture, the kind it claims to be, and the JSON path the
#: validator must point at. Pinning the path is the point: an error that
#: does not locate the problem is not useful to a human or to FORGE.
INVALID_FIXTURES = {
    "atomic_strategy": ("atomic_strategy", "$.parameters[0]"),
    "atomic_strategy_references_strategy": ("atomic_strategy", "$"),
    "chain": ("chain", "$.primitive"),
    "chain_of_chain": ("chain", "$.inputs[0]"),
    "strategy_package": (
        "strategy_package",
        "$.atomic_strategies[0].parameters[0]",
    ),
    "cer_reference": ("cer_reference", "$.strategy_version"),
    "cer_reference_no_evidence": ("cer_reference", "$"),
    "not_sufficiently_defined": (
        "not_sufficiently_defined",
        "$.unresolved_items[0]",
    ),
}


# --- the contract set itself -------------------------------------------------


def test_kinds_match_the_contracts_directory():
    """KINDS is the frozen surface; a stray or missing schema file is drift."""
    on_disk = {
        path.name[: -len(".schema.json")]
        for path in contracts_dir().glob("*.schema.json")
    }
    assert on_disk == set(KINDS)


@pytest.mark.parametrize("kind", KINDS)
def test_schema_is_a_valid_draft_2020_12_schema(kind):
    schema = load_schema(kind)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def test_shared_definitions_file_is_a_valid_schema():
    """common.defs.json is shared building blocks, not a document kind."""
    path = contracts_dir() / "common.defs.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert DISCRIMINATOR not in schema.get("properties", {})


@pytest.mark.parametrize("kind", KINDS)
def test_schema_pins_its_own_discriminator(kind):
    """Each schema must accept only its own $hsa_kind, so routing is safe."""
    schema = load_schema(kind)
    assert schema["properties"][DISCRIMINATOR]["const"] == kind
    assert DISCRIMINATOR in schema["required"]
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize("kind", KINDS)
def test_schema_path_and_load_are_consistent(kind):
    assert schema_path(kind).name == kind + ".schema.json"
    assert load_schema(kind)["$id"].endswith(kind + ".schema.json")


def test_unknown_kind_is_refused():
    with pytest.raises(UnknownKindError):
        load_schema("not_a_kind")


# --- valid documents ---------------------------------------------------------


@pytest.mark.parametrize("name,kind", sorted(VALID_FIXTURES.items()))
def test_valid_fixture_validates(valid_doc, name, kind):
    document = valid_doc(name)
    assert validate_document(document) == kind


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_has_a_valid_fixture(kind):
    assert kind in VALID_FIXTURES.values()


def test_explicit_kind_overrides_the_discriminator(valid_doc):
    """--schema forces a contract even when the document claims another."""
    document = valid_doc("chain")
    with pytest.raises(DocumentInvalidError) as caught:
        validate_document(document, kind="atomic_strategy")
    assert caught.value.kind == "atomic_strategy"


# --- invalid documents -------------------------------------------------------


@pytest.mark.parametrize("name,expected", sorted(INVALID_FIXTURES.items()))
def test_invalid_fixture_fails_with_a_useful_path(invalid_doc, name, expected):
    kind, path = expected
    with pytest.raises(DocumentInvalidError) as caught:
        validate_document(invalid_doc(name))
    error = caught.value
    assert error.kind == kind
    assert error.json_path == path
    assert error.failures[0]["message"]
    assert path in str(error)


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_has_an_invalid_fixture(kind):
    assert kind in {claimed for claimed, _ in INVALID_FIXTURES.values()}


# --- the two structural doctrine prohibitions --------------------------------


def test_atomic_strategy_cannot_reference_another_strategy(valid_doc):
    """PID lines 52 and 59: atomic strategies are unaware of each other.

    Enforced by construction — the schema provides no property through which
    another strategy could be named, and rejects unknown ones.
    """
    for field in ("depends_on", "requires_strategy", "components", "inputs"):
        document = valid_doc("atomic_strategy")
        document[field] = [
            {"strategy_id": "range_breakout", "strategy_version": "1.0.0"}
        ]
        with pytest.raises(DocumentInvalidError) as caught:
            validate_document(document)
        assert field in str(caught.value)


def test_atomic_schema_declares_no_strategy_reference_property():
    """No property could ever hold a peer strategy reference."""
    properties = load_schema("atomic_strategy")["properties"]
    # The only strategy_id in an atomic document is its own identity.
    assert "strategy_id" in properties
    for forbidden in (
        "depends_on",
        "requires_strategy",
        "components",
        "inputs",
        "child_strategies",
        "parent_chain",
        "chain_id",
    ):
        assert forbidden not in properties


def test_chain_rejects_a_nested_composition_node(invalid_doc):
    """PID line 82: no recursive chain-of-chain complexity in v1."""
    document = invalid_doc("chain_of_chain")
    with pytest.raises(DocumentInvalidError) as caught:
        validate_document(document)
    rendered = str(caught.value)
    assert "$.inputs[0]" in rendered
    # The nested node's own composition keywords are what makes it a chain.
    assert "primitive" in rendered or "inputs" in rendered


def test_chain_rejects_an_input_that_references_another_chain(valid_doc):
    document = valid_doc("chain")
    document["inputs"][0] = {
        "input_id": "sub_chain",
        "chain_id": "some_other_chain",
        "chain_version": "1.0.0",
        "timeframe_role": "CONTEXT",
        "timeframe": "4H",
        "direction": "INHERIT",
    }
    with pytest.raises(DocumentInvalidError) as caught:
        validate_document(document)
    assert "$.inputs[0]" in str(caught.value)


def test_chain_input_schema_has_no_recursive_reference():
    """The input definition must not be able to expand into a chain."""
    schema = load_schema("chain")
    atomic_input = schema["$defs"]["atomic_input"]
    assert atomic_input["additionalProperties"] is False
    assert set(atomic_input["properties"]) == {
        "input_id",
        "strategy_id",
        "strategy_version",
        "timeframe_role",
        "timeframe",
        "direction",
        "sequence_index",
        "optional",
    }
    assert "$defs" not in atomic_input
    assert "#/$defs/atomic_input" not in json.dumps(atomic_input)


def test_chain_primitives_are_exactly_the_canonical_four():
    """PID lines 65-68. The enum is closed by design."""
    assert load_schema("chain")["properties"]["primitive"]["enum"] == [
        "ALL",
        "ANY",
        "SEQUENCE",
        "CONTEXT_TRIGGER",
    ]


def test_sequence_chain_requires_ordered_inputs(valid_doc):
    document = valid_doc("chain_sequence")
    del document["inputs"][1]["sequence_index"]
    with pytest.raises(DocumentInvalidError):
        validate_document(document)


def test_context_trigger_chain_requires_both_roles(valid_doc):
    document = valid_doc("chain")
    document["inputs"][1]["timeframe_role"] = "CONFIRMATION"
    with pytest.raises(DocumentInvalidError):
        validate_document(document)


def test_refusal_requires_a_resolution_per_unresolved_item(valid_doc):
    """PID line 120: say what is unresolved AND what would resolve it."""
    document = valid_doc("not_sufficiently_defined")
    document["unresolved_items"][0]["resolution_needed"].pop("responsible")
    with pytest.raises(DocumentInvalidError) as caught:
        validate_document(document)
    assert "$.unresolved_items[0].resolution_needed" in str(caught.value)


def test_refusal_cannot_mark_a_candidate_definition_as_chosen(valid_doc):
    """Offering an option must never become adopting one (PID line 39)."""
    document = valid_doc("not_sufficiently_defined")
    document["unresolved_items"][0]["candidate_definitions"][0]["selected"] = True
    with pytest.raises(DocumentInvalidError):
        validate_document(document)


def test_timestamps_must_be_utc(valid_doc):
    """PID line 225: UTC everywhere."""
    document = valid_doc("cer_reference")
    document["recorded_at_utc"] = "2026-09-04T00:00:00+01:00"
    with pytest.raises(DocumentInvalidError) as caught:
        validate_document(document)
    assert "$.recorded_at_utc" in str(caught.value)


# --- loader behaviour --------------------------------------------------------


def test_detect_kind_reads_the_discriminator(valid_doc):
    assert detect_kind(valid_doc("strategy_package")) == "strategy_package"


def test_detect_kind_refuses_a_document_with_no_discriminator():
    with pytest.raises(MissingDiscriminatorError):
        detect_kind({"title": "no discriminator here"})


def test_detect_kind_refuses_a_non_object():
    with pytest.raises(MissingDiscriminatorError):
        detect_kind([1, 2, 3])


def test_detect_kind_refuses_an_unknown_discriminator():
    with pytest.raises(UnknownKindError):
        detect_kind({DISCRIMINATOR: "backtest_result"})


def test_read_json_file_reports_a_missing_file(tmp_path):
    with pytest.raises(DocumentReadError):
        read_json_file(tmp_path / "absent.json")


def test_read_json_file_reports_malformed_json(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(DocumentReadError) as caught:
        read_json_file(broken)
    assert "not valid JSON" in str(caught.value)


def test_alternative_requirements_are_reported_honestly(invalid_doc):
    """An anyOf must not blame one arbitrary branch.

    A CER reference needs any one of four identities. Reporting only
    experiment_id would send the reader to fix the wrong field.
    """
    with pytest.raises(DocumentInvalidError) as caught:
        validate_document(invalid_doc("cer_reference_no_evidence"))
    message = caught.value.failures[0]["message"]
    assert message.startswith("at least one of")
    for identity in ("experiment_id", "run_id", "evidence_id", "artifact_id"):
        assert identity in message


def test_mutually_exclusive_requirements_say_exactly_one(valid_doc):
    """A parameter must carry a range or a value list, never neither."""
    document = valid_doc("atomic_strategy")
    del document["parameters"][0]["allowed_range"]
    with pytest.raises(DocumentInvalidError) as caught:
        validate_document(document)
    message = caught.value.failures[0]["message"]
    assert message == "exactly one of allowed_range, allowed_values is required"


def test_a_parameter_cannot_declare_both_a_range_and_a_value_list(valid_doc):
    document = valid_doc("atomic_strategy")
    document["parameters"][0]["allowed_values"] = [10, 20, 50]
    with pytest.raises(DocumentInvalidError) as caught:
        validate_document(document)
    assert caught.value.json_path == "$.parameters[0]"
