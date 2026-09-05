"""PID acceptance Example B — the ordered price-action sequence (PID line 242).

    large 15m rejection wick -> subsequent no-wick directional confirmation
    -> optional lower-timeframe trigger

This module proves that Example B passes as a *governed package produced by
HSA's own pipeline*, not as a document hand-authored to fit. Every test names
the PID acceptance criterion (PID lines 248-262) it proves, by number.

The sharp point of Example B is PID line 114 against PID line 242. Line 114
lists "large wick" among the phrases HSA must never guess; line 242 builds
this example on that exact phrase and line 288 requires it to pass. The
ratified resolution is ``docs/AMBIGUITY-POLICY.md``: parameterise when the
measurement basis is known and only the threshold is unset, refuse when the
basis is itself undefined. ``test_criterion_3_*`` proves BOTH sides of that
boundary on the real analyser — the parameterisation is attributed, and a
term whose basis is undefined still refuses. A test that only proved the
first half would be proving that HSA guesses.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from hsa.cer import validate_reference
from hsa.contracts import validate_document
from hsa.semantics import Catalogue, check_chain, check_package
from hsa.versioning import lineage

REPO_ROOT = Path(__file__).resolve().parent.parent

STRATEGY_ID = "wick_rejection_sequence"
STRATEGY_VERSION = "0.1.0"

PACKAGE_DIR = REPO_ROOT / "strategies" / STRATEGY_ID / STRATEGY_VERSION
PACKAGE_PATH = PACKAGE_DIR / "package.json"
SOURCE_PATH = PACKAGE_DIR / "source.txt"
EVIDENCE_PATH = PACKAGE_DIR / "evidence.json"

INTAKE_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "intake" / "example_b_wick_rejection_sequence.txt"
)
#: W2C's fixture, read only. It is the negative control for criterion 3.
REFUSAL_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "intake" / "near_resistance_pullback.txt"
)

RULING_DOCUMENT = "docs/AMBIGUITY-POLICY.md"

#: Exit codes owned by ``hsa/cli.py`` and ``hsa/commands/intake.py``.
EXIT_OK = 0
EXIT_NOT_SUFFICIENTLY_DEFINED = 4


def _load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _run(*args: str) -> subprocess.CompletedProcess:
    """Run the real shipped CLI in a real process from the repository root."""
    return subprocess.run(
        [sys.executable, "-m", "hsa.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="module")
def package() -> dict:
    return _load(PACKAGE_PATH)


@pytest.fixture(scope="module")
def chain(package) -> dict:
    return package["chain"]


@pytest.fixture(scope="module")
def evidence() -> dict:
    return _load(EVIDENCE_PATH)


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    return Catalogue.from_directory(REPO_ROOT / "catalogue" / "atomic")


@pytest.fixture(scope="module")
def intake_draft() -> dict:
    """The draft the SHIPPED analyser produces from the raw source.

    Produced by running ``hsa intake`` in a real process, so this fixture
    fails if the pipeline the package claims to have come through does not
    actually work.
    """
    result = _run(
        "intake",
        str(INTAKE_FIXTURE.relative_to(REPO_ROOT)),
        "--source-type",
        "TRADER_EXPLANATION",
        "--quiet",
    )
    assert result.returncode == EXIT_OK, result.stderr
    return json.loads(result.stdout)


# --- the inventory layout ----------------------------------------------------


def test_inventory_layout_is_the_canonical_three_files():
    """package.json, source.txt and evidence.json, under id/version."""
    assert PACKAGE_PATH.is_file()
    assert SOURCE_PATH.is_file()
    assert EVIDENCE_PATH.is_file()
    assert sorted(p.name for p in PACKAGE_DIR.iterdir()) == [
        "evidence.json",
        "package.json",
        "source.txt",
    ]


def test_package_directory_path_states_the_same_identity_as_the_package(package):
    """The path is not decoration: id and version are load-bearing (PID 72)."""
    assert PACKAGE_DIR.parent.name == package["strategy_id"] == STRATEGY_ID
    assert PACKAGE_DIR.name == package["strategy_version"] == STRATEGY_VERSION


# --- criterion 2: ingest a realistic raw strategy description ----------------


def test_criterion_2_raw_source_is_unsanitised_trader_prose():
    """PID line 251. The input must contain the discretionary language.

    A pre-sanitised source would make criteria 2 and 3 unfalsifiable: there
    would be nothing to resolve and nothing to refuse.
    """
    raw = SOURCE_PATH.read_text(encoding="utf-8")
    assert "large 15m rejection wick" in raw
    assert "no-wick directional confirmation" in raw
    assert "optional" in raw
    # It is prose, not a specification: no thresholds were written into it.
    assert "0.6" not in raw and "ratio" not in raw


def test_criterion_2_the_intake_fixture_is_the_governed_source_verbatim():
    """The pipeline was run on this exact source, not on a cleaned-up copy."""
    assert INTAKE_FIXTURE.read_text(encoding="utf-8") == SOURCE_PATH.read_text(
        encoding="utf-8"
    )


def test_criterion_2_intake_produces_a_draft_not_a_refusal(intake_draft):
    """PID line 251, through the shipped analyser in a real process."""
    assert intake_draft["result"] == "STRATEGY_INTAKE_DRAFT"
    assert intake_draft["provenance"]["source_type"] == "TRADER_EXPLANATION"


# --- criterion 3: identify ambiguity rather than guessing --------------------


def test_criterion_3_both_discretionary_terms_are_parameterised_with_attribution(
    intake_draft,
):
    """PID line 252 and docs/AMBIGUITY-POLICY.md, 'Attribution'.

    The claim under test is not "a number appeared". It is that the number
    is *declared, bounded, attributed and revisable* — which is the policy's
    own stated difference between a parameter and a guess made quietly.
    """
    resolved = {term["term_id"]: term for term in intake_draft["resolved_terms"]}
    assert set(resolved) == {"large_wick", "no_wick_candle"}

    for term_id in ("large_wick", "no_wick_candle"):
        term = resolved[term_id]
        resolution = term["resolution"]
        assert resolution["disposition"] == "PARAMETERISED"
        # Not ``hsa_guessed: false``. That single boolean asserted both that
        # the basis came from a ruling (checked) and that the source agreed
        # with it (never checked). The two are separated now, and only the
        # first is claimed outright.
        assert "hsa_guessed" not in resolution
        assert resolution["basis_authority"] == "RATIFIED_LEXICON_RULING"
        assert resolution["hsa_invented_basis"] is False
        assert resolution["source_basis_agreement"] == "NOT_VERIFIED"
        scan = resolution["basis_conflict_scan"]
        # NO_ATTACHED_REBASING_FOUND, not NO_DECLARED_REBASING_FOUND: the
        # guard is precision-tuned and deliberately passes over declared
        # qualifiers that attach to something other than the ruled
        # measurement, so the stamp names what was actually established.
        assert scan["result"] == "NO_ATTACHED_REBASING_FOUND"
        assert scan["qualifiers_declared"] > 0
        assert term["source_language"] in scan["inspected_text"]
        assert scan["attachment_rule"].strip()
        assert isinstance(scan["declared_qualifiers_seen_unattached"], list)
        assert resolution["authority"] == "HUMAN_ARCHITECT_RULING"
        assert resolution["ruling_document"] == RULING_DOCUMENT
        assert resolution["lexicon_term"] == term_id
        assert resolution["lexicon_version"]
        assert resolution["default_status"] == "PROVISIONAL_PENDING_EVIDENCE"
        # The basis is named in words, and the source language is quoted
        # verbatim with its location, so the resolution is auditable back to
        # the sentence that caused it.
        assert term["measurement_basis"]
        assert term["basis_rationale"]
        assert term["source_language"]
        assert term["location"]
        assert term["declared_parameters"]


def test_criterion_3_the_quoted_source_language_really_is_in_the_source(intake_draft):
    """Attribution is worthless if the quoted phrase is not the source's."""
    raw = SOURCE_PATH.read_text(encoding="utf-8")
    for term in intake_draft["resolved_terms"]:
        assert term["source_language"] in raw


