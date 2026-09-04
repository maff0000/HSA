"""PID acceptance Example A — context + trigger chain (PID lines 234-236).

    A multi-timeframe strategy using a higher-timeframe context such as
    golden cross/market structure plus lower-timeframe breakout/confirmation.

The governed package under test is ``strategies/gold_context_breakout/1.0.0/``.
These tests prove it mechanically rather than by assertion in prose: that it
came through HSA's own intake, that it decomposes onto catalogue entries at
the exact versions it pins, that its CONTEXT genuinely sits above its
TRIGGER, that HERMES coverage holds, and that its CER references validate.

Each test names the PID acceptance criterion it proves (PID lines 250-262).
Criteria 1, 3 and 13 are proven elsewhere — by ``tests/test_boot.py``,
``tests/test_ambiguity.py`` and ``tests/test_versioning.py`` respectively —
and are only touched here where Example A exercises them incidentally.

NOTE ON WHAT THIS IS NOT. Example A is a product proof, not a claim of a
profitable strategy (PID line 244). Nothing here asserts that the strategy
makes money, and nothing could: no evidence exists, and the CER references
it carries are contract fixtures standing in for a system that is not live.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hsa.cer import (
    SOURCE_CONTRACT_FIXTURE,
    is_fixture,
    validate_reference,
)
from hsa.contracts import validate_document
from hsa.intake import OUTCOME_DRAFT, OUTCOME_NOT_SUFFICIENTLY_DEFINED, intake, read_request
from hsa.semantics import Catalogue, check_package, timeframe_minutes

REPO = Path(__file__).resolve().parent.parent
STRATEGY_DIR = REPO / "strategies" / "gold_context_breakout" / "1.0.0"
PACKAGE_PATH = STRATEGY_DIR / "package.json"
SOURCE_PATH = STRATEGY_DIR / "source.txt"
EVIDENCE_PATH = STRATEGY_DIR / "evidence.json"
CATALOGUE_DIR = REPO / "catalogue" / "atomic"
INTAKE_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "intake"

STRATEGY_ID = "gold_context_breakout"
STRATEGY_VERSION = "1.0.0"

#: The two atomic strategies Example A composes, at the versions it pins.
PINNED = (("golden_cross", "1.0.0"), ("range_breakout", "1.0.0"))


def _load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def package():
    return _load(PACKAGE_PATH)


@pytest.fixture(scope="module")
def evidence():
    return _load(EVIDENCE_PATH)


@pytest.fixture(scope="module")
def catalogue():
    return Catalogue.from_directory(CATALOGUE_DIR)


@pytest.fixture(scope="module")
def chain(package):
    return package["chain"]


# --- the inventory itself ----------------------------------------------------


def test_the_package_lives_at_the_canonical_inventory_path():
    """strategies/<strategy_id>/<strategy_version>/ — see strategies/README.md."""
    assert PACKAGE_PATH.is_file()
    assert SOURCE_PATH.is_file()
    assert EVIDENCE_PATH.is_file()
    assert STRATEGY_DIR.parent.name == STRATEGY_ID
    assert STRATEGY_DIR.name == STRATEGY_VERSION


def test_the_directory_names_agree_with_the_identity_inside_the_package(package):
    """A package filed under a path that contradicts its own identity is
    unfindable by the identity CER records evidence against (criterion 10)."""
    assert package["strategy_id"] == STRATEGY_DIR.parent.name
    assert package["strategy_version"] == STRATEGY_DIR.name


# --- criterion 2: ingest a realistic raw strategy description ----------------


def test_criterion_2_the_raw_source_passes_intake_as_a_draft():
    """PID criterion 2: ingest a realistic raw strategy description.

    Driven through the shipped intake, not simulated. The outcome is a draft
    with no discretionary term left unruled.
    """
    request = read_request(SOURCE_PATH, source_type="TRADER_EXPLANATION")
    result = intake(request)

    assert result.outcome == OUTCOME_DRAFT
    assert result.sufficiently_defined is True
    assert result.blocking_items == []


def test_criterion_2_the_packaged_source_is_the_intake_fixture_byte_for_byte():
    """The description the package claims provenance to must be the one that
    actually went through intake. Two copies that could drift would make the
    provenance claim unverifiable."""
    packaged = SOURCE_PATH.read_bytes()
    fixture = (INTAKE_FIXTURES / "example_a_gold_context_breakout.txt").read_bytes()
    assert packaged == fixture


def test_the_first_pass_of_the_same_source_was_refused_not_guessed():
    """Example A's own ambiguity history, which is why the final source reads
    as precisely as it does (PID criterion 3, exercised here incidentally).

    The trader's first explanation said "strong trend" and "clean breakout".
    Both are REFUSE terms under docs/AMBIGUITY-POLICY.md: their measurement
    basis is undefined, so HSA could not parameterise them without inventing
    trading semantics. It refused and named what it needed.
    """
    request = read_request(
        INTAKE_FIXTURES / "example_a_first_pass.txt",
        source_type="TRADER_EXPLANATION",
    )
    result = intake(request)

    assert result.outcome == OUTCOME_NOT_SUFFICIENTLY_DEFINED
    assert result.sufficiently_defined is False

    refused = {item["item_id"] for item in result.blocking_items}
    assert refused == {"strong_trend", "good_breakout"}

    for item in result.blocking_items:
        assert item["why_unresolved"].strip()
        assert item["resolution_needed"]["description"].strip()
        assert item["resolution_needed"]["responsible"]
        assert "ATOMIC_DECOMPOSITION" in item["blocks"]


def test_the_resolution_named_constructions_rather_than_parameterising(package):
    """The refusal was answered by the trader naming the constructions, not by
    HSA choosing them. So the second pass resolves with zero parameterised
    terms, and the package says so in its provenance rather than leaving a
    reader to infer that no guess was made."""
    request = read_request(SOURCE_PATH, source_type="TRADER_EXPLANATION")
    result = intake(request)

    assert result.document["resolved_terms"] == []

    notes = package["provenance"]["notes"]
    assert "STRATEGY_NOT_SUFFICIENTLY_DEFINED" in notes
    assert "strong_trend" in notes and "good_breakout" in notes


# --- criterion 9: a coherent deterministic package ---------------------------


def test_criterion_9_the_package_is_structurally_valid(package):
    """PID criterion 9: produce a coherent deterministic HELIOS package.

    Structural half: the frozen strategy_package contract.
    """
    assert validate_document(package, source=str(PACKAGE_PATH)) == "strategy_package"


def test_criterion_9_the_package_is_semantically_clean(package, catalogue):
    """PID criterion 9, semantic half: the cross-field rules JSON Schema
    cannot express. This is the check that would catch an inverted context,
    a chain that disagrees with its package, or an unresolvable reference."""
    assert check_package(package, catalogue=catalogue) == []


def test_criterion_9_every_package_section_the_pid_enumerates_is_present(package):
    """PID lines 126-146. The contract requires each of these, so this test
    is a restatement rather than new coverage — but Example A is where the
    enumeration is proven against a real package rather than a fixture."""
    for field in (
        "strategy_id",
        "strategy_version",
        "title",
        "description",
        "thesis",
        "instruments",
        "intended_horizon",
        "intended_style",
        "required_hermes_fields",
        "atomic_strategies",
        "timeframe_roles",
        "chain",
        "direction_semantics",
        "timing",
        "persistence",
        "expiry",
        "state_semantics",
        "invalidation_conditions",
        "validity_conditions",
        "parameters",
        "output_contract",
        "deterministic_test_cases",
        "evidence_requirements",
        "acceptance_criteria",
        "rejection_criteria",
        "provenance",
        "cer_references",
        "lifecycle",
    ):
        assert field in package, "package omits %s" % field


def test_the_package_states_it_is_a_product_proof_not_a_profitable_strategy(package):
    """PID line 244. An example that reads as a trading recommendation is a
    different and worse artefact than the one the PID asked for."""
    description = package["description"]
    assert "PRODUCT PROOF" in description.upper()
    assert "NOT A CLAIM OF A PROFITABLE STRATEGY" in description.upper()


# --- criterion 4: decomposition into independent atomic strategies -----------


def test_criterion_4_the_package_decomposes_into_atomic_strategies(package):
    """PID criterion 4: decompose measurable logic into independent atomics."""
    atomics = package["atomic_strategies"]
    assert len(atomics) == 2
    identities = {(a["strategy_id"], a["strategy_version"]) for a in atomics}
    assert identities == set(PINNED)


def test_criterion_4_each_embedded_atomic_is_valid_on_its_own(package):
    """Each embedded definition validates against the atomic contract by
    itself: an atomic strategy is independently testable (PID line 47)."""
    for atomic in package["atomic_strategies"]:
        assert validate_document(atomic, kind="atomic_strategy") == "atomic_strategy"


def test_criterion_4_each_atomic_asserts_it_is_unaware_of_the_others(package):
    """PID lines 51-52. The contract makes a peer reference structurally
    unrepresentable; this asserts the doctrine flags agree with that."""
    for atomic in package["atomic_strategies"]:
        assertions = atomic["doctrine_assertions"]
        assert assertions["unaware_of_other_strategies"] is True
        assert assertions["self_contained"] is True
        assert assertions["independently_testable"] is True
        assert assertions["deterministic"] is True
        assert assertions["execution_blind"] is True
        assert assertions["hermes_driven"] is True


def test_criterion_4_no_atomic_names_the_other(package):
    """Stronger than the flag: neither embedded document mentions the other's
    strategy_id anywhere in its text, so neither could have been authored
    with the other in mind."""
    atomics = {a["strategy_id"]: a for a in package["atomic_strategies"]}
    for own_id, atomic in atomics.items():
        rendered = json.dumps(atomic)
        for other_id in atomics:
            if other_id != own_id:
                assert other_id not in rendered


# --- criterion 10: identity and version preservation -------------------------


def test_criterion_10_every_chain_input_resolves_in_the_catalogue(chain, catalogue):
    """PID criterion 10, and PID line 72: a chain pins the exact immutable
    version it was proven against, and that version must actually exist."""
    for item in chain["inputs"]:
        entry = catalogue.get(item["strategy_id"], item["strategy_version"])
        assert entry is not None, (
            "chain input %s pins %s %s, which the catalogue does not hold"
            % (item["input_id"], item["strategy_id"], item["strategy_version"])
        )


def test_criterion_10_the_embedded_atomics_are_the_catalogue_entries_verbatim(package):
    """The package embeds full definitions so FORGE implements from one
    document (PID line 148). Those embedded copies must be the catalogue
    entries themselves, not paraphrases that could drift away from the
    versions the chain pins and CER records evidence against."""
    for atomic in package["atomic_strategies"]:
        catalogue_entry = _load(CATALOGUE_DIR / (atomic["strategy_id"] + ".json"))
        assert atomic == catalogue_entry


def test_criterion_10_the_chain_pins_a_version_for_every_input(chain):
    """Version is required, never implied."""
    for item in chain["inputs"]:
        assert item["strategy_version"], item["input_id"]


def test_criterion_10_the_lifecycle_records_immutability_and_lineage(package):
    """PID lines 185-189. status CANDIDATE is the honest one: no evidence
    gate has been evaluated, so nothing here has been promoted."""
    lifecycle = package["lifecycle"]
    assert lifecycle["immutable_once_promoted"] is True
    assert lifecycle["status"] == "CANDIDATE"
    assert lifecycle["supersedes"] is None
    assert lifecycle["created_at_utc"].endswith("Z")


# --- criterion 5: an explicit chain using canonical primitives ---------------


def test_criterion_5_the_chain_uses_the_context_trigger_primitive(chain):
    """PID criterion 5. CONTEXT_TRIGGER is the primitive Example A exists to
    exercise: it is the only one distinguishing a condition that persists
    from an event that occurs."""
    assert chain["primitive"] == "CONTEXT_TRIGGER"
    assert chain["$hsa_kind"] == "chain"


def test_criterion_5_the_chain_is_valid_as_a_chain_document(chain):
    assert validate_document(chain, kind="chain") == "chain"


def test_criterion_5_the_chain_is_flat(chain):
    """PID line 82: no chain-of-chain. Inputs are atomic references only, and
    none carries a nested primitive or a chain identity."""
    for item in chain["inputs"]:
        assert "primitive" not in item
        assert "inputs" not in item
        assert "chain_id" not in item
    assertions = chain["composition_assertions"]
    assert assertions["inputs_are_atomic_only"] is True
    assert assertions["no_chain_of_chain"] is True
    assert assertions["component_identity_preserved"] is True


def test_criterion_5_the_chain_carries_both_required_roles(chain):
    roles = {item["timeframe_role"] for item in chain["inputs"]}
    assert roles == {"CONTEXT", "TRIGGER"}


def test_criterion_5_neither_role_is_optional(chain):
    """The primitive is defined as the conjunction of the two roles, so
    neither may be skipped (docs/COMPOSITION-DOCTRINE.md section 3)."""
    for item in chain["inputs"]:
        assert item.get("optional") is not True


def test_criterion_5_input_handles_are_unique(chain):
    handles = [item["input_id"] for item in chain["inputs"]]
    assert len(handles) == len(set(handles))


def test_criterion_5_the_chain_explains_match_and_non_match(chain):
    """PID line 80: an explicit reason for match AND non-match, attributed
    per input. A non-match with no reason is unauditable."""
    contract = chain["explanation_contract"]
    assert contract["emit_reason_on_match"] is True
    assert contract["emit_reason_on_non_match"] is True
    assert contract["per_input_evaluation_reported"] is True
    assert contract["reason_fields"]


# --- criterion 6: semantic timeframe roles -----------------------------------


def test_criterion_6_roles_map_to_this_strategys_chosen_timeframes(package, chain):
    """PID criterion 6, and PID line 93: these are semantic ROLES, not
    hard-coded universal timeframes. 4H/5M is this strategy's mapping; the
    role names are what is canonical."""
    assert package["timeframe_roles"] == {"CONTEXT": "4H", "TRIGGER": "5M"}
    assert chain["timeframe_roles"] == package["timeframe_roles"]


def test_criterion_6_role_names_come_from_the_canonical_set(package):
    """The role vocabulary is closed (PID lines 84-97); the timeframes are
    not. This asserts the half that is fixed."""
    canonical = {"CONTEXT", "LOCATION", "CONFIRMATION", "TRIGGER"}
    assert set(package["timeframe_roles"]) <= canonical


def test_criterion_6_the_context_is_strictly_higher_than_the_trigger(chain):
    """The semantic heart of CONTEXT_TRIGGER. A 5M context over a 4H trigger
    validates structurally while inverting the entire model of PID lines
    84-97, so the comparison is made explicitly here in minutes."""
    by_role = {item["timeframe_role"]: item for item in chain["inputs"]}
    context_minutes = timeframe_minutes(by_role["CONTEXT"]["timeframe"])
    trigger_minutes = timeframe_minutes(by_role["TRIGGER"]["timeframe"])

    assert context_minutes == 240
    assert trigger_minutes == 5
    assert context_minutes > trigger_minutes


def test_criterion_6_each_input_runs_on_the_timeframe_its_role_maps_to(chain):
    roles = chain["timeframe_roles"]
    for item in chain["inputs"]:
        assert item["timeframe"] == roles[item["timeframe_role"]]


def test_criterion_6_each_input_runs_on_the_timeframe_its_atomic_declares(
    chain, catalogue
):
    """A stronger claim than the role model alone: the catalogue entry for
    each input declares the timeframe its HERMES facts are drawn on, and the
    chain must run it there rather than silently relocating it."""
    for item in chain["inputs"]:
        entry = catalogue.get(item["strategy_id"], item["strategy_version"])
        declared = {field["timeframe"] for field in entry["required_hermes_fields"]}
        assert declared == {item["timeframe"]}


# --- criterion 7: timing, direction, persistence, expiry ---------------------


def test_criterion_7_direction_semantics_are_defined(package):
    """PID criterion 7. Direction is taken from the context and the trigger
    must agree; composing a LONG context with a SHORT trigger is a non-match,
    not a match, and that is only decidable if both express direction."""
    direction = package["direction_semantics"]
    assert direction["emits"] == ["LONG", "SHORT"]
    assert direction["inversion_allowed"] is False
    assert direction["direction_rule"].strip()


def test_criterion_7_the_context_supplies_direction_and_the_trigger_inherits(chain):
    by_role = {item["timeframe_role"]: item for item in chain["inputs"]}
    assert by_role["CONTEXT"]["direction"] == "EITHER"
    assert by_role["TRIGGER"]["direction"] == "INHERIT"


def test_criterion_7_timing_is_defined(package):
    timing = package["timing"]
    assert timing["evaluation_trigger"] == "BAR_CLOSE"
    assert timing["evaluation_timeframe"] == "5M"


def test_criterion_7_the_chain_is_evaluated_on_the_trigger_timeframe(package):
    """The chain reads the latched context on every trigger bar, so it is
    evaluated on the lower of the two timeframes."""
    assert package["timing"]["evaluation_timeframe"] == package["timeframe_roles"]["TRIGGER"]


def test_criterion_7_a_context_trigger_chain_declares_no_sequence_window(package):
    """sequence_window belongs to SEQUENCE. Here the horizon over which the
    context stays usable is expiry, and conflating the two would state the
    same rule twice in two places."""
    assert "sequence_window" not in package["timing"]


def test_criterion_7_persistence_is_defined(package):
    persistence = package["persistence"]
    assert persistence["signal_persists"] is False
    assert persistence["persist_for_bars"] == 0
    assert persistence["persist_timeframe"]
    assert persistence["re_arm_rule"].strip()


def test_criterion_7_expiry_is_defined_with_a_measurable_horizon(package):
    """An expiry without a bar count is exactly the discretionary language
    HSA refuses (PID lines 110-120), so the horizon is stated in bars of a
    named timeframe."""
    expiry = package["expiry"]
    assert expiry["expires"] is True
    assert expiry["expires_after_bars"] == 30
    assert expiry["expiry_timeframe"] == "4H"
    assert expiry["expiry_rule"].strip()


def test_criterion_7_the_expiry_horizon_is_counted_on_the_context_timeframe(package):
    """Thirty bars means thirty of something. Counting the latched context's
    age on the TRIGGER timeframe would shorten it by a factor of 48."""
    assert package["expiry"]["expiry_timeframe"] == package["timeframe_roles"]["CONTEXT"]


def test_criterion_7_the_expiry_horizon_matches_its_governing_parameter(package):
    """context_window_bars is the declared, bounded parameter; expiry states
    the same number. Two statements of one quantity must agree."""
    parameter = {p["name"]: p for p in package["parameters"]}["context_window_bars"]
    assert parameter["default"] == package["expiry"]["expires_after_bars"]
    assert parameter["units"] == "bars"
    domain = parameter["allowed_range"]
    assert domain["minimum"] <= parameter["default"] <= domain["maximum"]


def test_criterion_7_state_semantics_are_defined(package):
    """A CONTEXT_TRIGGER chain latches its context, and undeclared state is
    state HELIOS would have to invent for itself."""
    state = package["state_semantics"]
    assert state["stateful"] is True
    assert state["initial_state"] == "IDLE"
    assert state["initial_state"] in state["states"]
    assert state["state_transition_rule"].strip()
    assert state["reset_conditions"]


def test_criterion_7_the_package_and_its_chain_state_the_same_semantics(package, chain):
    """PID lines 135-137: the package is authoritative and the chain restates
    it operationally. Disagreement hands FORGE two specifications and no way
    to choose."""
    for section in (
        "direction_semantics",
        "timing",
        "persistence",
        "expiry",
        "state_semantics",
        "timeframe_roles",
    ):
        assert package[section] == chain[section], section


# --- criterion 8: HERMES mapping ---------------------------------------------


def test_criterion_8_every_required_input_maps_to_a_hermes_field(package):
    """PID criterion 8. Each entry names the field, why it is needed, and the
    timeframe it is drawn on."""
    fields = package["required_hermes_fields"]
    assert fields
    for entry in fields:
        assert entry["field"]
        assert entry["purpose"].strip()
        assert entry["timeframe"]


def test_criterion_8_the_package_level_list_covers_every_atomics_needs(package):
    """PID line 132: the package-level list is stated once so FORGE can
    provision inputs without walking the atomics, which is only true if it is
    a superset of what they consume."""
    declared = {(e["field"], e["timeframe"]) for e in package["required_hermes_fields"]}
    for atomic in package["atomic_strategies"]:
        for entry in atomic["required_hermes_fields"]:
            assert (entry["field"], entry["timeframe"]) in declared, (
                "%s needs %s on %s, which the package does not declare"
                % (atomic["strategy_id"], entry["field"], entry["timeframe"])
            )


def test_criterion_8_the_package_declares_no_field_no_atomic_uses(package):
    """The other direction. A package-level field nothing consumes is an
    input FORGE would provision for no reason."""
    consumed = set()
    for atomic in package["atomic_strategies"]:
        for entry in atomic["required_hermes_fields"]:
            consumed.add((entry["field"], entry["timeframe"]))
    for entry in package["required_hermes_fields"]:
        assert (entry["field"], entry["timeframe"]) in consumed


def test_criterion_8_hermes_fields_are_drawn_on_both_role_timeframes(package):
    """A multi-timeframe strategy that drew every fact from one timeframe
    would not be multi-timeframe."""
    timeframes = {e["timeframe"] for e in package["required_hermes_fields"]}
    assert timeframes == {"4H", "5M"}


def test_the_package_carries_no_account_or_broker_state(package):
    """PID line 156: HSA must not embed runtime trading state or
    broker/account knowledge into a HELIOS specification."""
    rendered = json.dumps(package).lower()
    for forbidden in (
        "account_balance",
        "broker",
        "order_id",
        "position_size",
        "lot_size",
        "equity_curve",
        "margin_level",
    ):
        assert forbidden not in rendered


# --- criterion 11: deterministic tests and evidence requirements -------------


def test_criterion_11_the_package_carries_deterministic_test_cases(package):
    """PID criterion 11, and PID line 49: determinism is a claim until it is
    pinned by cases."""
    cases = package["deterministic_test_cases"]
    assert len(cases) >= 4
    for case in cases:
        assert case["case_id"]
        assert case["description"].strip()
        assert case["given_hermes_facts"]
        assert case["expected_output"]


def test_criterion_11_case_ids_are_unique(package):
    ids = [case["case_id"] for case in package["deterministic_test_cases"]]
    assert len(ids) == len(set(ids))


def test_criterion_11_the_cases_include_a_match_and_several_non_matches(package):
    """A package whose cases all match has not been shown to discriminate."""
    outcomes = [
        case["expected_output"].get("matched")
        for case in package["deterministic_test_cases"]
    ]
    assert True in outcomes
    assert outcomes.count(False) >= 3


def test_criterion_11_the_cases_prove_the_context_gate_actually_gates(package):
    """The three ways the gate can refuse — no context, expired context,
    disagreeing direction — each have a case, because those are exactly the
    behaviours that distinguish this chain from an ungated breakout."""
    cases = {c["case_id"]: c for c in package["deterministic_test_cases"]}

    for case_id in (
        "long_context_with_downward_break_does_not_match",
        "upward_break_without_latched_context_does_not_match",
        "expired_context_with_upward_break_does_not_match",
    ):
        assert cases[case_id]["expected_output"]["matched"] is False

    assert cases["long_context_then_upward_break_matches"]["expected_output"][
        "matched"
    ] is True


def test_criterion_11_the_gating_cases_share_the_matching_cases_trigger_facts(package):
    """The non-match cases are only evidence that the CONTEXT does the work
    if the TRIGGER facts are identical to the matching case's. Otherwise they
    would prove the trigger failed, not that the gate held."""
    cases = {c["case_id"]: c for c in package["deterministic_test_cases"]}
    trigger_keys = ("5M:range.high", "5M:range.low", "5M:candle.close")

    matching = cases["long_context_then_upward_break_matches"]["given_hermes_facts"]
    baseline = {key: matching[key] for key in trigger_keys}

    for case_id in (
        "upward_break_without_latched_context_does_not_match",
        "expired_context_with_upward_break_does_not_match",
    ):
        facts = cases[case_id]["given_hermes_facts"]
        assert {key: facts[key] for key in trigger_keys} == baseline


def test_criterion_11_evidence_requirements_are_stated(package):
    """PID line 143. Stated BEFORE evidence is gathered, which is what stops
    thresholds moving to fit a result."""
    requirements = package["evidence_requirements"]
    assert requirements["backtest_requirements"]
    assert requirements["minimum_sample_size"] >= 1
    assert requirements["required_cer_evidence_types"]


def test_criterion_11_acceptance_and_rejection_criteria_are_machine_evaluable(package):
    """PID line 144. Prose alone is not sufficient: FORGE and CER must be
    able to evaluate these without interpretation."""
    for group in ("acceptance_criteria", "rejection_criteria"):
        criteria = package[group]
        assert criteria, group
        for criterion in criteria:
            assert criterion["criterion_id"]
            assert criterion["statement"].strip()
            assert criterion["metric"].strip()
            assert criterion["comparator"] in (">=", "<=", ">", "<", "==", "!=")
            assert criterion["threshold"] is not None


def test_criterion_11_the_strategy_has_a_stated_way_to_fail(package):
    """A strategy with no stated way to fail cannot be governed by evidence.
    The rejection criteria must be able to fire on the same metrics the
    acceptance criteria read, or they are decoration."""
    accepted = {c["metric"] for c in package["acceptance_criteria"]}
    rejected = {c["metric"] for c in package["rejection_criteria"]}
    assert accepted & rejected


def test_criterion_11_the_thesis_can_be_falsified_by_a_control_arm(package):
    """The economic claim is specifically that the CONTEXT adds information.
    That is only testable against an ungated control, so the requirement and
    a rejection criterion that reads it must both exist."""
    backtests = " ".join(package["evidence_requirements"]["backtest_requirements"])
    assert "control arm" in backtests

    metrics = {c["metric"] for c in package["rejection_criteria"]}
    assert "expectancy_uplift_over_ungated_control_r_multiple" in metrics


# --- criterion 12: CER semantics ---------------------------------------------


def test_criterion_12_the_package_carries_cer_references(package):
    """PID criterion 12: use and target CER identities and evidence
    semantics."""
    references = package["cer_references"]
    assert references
    for reference in references:
        assert validate_reference(reference) == reference


def test_criterion_12_evidence_json_references_all_validate(evidence):
    """Every entry in the inventory-local evidence index is a full
    cer_reference document in its own right."""
    references = evidence["references"]
    assert len(references) >= 3
    for reference in references:
        assert validate_document(reference, kind="cer_reference") == "cer_reference"


def test_criterion_12_evidence_covers_source_analysis_hypothesis_and_lineage(evidence):
    """The three a package always has before any run exists (PID lines
    175-179)."""
    present = {reference["reference_type"] for reference in evidence["references"]}
    assert {"SOURCE_ANALYSIS", "STRATEGY_HYPOTHESIS", "VERSION_LINEAGE"} <= present


def test_criterion_12_every_reference_is_anchored_to_this_strategy_version(evidence):
    """An evidence reference not anchored to a specific immutable version is
    not attributable to anything (PID lines 166-171)."""
    for reference in evidence["references"]:
        assert reference["strategy_id"] == STRATEGY_ID
        assert reference["strategy_version"] == STRATEGY_VERSION


def test_criterion_12_every_reference_names_at_least_one_cer_identity(evidence):
    """A reference naming a strategy but no evidence is not a reference."""
    for reference in evidence["references"]:
        opaque = ("experiment_id", "run_id", "evidence_id", "artifact_id")
        assert any(key in reference for key in opaque)


def test_criterion_12_every_reference_is_labelled_a_contract_fixture(evidence):
    """CER is not live (PID line 181). A fixture mistaken for live evidence
    is the failure this labelling exists to prevent, so it is asserted rather
    than assumed."""
    for reference in evidence["references"]:
        assert reference["source"] == SOURCE_CONTRACT_FIXTURE
        assert is_fixture(reference)


def test_criterion_12_fixture_identities_are_visibly_fixtures(evidence):
    """The second, independent signal: CER-minted identities are prefixed
    FIXTURE- so a reference read out of context still cannot pass for live."""
    for reference in evidence["references"]:
        for key in ("experiment_id", "run_id", "evidence_id", "artifact_id"):
            if key in reference:
                assert reference[key].startswith("FIXTURE-")


def test_criterion_12_the_evidence_index_is_not_a_contract_kind(evidence):
    """evidence.json is an inventory convention, not a new HSA contract. It
    carries no $hsa_kind, so no tool routes it to a schema it was never meant
    to satisfy, and it cannot become a parallel evidence store by accretion."""
    assert "$hsa_kind" not in evidence
    assert evidence["document_type"] == "hsa_strategy_evidence_index"
    assert evidence["cer_status"] == "NOT_LIVE"


def test_criterion_12_the_evidence_index_agrees_with_the_package(evidence, package):
    indexed = {r["reference_type"] for r in evidence["references"]}
    embedded = {r["reference_type"] for r in package["cer_references"]}
    assert embedded <= indexed
    assert evidence["strategy_id"] == package["strategy_id"]
    assert evidence["strategy_version"] == package["strategy_version"]


def test_criterion_12_the_required_evidence_types_are_canonical(package):
    canonical = {
        "SOURCE_ANALYSIS",
        "STRATEGY_HYPOTHESIS",
        "VERSION_LINEAGE",
        "RESEARCH_FINDING",
        "PROMOTION_EVIDENCE",
        "REVISION_EVIDENCE",
        "REJECTION_EVIDENCE",
    }
    required = set(package["evidence_requirements"]["required_cer_evidence_types"])
    assert required <= canonical


# --- provenance and UTC ------------------------------------------------------


def test_provenance_traces_back_to_the_packaged_source(package):
    """PID line 145: an artefact whose origin cannot be named is not
    governed."""
    provenance = package["provenance"]
    assert provenance["source_type"] == "TRADER_EXPLANATION"
    assert provenance["source_reference"] == "strategies/gold_context_breakout/1.0.0/source.txt"
    assert provenance["ingested_at_utc"].endswith("Z")


def test_the_provenance_excerpt_appears_in_the_source(package):
    """An excerpt that is not in the source is not an excerpt."""
    source = " ".join(SOURCE_PATH.read_text(encoding="utf-8").split())
    excerpt = " ".join(package["provenance"]["excerpt"].split())
    assert excerpt in source


def test_the_chain_provenance_excerpt_appears_in_the_source(chain):
    source = " ".join(SOURCE_PATH.read_text(encoding="utf-8").split())
    excerpt = " ".join(chain["provenance"]["excerpt"].split())
    assert excerpt in source


def test_every_timestamp_in_the_package_is_utc(package):
    """PID line 225: UTC everywhere. Local time is display-only and never
    reaches a document."""
    stamps = [
        package["provenance"]["ingested_at_utc"],
        package["chain"]["provenance"]["ingested_at_utc"],
        package["lifecycle"]["created_at_utc"],
    ]
    stamps += [atomic["provenance"]["ingested_at_utc"] for atomic in package["atomic_strategies"]]
    stamps += [reference["recorded_at_utc"] for reference in package["cer_references"]]
    for stamp in stamps:
        assert stamp.endswith("Z"), stamp
        assert "+" not in stamp


def test_every_timestamp_in_the_evidence_index_is_utc(evidence):
    assert evidence["generated_at_utc"].endswith("Z")
    for reference in evidence["references"]:
        assert reference["recorded_at_utc"].endswith("Z")
