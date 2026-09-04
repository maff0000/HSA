"""The parameterise-vs-reject boundary — PID lines 110-120, criterion 3.

These tests exist to stop the boundary drifting. The ruling itself lives in
``docs/AMBIGUITY-POLICY.md``; the lexicon applies it; these tests check that
the two still agree and that the fail-closed property still holds.

The property that matters most is the last section: an undeclared
discretionary term must REFUSE. If that ever regresses, HSA starts baking
guesses into governed strategies (PID line 39) and nothing else here saves
it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from hsa.contracts import validate_document
from hsa.intake import build_request, intake, load_lexicon
from hsa.intake.analyser import analyse
from hsa.intake.errors import LexiconError
from hsa.intake.lexicon import PARAMETERISE, REFUSE

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY = REPO_ROOT / "docs" / "AMBIGUITY-POLICY.md"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "intake"
STAMP = "2026-09-04T00:00:00Z"

#: The five phrases PID lines 114-118 say must never be guessed, plus the
#: one PID acceptance Example B (line 242) additionally depends on.
PID_PHRASES = {
    "large wick": ("large_wick", PARAMETERISE),
    "no-wick candle": ("no_wick_candle", PARAMETERISE),
    "near resistance": ("near_resistance", REFUSE),
    "strong trend": ("strong_trend", REFUSE),
    "confirmation candle": ("confirmation_candle", REFUSE),
    "good breakout": ("good_breakout", REFUSE),
}


@pytest.fixture(scope="module")
def lexicon():
    return load_lexicon()


def _run(name: str, source_type: str, lex=None):
    text = (FIXTURES / name).read_text(encoding="utf-8")
    request = build_request(text, source_type, str(FIXTURES / name))
    return intake(request, lexicon=lex, generated_at_utc=STAMP)


# --- the ruling is declared, not implicit ------------------------------------


def test_the_policy_document_exists_at_the_cross_referenced_path():
    """Other work items cite this exact path; moving it breaks them."""
    assert POLICY.is_file()
    text = POLICY.read_text(encoding="utf-8")
    assert "measurement basis is known" in text
    assert "measurement basis is itself undefined" in text


def test_the_lexicon_points_back_at_the_policy_document(lexicon):
    assert lexicon.ruling_document == "docs/AMBIGUITY-POLICY.md"
    assert (REPO_ROOT / lexicon.ruling_document).is_file()


def test_every_pid_phrase_has_a_declared_ruling(lexicon):
    """PID lines 114-118 name five phrases. None may be undeclared."""
    declared = {term.term_id: term for term in lexicon.terms}
    for phrase, (term_id, disposition) in PID_PHRASES.items():
        assert term_id in declared, "%s has no lexicon entry" % phrase
        assert declared[term_id].disposition == disposition


def test_policy_document_and_lexicon_agree_on_every_ruling(lexicon):
    """The prose and the data file must not drift apart.

    The policy table is what a human reads; the lexicon is what runs. If a
    term were reclassified in one and not the other, HSA would behave
    differently from its own stated doctrine.
    """
    text = POLICY.read_text(encoding="utf-8")
    for term in lexicon.terms:
        rows = [
            line
            for line in text.splitlines()
            if line.startswith("|") and "**\"%s\"**" % term.label in line
        ]
        assert rows, "no policy table row for %r" % term.label
        expected = "PARAMETERISE" if term.disposition == PARAMETERISE else "REFUSE"
        assert "**%s**" % expected in rows[0], (
            "policy document and lexicon disagree on %r" % term.label
        )


# --- parameterise: the measurement basis is known ----------------------------


def test_parameterised_terms_declare_a_basis_and_bounded_parameters(lexicon):
    for term in lexicon.terms:
        if term.disposition != PARAMETERISE:
            continue
        assert term.measurement_basis
        assert term.basis_rationale
        assert term.parameters
        for param in term.parameters:
            # PID line 140: default, allowed range and units, all present.
            assert param["default"] is not None
            assert param["units"]
            assert "allowed_range" in param or "allowed_values" in param


def test_large_wick_is_parameterised_not_rejected():
    """PID line 117 names it; PID line 242 depends on it. Both hold.

    The measurement basis (wick length over candle range) is known, so only
    the threshold was missing — and a missing threshold is a parameter.
    """
    result = _run("example_b_rejection_wick_sequence.txt", "TRADER_EXPLANATION")
    assert result.sufficiently_defined
    resolved = {entry["term_id"]: entry for entry in result.document["resolved_terms"]}
    assert "large_wick" in resolved
    assert "large 15m rejection wick" in resolved["large_wick"]["source_language"]
    assert "wick length" in resolved["large_wick"]["measurement_basis"].lower()


def test_a_parameterisation_is_never_silent():
    """It must be visible AND attributable in the output, per the ruling."""
    result = _run("example_b_rejection_wick_sequence.txt", "TRADER_EXPLANATION")
    entry = next(
        e for e in result.document["resolved_terms"] if e["term_id"] == "large_wick"
    )
    resolution = entry["resolution"]
    assert resolution["disposition"] == "PARAMETERISED"
    assert resolution["authority"] == "HUMAN_ARCHITECT_RULING"
    assert resolution["ruling_document"] == "docs/AMBIGUITY-POLICY.md"
    # There is deliberately no ``hsa_guessed`` field. It was emitted as
    # ``false`` on every resolution, which asserted more than the analyser had
    # checked: it had verified that the basis came from a ratified ruling and
    # had verified nothing about whether the source agreed with that basis.
    # The two claims are now separated, and the second one says NOT_VERIFIED.
    assert "hsa_guessed" not in resolution
    assert resolution["basis_authority"] == "RATIFIED_LEXICON_RULING"
    assert resolution["hsa_invented_basis"] is False
    assert resolution["source_basis_agreement"] == "NOT_VERIFIED"
    # And what WAS checked is recorded, including what it does not cover.
    scan = resolution["basis_conflict_scan"]
    assert scan["result"] == "NO_DECLARED_REBASING_FOUND"
    assert scan["qualifiers_declared"] > 0
    assert entry["source_language"] in scan["inspected_text"]
    assert "not proven" in scan["limits"].lower() or "nothing more" in scan["limits"].lower()
    # The basis is ratified; the default is not. Saying so is what keeps a
    # provisional number from hardening into an unexamined decision.
    assert resolution["default_status"] == "PROVISIONAL_PENDING_EVIDENCE"
    assert resolution["evidence_required"] is True
    # And the source language is quoted verbatim with a real location.
    assert entry["source_language"] in result.document["raw_description"]
    assert re.match(r"^line \d+, characters \d+-\d+", entry["location"])


def test_example_b_passes_acceptance():
    """PID line 242 + line 288: the ordered price-action sequence resolves."""
    result = _run("example_b_rejection_wick_sequence.txt", "TRADER_EXPLANATION")
    assert result.sufficiently_defined
    ids = {entry["term_id"] for entry in result.document["resolved_terms"]}
    assert {"large_wick", "no_wick_candle"} <= ids
    names = {param["name"] for param in result.document["parameters"]}
    assert {"min_wick_to_range_ratio", "max_wick_to_range_ratio"} <= names


# --- refuse: the measurement basis is itself undefined -----------------------


def test_refused_terms_declare_no_measurement_basis(lexicon):
    for term in lexicon.terms:
        if term.disposition != REFUSE:
            continue
        assert term.measurement_basis is None
        assert term.why_unresolved
        assert term.blocks
        assert term.resolution_needed["kind"]
        assert term.resolution_needed["responsible"]


def test_near_resistance_refuses_and_is_named_exactly():
    """PID line 115. The reference level is undefined, so no parameter exists."""
    result = _run("near_resistance_pullback.txt", "TRADER_EXPLANATION")
    assert not result.sufficiently_defined
    assert result.document["result"] == "STRATEGY_NOT_SUFFICIENTLY_DEFINED"
    items = {item["item_id"]: item for item in result.document["unresolved_items"]}
    assert "near_resistance" in items
    item = items["near_resistance"]
    assert item["source_language"] == "near resistance"
    assert item["severity"] == "BLOCKING"
    assert "resistance is never constructed" in item["why_unresolved"]
    assert item["resolution_needed"]["responsible"] == "MATT"
    assert item["blocks"]


def test_refusal_preserves_the_work_already_done():
    """Partial extraction is not thrown away, so resubmission restarts less."""
    result = _run("near_resistance_pullback.txt", "TRADER_EXPLANATION")
    summary = " ".join(result.document["resolved_summary"])
    assert "large 15m" in summary and "wick" in summary


def test_all_five_pid_phrases_are_handled_without_guessing():
    result = _run("all_five_pid_phrases.txt", "VIDEO_DERIVED")
    assert not result.sufficiently_defined
    ids = {item["item_id"] for item in result.document["unresolved_items"]}
    assert {"near_resistance", "strong_trend", "confirmation_candle", "good_breakout"} <= ids
    # large wick is present in the same source and was resolved, not refused.
    assert "large_wick" not in ids
    assert any("large rejection wick" in line for line in result.document["resolved_summary"])


def test_every_refusal_names_what_is_needed_and_who_owes_it():
    """PID line 120: exactly what is unresolved, and what would unblock it."""
    for name, source_type in (
        ("near_resistance_pullback.txt", "TRADER_EXPLANATION"),
        ("all_five_pid_phrases.txt", "VIDEO_DERIVED"),
        ("unknown_term_healthy_pullback.txt", "MATT_OBSERVATION"),
    ):
        result = _run(name, source_type)
        assert not result.sufficiently_defined
        for item in result.document["unresolved_items"]:
            assert item["source_language"].strip()
            assert item["why_unresolved"].strip()
            assert item["blocks"]
            resolution = item["resolution_needed"]
            assert resolution["kind"] and resolution["description"] and resolution["responsible"]


def test_candidate_definitions_are_offered_but_never_chosen():
    """Presenting an option is not adopting it. Choosing is the resolution."""
    result = _run("all_five_pid_phrases.txt", "VIDEO_DERIVED")
    offered = 0
    for item in result.document["unresolved_items"]:
        for candidate in item.get("candidate_definitions", []):
            offered += 1
            assert "selected" not in candidate
            assert "chosen" not in candidate
    assert offered > 0


# --- the contract holds for every refusal ------------------------------------


@pytest.mark.parametrize(
    "name,source_type",
    [
        ("near_resistance_pullback.txt", "TRADER_EXPLANATION"),
        ("all_five_pid_phrases.txt", "VIDEO_DERIVED"),
        ("unknown_term_healthy_pullback.txt", "MATT_OBSERVATION"),
    ],
)
def test_every_emitted_refusal_validates_against_the_frozen_schema(name, source_type):
    result = _run(name, source_type)
    assert validate_document(result.document) == "not_sufficiently_defined"


# --- a ruled term can be re-based by its context -----------------------------


def test_the_policy_documents_own_worked_example_refuses():
    """docs/AMBIGUITY-POLICY.md names this exact phrase as a refusal.

    "Large wick relative to the recent average" is not the claim "large
    wick": it introduces a lookback the ruled single-bar basis does not
    cover. The document said so before the behaviour existed, and the
    behaviour resolved the phrase at exit 0 — a required boot artifact
    asserting something the code did not do. This is that gap, closed and
    tested.
    """
    result = _run("rebased_wick_recent_average.txt", "MATT_OBSERVATION")
    assert not result.sufficiently_defined
    items = {item["item_id"]: item for item in result.document["unresolved_items"]}
    assert "rebased_large_wick" in items
    item = items["rebased_large_wick"]
    assert item["severity"] == "BLOCKING"
    assert "re-bases the measurement" in item["why_unresolved"]
    # The ruled term is NOT reported as resolved anywhere.
    assert "large 15m" not in " ".join(result.document["resolved_summary"])


def test_a_ruled_term_rebased_onto_another_quantity_refuses():
    """The source states 2 x ATR and that the bar range is irrelevant.

    Applying the ruled wick-over-bar-range basis here would emit
    ``candle.range`` as a required HERMES input for a trader who said the
    bar range does not matter, and would hand FORGE a threshold the source
    never gave. PID line 39 forbids exactly that.
    """
    result = _run("rebased_wick_atr_multiple.txt", "TRADER_EXPLANATION")
    assert not result.sufficiently_defined
    assert result.document["result"] == "STRATEGY_NOT_SUFFICIENTLY_DEFINED"
    assert validate_document(result.document) == "not_sufficiently_defined"
    item = next(
        i
        for i in result.document["unresolved_items"]
        if i["item_id"] == "rebased_large_wick"
    )
    # The quantity the source actually named is quoted back at the reader.
    assert "ATR" in item["why_unresolved"] or "atr" in item["why_unresolved"]
    assert item["resolution_needed"]["responsible"] == "MATT"
    # Nothing was mapped to HERMES off the displaced basis.
    assert "required_hermes_fields" not in result.document


def test_the_refusal_quotes_the_full_qualifying_context_not_just_the_term():
    """Quoting only "large wick" would hide the words that caused the refusal.

    docs/AMBIGUITY-POLICY.md promises source_language verbatim. Verbatim of
    the matched span alone is not enough here: the qualifier is the evidence.
    """
    result = _run("rebased_wick_atr_multiple.txt", "TRADER_EXPLANATION")
    item = next(
        i
        for i in result.document["unresolved_items"]
        if i["item_id"] == "rebased_large_wick"
    )
    raw = (FIXTURES / "rebased_wick_atr_multiple.txt").read_text(encoding="utf-8")
    quoted = item["source_language"]
    assert quoted in raw, "source_language must be a verbatim slice of the source"
    assert "large wick" in quoted
    assert "ATR" in quoted


def test_a_plain_ruled_term_with_no_rebasing_still_parameterises():
    """The guard must not swallow the case the ruling exists to resolve."""
    for name in (
        "example_b_rejection_wick_sequence.txt",
        "example_b_wick_rejection_sequence.txt",
    ):
        result = _run(name, "TRADER_EXPLANATION")
        assert result.sufficiently_defined, name
        ids = {entry["term_id"] for entry in result.document["resolved_terms"]}
        assert {"large_wick", "no_wick_candle"} <= ids, name


def test_the_rebasing_vocabulary_is_declared_data_not_code(lexicon):
    """Reviewable without reading Python, exactly like every other ruling."""
    assert lexicon.basis_qualifiers
    for qualifier in lexicon.basis_qualifiers:
        assert qualifier.qualifier_id
        assert qualifier.category in (
            "COMPARATIVE",
            "LOOKBACK",
            "ALTERNATIVE_BASIS",
            "NEIGHBOUR",
        )
        assert qualifier.reason.strip()
        assert qualifier.raw_pattern.strip()
    # The PID-facing constructions the ruling has to cover are all declared.
    patterns = " ".join(q.raw_pattern for q in lexicon.basis_qualifiers)
    for construction in ("relative to", "compared", "versus", "against", "average",
                         "recent", "atr", "true range", "other", "neighbou"):
        assert construction in patterns, construction


def test_the_inspected_window_is_declared_rather_than_chosen_in_code(lexicon):
    """Window size is the reviewable half of the guard, so it lives in data."""
    window = lexicon.basis_qualifier_policy["window"]
    assert window["unit"] == "SENTENCE"
    assert isinstance(window["sentences_after"], int)
    assert window["sentence_terminators"]
    assert window["description"].strip()


def test_a_lexicon_with_no_basis_qualifiers_is_refused_at_load(tmp_path):
    """An empty vocabulary would fail OPEN: every ruled term would resolve."""
    source = json.loads(
        (FIXTURES / "lexicon_advisory.json").read_text(encoding="utf-8")
    )
    source["basis_qualifiers"] = []
    broken = tmp_path / "no_qualifiers.json"
    broken.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(LexiconError, match="fail open"):
        load_lexicon(broken)


def test_basis_qualifier_policy_must_refuse(tmp_path):
    source = json.loads(
        (FIXTURES / "lexicon_advisory.json").read_text(encoding="utf-8")
    )
    source["basis_qualifier_policy"]["disposition"] = "PARAMETERISE"
    broken = tmp_path / "open_rebasing.json"
    broken.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(LexiconError, match="fails closed"):
        load_lexicon(broken)


def test_the_guard_does_not_claim_to_be_complete(lexicon):
    """An overstated guard is worse than none, so the limit is declared."""
    limits = lexicon.basis_qualifier_policy["limits"].lower()
    assert "not proven" in limits or "passes it" in limits
    assert "surface" in limits


def test_the_policy_document_and_the_guard_describe_the_same_system():
    """The document's carve-out and its 'context can fool it' limit agreed
    on nothing before: one promised a refusal the other said was impossible.
    Both passages must now describe what actually runs."""
    text = POLICY.read_text(encoding="utf-8")
    assert "A ruled term can be re-based by its context" in text
    # The carve-out no longer stands alone as an unqualified promise.
    assert "basis_qualifiers" in text
    assert "hsa_guessed" in text, "the removed field must be explained, not vanish"


# --- unknown terms fail closed: the property everything else rests on --------


def test_an_undeclared_discretionary_term_refuses():
    """The single most important behaviour of intake.

    A term with no lexicon ruling must not pass through into a draft. If it
    did, it would become an assumption baked into a governed strategy, and
    nobody downstream could tell it from a decision (PID line 39).
    """
    result = _run("unknown_term_healthy_pullback.txt", "MATT_OBSERVATION")
    assert not result.sufficiently_defined
    items = result.document["unresolved_items"]
    assert len(items) == 1
    item = items[0]
    assert item["source_language"] == "healthy pullback"
    assert item["severity"] == "BLOCKING"
    assert "no entry in HSA's declared intake lexicon" in item["why_unresolved"]
    assert "healthy pullback" in item["resolution_needed"]["description"]


def test_unknown_terms_still_refuse_when_no_term_matches_at_all(lexicon):
    """Fail-closed does not depend on any ruled term also being present."""
    request = build_request(
        "Take the trade when the structure looks clean and the move is quick.",
        "MATT_OBSERVATION",
        "unit test",
    )
    result = intake(request, lexicon=lexicon, generated_at_utc=STAMP)
    assert not result.sufficiently_defined
    assert all(
        item["item_id"].startswith("unknown_")
        for item in result.document["unresolved_items"]
    )
    assert validate_document(result.document) == "not_sufficiently_defined"


def test_a_known_term_is_not_also_reported_as_unknown():
    """Fail-closed must not become fail-noisy: no double reporting."""
    result = _run("all_five_pid_phrases.txt", "VIDEO_DERIVED")
    ids = [item["item_id"] for item in result.document["unresolved_items"]]
    assert len(ids) == len(set(ids))
    assert not any(identifier.startswith("unknown_") for identifier in ids)


def test_a_lexicon_with_no_markers_is_refused_at_load(tmp_path):
    """A marker-less lexicon would fail OPEN. That must not be loadable."""
    source = json.loads(
        (FIXTURES / "lexicon_advisory.json").read_text(encoding="utf-8")
    )
    source["discretionary_markers"] = []
    broken = tmp_path / "no_markers.json"
    broken.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(LexiconError, match="fail open"):
        load_lexicon(broken)


def test_unknown_term_policy_must_refuse(tmp_path):
    source = json.loads(
        (FIXTURES / "lexicon_advisory.json").read_text(encoding="utf-8")
    )
    source["unknown_term_policy"]["disposition"] = "PARAMETERISE"
    broken = tmp_path / "open_policy.json"
    broken.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(LexiconError, match="fail open"):
        load_lexicon(broken)


def test_a_refuse_term_may_not_smuggle_in_a_measurement_basis(tmp_path):
    """A known basis is exactly what would make it parameterisable instead."""
    source = json.loads(
        (FIXTURES / "lexicon_advisory.json").read_text(encoding="utf-8")
    )
    for term in source["terms"]:
        if term["disposition"] == "REFUSE":
            term["measurement_basis"] = "invented out of nowhere"
    broken = tmp_path / "smuggled.json"
    broken.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(LexiconError, match="measurement_basis"):
        load_lexicon(broken)


def test_a_parameterise_term_must_actually_declare_a_parameter(tmp_path):
    source = json.loads(
        (FIXTURES / "lexicon_advisory.json").read_text(encoding="utf-8")
    )
    for term in source["terms"]:
        if term["disposition"] == PARAMETERISE:
            term["parameters"] = []
    broken = tmp_path / "empty_params.json"
    broken.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(LexiconError, match="at least one parameter"):
        load_lexicon(broken)


# --- advisory items travel with a draft, they do not stop it -----------------


def test_advisory_items_do_not_block_but_are_carried():
    lexicon = load_lexicon(FIXTURES / "lexicon_advisory.json")
    result = _run("near_resistance_pullback.txt", "TRADER_EXPLANATION", lex=lexicon)
    assert result.sufficiently_defined
    advisory = result.document["advisory_items"]
    assert [item["item_id"] for item in advisory] == ["near_resistance"]
    assert advisory[0]["severity"] == "ADVISORY"


# --- the fixture inventory stays documented ----------------------------------


def test_the_fixture_readme_lists_every_fixture():
    """``tests/fixtures/intake/README.md`` is the only index of these inputs.

    It went stale once already: two acceptance work items added three
    fixtures and the table was not updated, so a reader could not tell
    ``example_b_rejection_wick_sequence.txt`` (a unit fixture) from
    ``example_b_wick_rejection_sequence.txt`` (a governed package's source,
    asserted byte for byte) without opening both. Documentation nobody checks
    drifts, so this checks it, in both directions.
    """
    readme = FIXTURES / "README.md"
    listed = set()
    for line in readme.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        listed.add(line.split("`")[1])

    present = {path.name for path in FIXTURES.iterdir() if path.name != "README.md"}

    assert not present - listed, "fixtures with no row in README.md: %s" % ", ".join(
        sorted(present - listed)
    )
    assert not listed - present, "README.md rows with no such fixture: %s" % ", ".join(
        sorted(listed - present)
    )


# --- honesty about the mechanism ---------------------------------------------


def test_the_output_says_a_clean_scan_is_not_proof_of_precision():
    """Overstating the analyser would undermine every guarantee above."""
    result = _run("well_specified_wick_sequence.txt", "MATT_OBSERVATION")
    assert result.sufficiently_defined
    limits = " ".join(result.document["analyser_limits"])
    assert "does not mean the description is fully specified" in limits.lower()
    assert "does not understand english" in limits.lower()


def test_the_scan_is_deterministic(lexicon):
    text = (FIXTURES / "all_five_pid_phrases.txt").read_text(encoding="utf-8")
    first = analyse(text, lexicon)
    second = analyse(text, lexicon)
    assert [f.term.term_id for f in first.term_findings] == [
        f.term.term_id for f in second.term_findings
    ]
    request = build_request(text, "VIDEO_DERIVED", "unit test")
    doc_a = intake(request, lexicon=lexicon, generated_at_utc=STAMP).document
    doc_b = intake(request, lexicon=lexicon, generated_at_utc=STAMP).document
    assert json.dumps(doc_a, sort_keys=True) == json.dumps(doc_b, sort_keys=True)

    # And the same for a source that trips the re-basing guard, where the
    # findings are grouped across occurrences and could otherwise come out in
    # dict or set order.
    rebased = (FIXTURES / "rebased_wick_atr_multiple.txt").read_text(encoding="utf-8")
    request = build_request(rebased, "TRADER_EXPLANATION", "unit test")
    doc_a = intake(request, lexicon=lexicon, generated_at_utc=STAMP).document
    doc_b = intake(request, lexicon=lexicon, generated_at_utc=STAMP).document
    assert json.dumps(doc_a, sort_keys=True) == json.dumps(doc_b, sort_keys=True)