def test_criterion_3_every_declared_parameter_is_bounded(intake_draft):
    """PID line 140: a parameter carries a default, a range and units."""
    declared = {parameter["name"]: parameter for parameter in intake_draft["parameters"]}
    for term in intake_draft["resolved_terms"]:
        for name in term["declared_parameters"]:
            parameter = declared[name]
            assert parameter["units"]
            bounds = parameter["allowed_range"]
            assert bounds["minimum"] <= parameter["default"] <= bounds["maximum"]
            assert bounds["minimum"] < bounds["maximum"]


def test_criterion_3_nothing_recognised_was_left_unruled(intake_draft):
    """A draft is only honest if no recognised term slipped through."""
    assert intake_draft["advisory_items"] == []
    # And the analyser still states its own limits rather than claiming the
    # description is proven unambiguous.
    assert intake_draft["analyser_limits"]


def test_criterion_3_a_term_whose_basis_is_undefined_still_refuses():
    """PID line 252, the other half of the boundary — the negative control.

    Parameterising "large wick" is only a ruling, rather than a blanket
    pass, if the same analyser still refuses a term whose measurement basis
    is undefined. Without this test, Example B would demonstrate that HSA
    resolves everything, which is exactly what PID line 39 forbids.
    """
    result = _run(
        "intake",
        str(REFUSAL_FIXTURE.relative_to(REPO_ROOT)),
        "--source-type",
        "TRADER_EXPLANATION",
        "--quiet",
    )
    assert result.returncode == EXIT_NOT_SUFFICIENTLY_DEFINED, result.stderr
    document = json.loads(result.stdout)
    assert document["$hsa_kind"] == "not_sufficiently_defined"
    validate_document(document, kind="not_sufficiently_defined")


def test_criterion_3_package_provenance_carries_the_attribution(package):
    """The resolution must survive into the governed artefact.

    An attribution that exists only in a transient intake draft is not
    durable authority (PID line 206). FORGE reads the package.
    """
    notes = package["provenance"]["notes"]
    for expected in (
        "PARAMETERISED",
        "HUMAN_ARCHITECT_RULING",
        RULING_DOCUMENT,
        "hsa_guessed false",
        "PROVISIONAL_PENDING_EVIDENCE",
        "large_wick",
        "no_wick_candle",
    ):
        assert expected in notes, expected
    assert package["provenance"]["source_reference"].endswith("source.txt")


def test_criterion_3_the_packages_thresholds_match_the_ruled_intake_defaults(
    package, intake_draft
):
    """The package did not quietly move the number the ruling produced.

    The lexicon and the catalogue name the same ratified basis differently
    (``min_wick_to_range_ratio`` against ``wick_to_range_ratio_min``), so
    this asserts on the VALUE, which is what a silent guess would change.
    """
    intake_defaults = {
        parameter["name"]: parameter["default"]
        for parameter in intake_draft["parameters"]
    }
    atomics = {
        atomic["strategy_id"]: atomic for atomic in package["atomic_strategies"]
    }
    carried = {
        ("rejection_wick", "wick_to_range_ratio_min"): "min_wick_to_range_ratio",
        ("no_wick_candle", "wick_to_range_ratio_max"): "max_wick_to_range_ratio",
    }
    for (strategy_id, package_name), intake_name in carried.items():
        parameters = {
            parameter["name"]: parameter
            for parameter in atomics[strategy_id]["parameters"]
        }
        parameter = parameters[package_name]
        assert parameter["default"] == intake_defaults[intake_name]
        bounds = parameter["allowed_range"]
        assert bounds["minimum"] <= parameter["default"] <= bounds["maximum"]


def test_criterion_3_the_provisional_defaults_are_required_to_be_evidenced(package):
    """The policy's honest part, enforced: a default is not a result.

    docs/AMBIGUITY-POLICY.md ratifies the measurement basis, NOT the value.
    A default that shipped unchanged and unevidenced into a promoted version
    would be a guess wearing a parameter's clothes, so the package must
    demand evidence for it before promotion.
    """
    requirements = " ".join(package["evidence_requirements"]["backtest_requirements"])
    assert "wick_to_range_ratio_min" in requirements
    assert "wick_to_range_ratio_max" in requirements
    assert "allowed_range" in requirements

    criteria = {c["criterion_id"] for c in package["acceptance_criteria"]}
    assert "wick_ratio_default_evidenced" in criteria
    assert "no_wick_ratio_default_evidenced" in criteria

    assert package["lifecycle"]["status"] == "CANDIDATE"


# --- criterion 4: decompose into independent atomic strategies ---------------


def test_criterion_4_every_chain_input_resolves_in_the_catalogue(chain, catalogue):
    """PID line 253. No input may name a strategy that does not exist."""
    assert chain["inputs"]
    for item in chain["inputs"]:
        entry = catalogue.get(item["strategy_id"], item["strategy_version"])
        assert entry is not None, (item["strategy_id"], item["strategy_version"])
        assert entry["strategy_version"] == item["strategy_version"]


def test_criterion_4_no_catalogue_entry_was_added_for_this_example(catalogue):
    """Example B is a proof of the shipped system, not an extension of it."""
    assert {"rejection_wick", "no_wick_candle", "range_breakout"} <= set(catalogue.ids)
    assert STRATEGY_ID not in catalogue.ids


def test_criterion_4_embedded_atomics_are_the_catalogue_entries_verbatim(
    package, catalogue
):
    """Self-containment must not become divergence.

    The package embeds full atomic definitions so FORGE implements from one
    document. If an embedded copy drifted from the catalogue entry, the
    chain would pin a version whose meaning differs from the version the
    evidence was gathered against.
    """
    for atomic in package["atomic_strategies"]:
        entry = catalogue.get(atomic["strategy_id"], atomic["strategy_version"])
        assert entry == atomic, atomic["strategy_id"]


def test_criterion_4_atomics_are_independent_of_each_other(package):
    """PID lines 52, 59. Enforced structurally; asserted here as well."""
    identities = {atomic["strategy_id"] for atomic in package["atomic_strategies"]}
    for atomic in package["atomic_strategies"]:
        assert atomic["doctrine_assertions"]["unaware_of_other_strategies"] is True
        assert atomic["doctrine_assertions"]["independently_testable"] is True
        assert atomic["doctrine_assertions"]["deterministic"] is True
        assert atomic["doctrine_assertions"]["execution_blind"] is True
        # No atomic may name a peer anywhere in its own document.
        serialised = json.dumps(atomic)
        for peer in identities - {atomic["strategy_id"]}:
            assert peer not in serialised, (atomic["strategy_id"], peer)
        # And each is independently testable in fact, not only by assertion.
        assert len(atomic["deterministic_test_cases"]) >= 2


# --- criterion 5: an explicit chain using canonical primitives ---------------


def test_criterion_5_the_primitive_is_sequence(chain):
    """PID line 254. SEQUENCE is the primitive Example B exists to exercise."""
    assert chain["primitive"] == "SEQUENCE"


def test_criterion_5_sequence_indices_are_contiguous_from_one(chain):
    """A gap or a repeat leaves the order undetermined (PID line 75)."""
    indices = [item["sequence_index"] for item in chain["inputs"]]
    assert indices == list(range(1, len(chain["inputs"]) + 1))
    assert len(set(indices)) == len(indices)


def test_criterion_5_the_steps_are_in_the_order_the_pid_describes(chain):
    """PID line 242, step by step."""
    ordered = sorted(chain["inputs"], key=lambda item: item["sequence_index"])
    assert [item["strategy_id"] for item in ordered] == [
        "rejection_wick",
        "no_wick_candle",
        "range_breakout",
    ]


def test_criterion_5_a_sequence_window_is_declared(chain, package):
    """The schema makes the window mandatory for SEQUENCE; check it is real."""
    window = chain["timing"]["sequence_window"]
    assert window["max_bars"] >= 1
    assert window["timeframe"] == chain["timing"]["evaluation_timeframe"]
    assert window == package["timing"]["sequence_window"]


def test_criterion_5_the_chain_is_flat(chain):
    """PID line 82: one top-level primitive, atomic inputs only."""
    assert chain["composition_assertions"] == {
        "inputs_are_atomic_only": True,
        "component_identity_preserved": True,
        "no_chain_of_chain": True,
    }
    for item in chain["inputs"]:
        assert "primitive" not in item
        assert "inputs" not in item
        assert "chain_id" not in item


def test_criterion_5_every_input_pins_an_exact_version(chain):
    """PID line 72: identity is id AND version, never id alone."""
    for item in chain["inputs"]:
        assert item["strategy_id"]
        assert item["strategy_version"]


def test_criterion_5_the_chain_explains_match_and_non_match(package, chain, catalogue):
    """PID line 80. A non-match with no reason is unauditable.

    The four assertions this test used to make were all guaranteed by the
    frozen schema — three ``const: true`` flags and a truthiness check on an
    array already ``minItems: 1`` — so nothing here could fail. Meanwhile this
    package declared ``reason_fields: ["reason"]``, naming none of its three
    ``input_id``s while asserting ``per_input_evaluation_reported: true``.
    """
    contract = chain["explanation_contract"]
    # The three flags above are const true in the frozen chain schema, so
    # asserting them proves nothing a validated document could ever fail —
    # and reason_fields is minItems 1, so a truthiness check on it is the
    # same. What the schema CANNOT check, and what these packages had
    # actually got wrong, is whether those field names name anything.
    emitted = {field["name"] for field in package["output_contract"]["fields"]}
    atomics = {
        (atomic["strategy_id"], atomic["strategy_version"]): {
            field["name"] for field in atomic["output_contract"]["fields"]
        }
        for atomic in package["atomic_strategies"]
    }
    handles = {item["input_id"]: item for item in chain["inputs"]}

    # Every input is attributed, by its own handle. "The chain did not match"
    # is not a reason (docs/COMPOSITION-DOCTRINE.md).
    for input_id, item in handles.items():
        entry = "%s.reason" % input_id
        assert entry in contract["reason_fields"], input_id
        key = (item["strategy_id"], item["strategy_version"])
        assert "reason" in atomics[key], key

    # And every declared field binds to something real.
    for entry in contract["reason_fields"]:
        if "." in entry:
            handle, field = entry.split(".", 1)
            assert handle in handles, entry
            item = handles[handle]
            assert field in atomics[(item["strategy_id"], item["strategy_version"])]
        else:
            assert entry in emitted, entry

    # The chain-level reason is one the output contract promises to emit.
    assert package["output_contract"]["reason_field"] in contract["reason_fields"]

    # Finally the shipped check agrees, so this cannot pass here and fail in
    # the tool a fresh boot actually runs.
    findings = check_package(package, catalogue=catalogue)
    assert [
        finding
        for finding in findings
        if finding.check
        in ("package.reason_fields_bound", "chain.reason_fields_attribute_inputs")
    ] == []


# --- the optional lower-timeframe trigger (PID line 242) ---------------------


def test_the_optional_input_is_the_lower_timeframe_trigger(chain):
    """PID line 242's 'optional lower-timeframe trigger', located exactly."""
    optional = [item for item in chain["inputs"] if item.get("optional") is True]
    assert len(optional) == 1
    step = optional[0]
    assert step["timeframe_role"] == "TRIGGER"
    assert step["sequence_index"] == max(
        item["sequence_index"] for item in chain["inputs"]
    )
    # It is genuinely the LOWER timeframe of the chain.
    others = [item for item in chain["inputs"] if item is not step]
    assert all(item["timeframe"] == "15M" for item in others)
    assert step["timeframe"] == "5M"


def test_the_optional_input_cannot_be_the_sole_cause_of_a_match(chain, catalogue):
    """docs/COMPOSITION-DOCTRINE.md section 6, the rule that gives the flag meaning.

    Proved three ways, because the assertion is easy to state and easy to
    fake:

      1. this chain leaves required inputs behind, and the shipped semantic
         engine passes it;
      2. mutating the chain so that nothing is required makes the SAME
         engine emit ``chain.optional_input`` — so the check is live, not
         vacuous;
      3. the package's own deterministic cases say a match happens without
         the optional step and does NOT happen with it alone.
    """
    # 1. As authored, at least one input is required.
    required = [item for item in chain["inputs"] if not item.get("optional")]
    assert required
    assert check_chain(chain, catalogue=catalogue) == []

    # 2. Make every input optional: the engine must object.
    all_optional = copy.deepcopy(chain)
    for item in all_optional["inputs"]:
        item["optional"] = True
    findings = check_chain(all_optional, catalogue=catalogue)
    assert any(finding.check == "chain.optional_input" for finding in findings)

    # 2b. Reduce the chain to the optional input alone: also rejected.
    only_optional = copy.deepcopy(chain)
    only_optional["inputs"] = [
        dict(item, sequence_index=1)
        for item in chain["inputs"]
        if item.get("optional") is True
    ]
    findings = check_chain(only_optional, catalogue=catalogue)
    assert any(finding.check == "chain.optional_input" for finding in findings)


def test_the_deterministic_cases_prove_the_optional_step_is_optional(package):
    """Point 3 of the rule above, in the package's own governed test cases."""
    cases = {case["case_id"]: case for case in package["deterministic_test_cases"]}

    without = cases["sequence_matches_without_optional_trigger"]
    assert without["expected_output"]["matched"] is True
    assert without["expected_output"]["trigger_confirmed"] is False

    alone = cases["optional_trigger_alone_does_not_match"]
    assert alone["expected_output"]["matched"] is False

    with_trigger = cases["sequence_completes_with_optional_trigger"]
    assert with_trigger["expected_output"]["matched"] is True
    assert with_trigger["expected_output"]["trigger_confirmed"] is True


def test_the_match_is_asserted_before_the_optional_step_can_run(package):
    """The state model must place the match on the REQUIRED steps alone.

    If the chain only matched in CONFIRMED_TRIGGERED, the optional step
    would be gating the match and would not be optional at all.
    """
    states = package["state_semantics"]["states"]
    assert "CONFIRMED" in states and "CONFIRMED_TRIGGERED" in states
    assert states.index("CONFIRMED") < states.index("CONFIRMED_TRIGGERED")

    cases = {case["case_id"]: case for case in package["deterministic_test_cases"]}
    without = cases["sequence_matches_without_optional_trigger"]
    assert without["expected_output"]["state"] == "CONFIRMED"
    assert without["expected_output"]["matched"] is True


# --- criterion 6: semantic timeframe roles -----------------------------------


CANONICAL_ROLES = {"CONTEXT", "LOCATION", "CONFIRMATION", "TRIGGER"}


def test_criterion_6_roles_are_canonical_and_timeframes_are_this_chains_choice(package):
    """PID lines 84-97, 255. The ROLE set is closed; the mapping is not."""
    roles = package["timeframe_roles"]
    assert set(roles) <= CANONICAL_ROLES
    assert roles == package["chain"]["timeframe_roles"]
    # This strategy deliberately maps two roles to one timeframe, which is
    # only legal because roles are semantic rather than universal.
    assert roles["LOCATION"] == roles["CONFIRMATION"] == "15M"
    assert roles["TRIGGER"] == "5M"


def test_criterion_6_every_input_agrees_with_the_role_model(chain):
    """A document that says a role is 15M in one place and 5M in another
    states two different things about one role."""
    roles = chain["timeframe_roles"]
    for item in chain["inputs"]:
        assert item["timeframe_role"] in roles
        assert item["timeframe"] == roles[item["timeframe_role"]]


def test_criterion_6_the_package_states_that_roles_are_not_universal_timeframes(
    package,
):
    """PID line 93, stated in the artefact rather than only in doctrine."""
    notes = package["provenance"]["notes"]
    assert "semantic roles, not universal timeframes" in notes
    assert "PID line 93" in notes
    # And the deliberate absence of a CONTEXT role is a recorded decision,
    # not an omission: inventing one would be HSA supplying trading logic.
    assert "CONTEXT" not in package["timeframe_roles"]
    assert "No CONTEXT role is used" in notes


# --- criterion 7: timing, direction, persistence, expiry ---------------------


def test_criterion_7_all_four_are_declared_and_measurable(package):
    """PID line 256."""
    timing = package["timing"]
    assert timing["evaluation_trigger"] == "BAR_CLOSE"
    assert timing["evaluation_timeframe"]

    direction = package["direction_semantics"]
    assert direction["emits"] == ["LONG", "SHORT"]
    assert direction["direction_rule"]
    assert direction["inversion_allowed"] is False

    persistence = package["persistence"]
    assert persistence["signal_persists"] is True
    assert persistence["persist_for_bars"] >= 1
    assert persistence["persist_timeframe"]

    expiry = package["expiry"]
    assert expiry["expires"] is True
    assert expiry["expires_after_bars"] >= 1
    assert expiry["expiry_timeframe"]
    assert expiry["expiry_rule"]


def test_criterion_7_the_evaluation_timeframe_can_see_every_step(package):
    """A 5M step is unobservable on a chain evaluated only on 15M closes."""
    from hsa.semantics import timeframe_minutes

    evaluation = timeframe_minutes(package["timing"]["evaluation_timeframe"])
    for item in package["chain"]["inputs"]:
        step = timeframe_minutes(item["timeframe"])
        assert step % evaluation == 0
        assert step >= evaluation


def test_criterion_7_the_window_budgets_are_arithmetically_consistent(package):
    """The numbers must agree with each other, or FORGE has to pick one."""
    parameters = {p["name"]: p for p in package["parameters"]}
    confirmation = parameters["confirmation_window_bars"]["default"]
    trigger = parameters["trigger_window_bars"]["default"]

    assert package["timing"]["sequence_window"]["max_bars"] == confirmation + trigger
    assert package["persistence"]["persist_for_bars"] == trigger
    assert package["expiry"]["expires_after_bars"] == trigger

    # Every window is counted on one timeframe, so the counts are comparable.
    one = package["timing"]["evaluation_timeframe"]
    assert package["timing"]["sequence_window"]["timeframe"] == one
    assert package["persistence"]["persist_timeframe"] == one
    assert package["expiry"]["expiry_timeframe"] == one


def test_criterion_7_the_ordered_sequence_carries_real_state(package):
    """PID line 137. An ordered sequence is inherently stateful."""
    state = package["state_semantics"]
    assert state["stateful"] is True
    assert state["initial_state"] in state["states"]
    assert len(state["states"]) >= 3
    assert state["state_transition_rule"]
    assert state["reset_conditions"]
    # Partial progress is a named state, not an implementation detail.
    assert "WICK_SEEN" in state["states"]
    # Every state named in the transition rule is a declared state.
    for name in state["states"]:
        assert name in state["state_transition_rule"] or name == state["initial_state"]


def test_criterion_7_an_in_progress_setup_can_be_invalidated(package):
    """A setup that can never be invalidated is not a testable claim."""
    assert package["invalidation_conditions"]
    assert package["validity_conditions"]


# --- criterion 8: map required inputs to HERMES ------------------------------


def test_criterion_8_package_hermes_fields_cover_every_atomic(package):
    """PID lines 132, 257. Stated once at package level, so it must be the
    union of what the atomics consume."""
    declared = {
        (entry["field"], entry.get("timeframe"))
        for entry in package["required_hermes_fields"]
    }
    any_timeframe = {
        entry["field"]
        for entry in package["required_hermes_fields"]
        if entry.get("timeframe") is None
    }
    for atomic in package["atomic_strategies"]:
        for entry in atomic["required_hermes_fields"]:
            key = (entry["field"], entry.get("timeframe"))
            assert key in declared or entry["field"] in any_timeframe, key


def test_criterion_8_every_package_hermes_field_states_its_timeframe(package):
    """The same fact on two timeframes is two facts: candle.close is needed
    on 15M for the wick atomics and on 5M for the breakout trigger."""
    for entry in package["required_hermes_fields"]:
        assert entry["timeframe"], entry["field"]
        assert entry["purpose"]
    closes = [
        entry
        for entry in package["required_hermes_fields"]
        if entry["field"] == "candle.close"
    ]
    assert {entry["timeframe"] for entry in closes} == {"15M", "5M"}


def test_criterion_8_the_package_invents_no_feed_of_its_own(package):
    """PID lines 21-22: HSA maps onto HERMES outputs, it does not invent."""
    declared = {entry["field"] for entry in package["required_hermes_fields"]}
    consumed = {
        entry["field"]
        for atomic in package["atomic_strategies"]
        for entry in atomic["required_hermes_fields"]
    }
    assert declared == consumed


# --- criterion 9: a coherent deterministic implementation package ------------


def test_criterion_9_the_package_is_structurally_valid(package):
    """PID line 258, against the frozen contract."""
    assert validate_document(package) == "strategy_package"


def test_criterion_9_the_package_is_semantically_clean(package, catalogue):
    """PID line 258, against every cross-field rule the schema cannot see.

    This is the check that ``hsa validate`` does NOT run; a package can pass
    the schema and still contradict itself.
    """
    assert check_package(package, catalogue=catalogue) == []


def test_criterion_9_the_package_and_its_embedded_chain_do_not_disagree(package):
    """The package level is authoritative and the chain restates it."""
    from hsa.semantics import AGREEMENT_SECTIONS

    for section in AGREEMENT_SECTIONS:
        assert package[section] == package["chain"][section], section


def test_criterion_9_the_cli_validates_the_package_in_a_real_process():
    """Not simulated: the shipped command, a real process, a real exit code."""
    result = _run("validate", str(PACKAGE_PATH.relative_to(REPO_ROOT)))
    assert result.returncode == EXIT_OK, result.stderr
    assert "valid strategy_package" in result.stdout


def test_criterion_9_the_embedded_chain_passes_the_shipped_chain_command(tmp_path):
    """``hsa chain`` runs both halves of validation and resolves the
    catalogue. It takes a chain document, so the embedded chain is extracted
    to run it — see the note in this module's docstring about the missing
    package-level semantic command."""
    chain_path = tmp_path / "chain.json"
    chain_path.write_text(
        json.dumps(_load(PACKAGE_PATH)["chain"], indent=2), encoding="utf-8"
    )
    result = _run("chain", str(chain_path))
    assert result.returncode == EXIT_OK, result.stderr
    assert "valid chain, structurally and semantically" in result.stdout
    assert "3 inputs resolved" in result.stdout


def test_criterion_9_the_package_is_precise_enough_for_forge(package):
    """PID line 148: FORGE implements, it does not invent trading logic.

    Every quantity the implementation needs is a declared parameter with a
    bounded domain, at package level or on an embedded atomic. Nothing is
    left as prose for FORGE to interpret.
    """
    parameters = list(package["parameters"])
    for atomic in package["atomic_strategies"]:
        parameters.extend(atomic["parameters"])
    assert parameters
    for parameter in parameters:
        assert parameter["units"]
        assert "default" in parameter
        assert ("allowed_range" in parameter) != ("allowed_values" in parameter)
        if "allowed_range" in parameter:
            bounds = parameter["allowed_range"]
            assert bounds["minimum"] <= parameter["default"] <= bounds["maximum"]

    output = package["output_contract"]
    assert output["reason_field"] in {field["name"] for field in output["fields"]}


def test_criterion_9_the_package_says_it_is_a_proof_not_a_profitable_strategy(package):
    """PID line 244. Overclaiming here would be the worst kind of defect."""
    description = package["description"]
    assert "PRODUCT PROOF" in description.upper()
    assert "NOT A CLAIM OF A PROFITABLE STRATEGY" in description.upper()


# --- criterion 10: preserve strategy and version identity --------------------


def test_criterion_10_identity_is_id_and_version_everywhere(package, evidence):
    """PID lines 259, 72."""
    assert package["strategy_id"] == STRATEGY_ID
    assert package["strategy_version"] == STRATEGY_VERSION
    assert evidence["strategy_id"] == STRATEGY_ID
    assert evidence["strategy_version"] == STRATEGY_VERSION
    for reference in package["cer_references"]:
        assert reference["strategy_id"] == STRATEGY_ID
        assert reference["strategy_version"] == STRATEGY_VERSION


def test_criterion_10_a_candidate_supersedes_nothing_and_mutates_nothing(package):
    """PID lines 260, 262 and 185-189.

    This is the original version, so ``supersedes`` is null — stated
    explicitly rather than omitted, because an absent field cannot be told
    apart from an overlooked one.
    """
    lifecycle = package["lifecycle"]
    assert lifecycle["status"] == "CANDIDATE"
    assert lifecycle["immutable_once_promoted"] is True
    assert lifecycle["supersedes"] is None
    assert "supersedes" in lifecycle
    assert lifecycle["created_at_utc"].endswith("Z")


def test_criterion_10_the_lineage_reader_agrees(package):
    """The shipped versioning module, not a re-derivation of its rules."""
    links = lineage([package])
    assert len(links) == 1
    assert links[0].strategy_id == STRATEGY_ID
    assert links[0].strategy_version == STRATEGY_VERSION
    assert links[0].status == "CANDIDATE"
    assert links[0].supersedes_version is None


def test_criterion_10_every_timestamp_is_utc(package, evidence):
    """PID line 225: UTC is canonical, local time is display-only."""
    stamps = [
        package["lifecycle"]["created_at_utc"],
        package["provenance"]["ingested_at_utc"],
        package["chain"]["provenance"]["ingested_at_utc"],
        evidence["generated_at_utc"],
    ]
    stamps.extend(
        reference["recorded_at_utc"] for reference in package["cer_references"]
    )
    stamps.extend(
        atomic["provenance"]["ingested_at_utc"]
        for atomic in package["atomic_strategies"]
    )
    for stamp in stamps:
        assert stamp.endswith("Z"), stamp


# --- criterion 11: define tests and evidence requirements --------------------


def test_criterion_11_the_package_has_end_to_end_deterministic_cases(package):
    """PID line 261. Over and above each atomic's own cases."""
    cases = package["deterministic_test_cases"]
    assert len(cases) >= 4
    assert len({case["case_id"] for case in cases}) == len(cases)
    for case in cases:
        assert case["description"]
        assert case["given_hermes_facts"]
        assert case["expected_output"]


def test_criterion_11_the_cases_discriminate(package):
    """A set of cases that only ever matches has not been shown to
    discriminate. Both outcomes must be pinned."""
    outcomes = {
        case["expected_output"].get("matched")
        for case in package["deterministic_test_cases"]
    }
    assert outcomes == {True, False}


def test_criterion_11_the_case_facts_only_use_declared_hermes_fields(package):
    """A case that invents a fact is not a case the package can be run on."""
    declared = {entry["field"] for entry in package["required_hermes_fields"]}
    bookkeeping = {"bar_index_5m", "timeframe"}
    for case in package["deterministic_test_cases"]:
        for bar in case["given_hermes_facts"]["bars"]:
            for key in bar:
                assert key in declared or key in bookkeeping, (case["case_id"], key)


def test_criterion_11_the_case_parameters_are_all_declared(package):
    """Likewise for parameters: a case may not set a knob that does not exist."""
    declared = {parameter["name"] for parameter in package["parameters"]}
    for atomic in package["atomic_strategies"]:
        declared.update(parameter["name"] for parameter in atomic["parameters"])
    for case in package["deterministic_test_cases"]:
        for name in case.get("given_parameters", {}):
            assert name in declared, (case["case_id"], name)


def test_criterion_11_evidence_requirements_are_stated_before_evidence_exists(package):
    """PID line 143. Stating them first is what stops thresholds moving to
    fit a result."""
    requirements = package["evidence_requirements"]
    assert requirements["backtest_requirements"]
    assert requirements["minimum_sample_size"] >= 1
    assert requirements["required_cer_evidence_types"]
    assert package["acceptance_criteria"]
    assert package["rejection_criteria"]


def test_criterion_11_acceptance_and_rejection_criteria_are_machine_evaluable(package):
    """PID line 144: prose alone is not sufficient."""
    comparators = {">=", "<=", ">", "<", "==", "!="}
    for criterion in package["acceptance_criteria"] + package["rejection_criteria"]:
        assert criterion["criterion_id"]
        assert criterion["statement"]
        assert criterion["metric"]
        assert criterion["comparator"] in comparators
        assert criterion["threshold"] is not None


def test_criterion_11_the_strategy_has_a_stated_way_to_fail(package):
    """A strategy with no way to fail cannot be governed by evidence."""
    rejection = {c["criterion_id"] for c in package["rejection_criteria"]}
    assert "insufficient_sample" in rejection
    # And the SEQUENCE primitive itself must be shown to be carrying
    # something, or the strategy is not the one the source described.
    assert "sequence_ordering_not_discriminating" in rejection


# --- criterion 12: use and target CER semantics ------------------------------


def test_criterion_12_every_reference_validates_against_the_frozen_contract(package):
    """PID line 261 and lines 160-181, through hsa/cer.py itself."""
    assert package["cer_references"]
    for reference in package["cer_references"]:
        validate_reference(reference, source=str(PACKAGE_PATH))


def test_criterion_12_the_minimum_reference_types_are_present(package):
    """Source analysis, hypothesis and version lineage (PID lines 175-179)."""
    types = {reference["reference_type"] for reference in package["cer_references"]}
    assert {"SOURCE_ANALYSIS", "STRATEGY_HYPOTHESIS", "VERSION_LINEAGE"} <= types


def test_criterion_12_every_reference_is_labelled_a_contract_fixture(package, evidence):
    """PID line 181. A fixture mistaken for live evidence is the failure
    this labelling exists to prevent."""
    # The envelope key is ``cer_status``, not ``source``/``cer_live``: both
    # governed evidence indexes now use one envelope. They used to differ —
    # ``$hsa_evidence``/``cer_live`` here, ``document_type``/``cer_status``
    # for gold — which meant one inventory convention with two shapes, only
    # one of them pinned by a test. Converged on gold's, because a container
    # is deliberately NOT a contract kind and ``$hsa_``-prefixed keys are the
    # namespace routable contract documents use.
    assert evidence["cer_status"] == "NOT_LIVE"
    for reference in package["cer_references"] + evidence["references"]:
        assert reference["source"] == "CONTRACT_FIXTURE"
        # Nothing here supports a promotion, because nothing has been run.
        assert reference["supports"] == "INFORMATIONAL"


def test_criterion_12_the_references_carry_cer_canonical_identities(package):
    """PID lines 166-171: opaque to HSA, carried rather than interpreted."""
    for reference in package["cer_references"]:
        identities = {"experiment_id", "run_id", "evidence_id", "artifact_id"}
        assert identities & set(reference)


def test_criterion_12_evidence_json_and_the_package_cannot_drift(package, evidence):
    """The two files state the same references, so neither can be updated
    alone and quietly disagree with the other."""
    assert evidence["references"] == package["cer_references"]


def test_criterion_12_evidence_json_is_not_a_parallel_evidence_store(evidence):
    """PID line 181 forbids an incompatible permanent evidence store.

    The file holds references and no measurements, and names what is still
    owed before promotion rather than implying it has been supplied.
    """
    assert evidence["evidence_still_owed_before_promotion"]
    for reference in evidence["references"]:
        assert set(reference) <= {
            "$hsa_kind",
            "$hsa_contract_version",
            "strategy_id",
            "strategy_version",
            "experiment_id",
            "run_id",
            "evidence_id",
            "artifact_id",
            "reference_type",
            "source",
            "summary",
            "recorded_at_utc",
            "supports",
        }


def test_criterion_12_the_cer_command_validates_the_references(tmp_path, evidence):
    """The shipped ``hsa cer`` reader over these exact references.

    ``hsa cer validate`` takes one cer_reference per file, so the references
    are materialised individually — see this module's docstring note.
    """
    for reference in evidence["references"]:
        path = tmp_path / (reference["evidence_id"] + ".json")
        path.write_text(json.dumps(reference, indent=2), encoding="utf-8")

    result = _run("cer", "validate", *sorted(str(p) for p in tmp_path.glob("*.json")))
    assert result.returncode == EXIT_OK, result.stderr
    assert result.stdout.count("valid cer_reference (CONTRACT_FIXTURE)") == len(
        evidence["references"]
    )

    listed = _run(
        "cer",
        "--fixtures",
        str(tmp_path),
        "list",
        "--strategy",
        STRATEGY_ID,
        "--strategy-version",
        STRATEGY_VERSION,
    )
    assert listed.returncode == EXIT_OK, listed.stderr
    assert "CONTRACT_FIXTURE" in listed.stdout
    for reference_type in ("SOURCE_ANALYSIS", "STRATEGY_HYPOTHESIS", "VERSION_LINEAGE"):
        assert reference_type in listed.stdout


def test_criterion_12_the_lineage_command_resolves_this_versions_evidence(
    tmp_path, evidence
):
    """``hsa cer lineage`` over the governed package itself."""
    for reference in evidence["references"]:
        path = tmp_path / (reference["evidence_id"] + ".json")
        path.write_text(json.dumps(reference, indent=2), encoding="utf-8")

    result = _run(
        "cer",
        "--fixtures",
        str(tmp_path),
        "lineage",
        str(PACKAGE_PATH.relative_to(REPO_ROOT)),
    )
    assert result.returncode == EXIT_OK, result.stderr
    assert "strategy_id %s" % STRATEGY_ID in result.stdout
    assert "0.1.0  [CANDIDATE]" in result.stdout
    assert "original version, supersedes nothing" in result.stdout
    assert "CER is not live" in result.stdout
