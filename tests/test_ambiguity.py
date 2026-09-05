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
    #
    # The stamp says NO_ATTACHED_REBASING_FOUND, not the old
    # NO_DECLARED_REBASING_FOUND. The old name was the same overclaim as
    # ``hsa_guessed`` one level down: the guard is tuned for precision and
    # routinely FINDS declared qualifiers it then declines to treat as
    # re-basing, so "no declared re-basing found" was a specific falsehood
    # about a scan that had found some and passed over them on purpose.
    scan = resolution["basis_conflict_scan"]
    assert scan["result"] == "NO_ATTACHED_REBASING_FOUND"
    assert scan["qualifiers_declared"] > 0
    assert entry["source_language"] in scan["inspected_text"]
    assert "not proven" in scan["limits"].lower() or "nothing more" in scan["limits"].lower()
    # The attachment ruling that produced this verdict is named, and the
    # qualifiers it saw and passed over are listed rather than dropped.
    assert scan["attachment_rule"].strip()
    assert isinstance(scan["declared_qualifiers_seen_unattached"], list)
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


# --- the guard is precise: it fires when attached, and only then -------------
#
# The guard's first form maximised RECALL — any declared qualifier anywhere in
# the window re-based the term. That refused ordinary, correct trading prose:
# an ATR stop, a bar-count expiry the PID itself REQUIRES a package to state,
# a moving-average trend filter, a prior-bar price reference. A guard that
# refuses valid strategies is a defect, not caution, so it was rebuilt around
# ATTACHMENT: a qualifier re-bases the ruled term only when it modifies that
# term, complements it, or glosses its own word.
#
# What makes precision safe here is that the guard is not the only thing
# telling the truth. Every resolution it permits still carries
# source_basis_agreement NOT_VERIFIED and now lists the declared qualifiers it
# saw and passed over, so the residual risk is stated rather than hidden.


def _analyse_text(text: str, lex):
    return analyse(text, lex)


def _refuses(text: str, lex) -> bool:
    """True when the source refuses, by any route intake actually uses."""
    request = build_request(text, "TRADER_EXPLANATION", "unit test")
    return not intake(request, lexicon=lex, generated_at_utc=STAMP).sufficiently_defined


#: Ordinary trading prose that must RESOLVE. Every one of these was refused by
#: the recall-maximising guard, and the refusal advised "restate the source
#: without the re-basing language" — which for an expiry means deleting the
#: expiry PID line 137 requires.
LEGITIMATE_SOURCES = [
    ("expiry_within_bars", "Enter on a large wick. The setup expires within 3 bars."),
    ("atr_sized_stop", "Enter on a large wick. My stop is 2 ATR below entry."),
    (
        "moving_average_trend_filter",
        "Enter on a large wick above the 200 period moving average.",
    ),
    (
        "prior_bar_price_reference",
        "Enter on a large wick that clears the previous bars' high.",
    ),
    ("expiry_spelled_out", "Enter on a large wick. Setup expires after four 15m bars."),
    ("expiry_in_digits", "Enter on a large wick. Setup expires after 4 bars."),
    ("volume_filter", "Enter on a large wick on above average volume."),
]


@pytest.mark.parametrize(("name", "source"), LEGITIMATE_SOURCES)
def test_a_legitimate_strategy_description_is_not_refused(name, source, lexicon):
    """A guard that refuses valid strategies is a different defect, not a fix."""
    assert not _refuses(source, lexicon), name


def test_the_same_expiry_spelled_two_ways_behaves_the_same(lexicon):
    """The clearest statement of the over-correction, kept as a regression.

    "after 4 bars" and "after four 15m bars" mean the same thing. Under the
    recall-maximising guard the first was refused and the second resolved,
    because the declared lookback pattern happens to match digits and not
    words. Example B passed acceptance on that accident of spelling. Identical
    meaning must not produce opposite outcomes on a spelling difference, in
    either direction — so this asserts they AGREE, not that they resolve.
    """
    digits = "Enter on a large wick. Setup expires after 4 bars."
    words = "Enter on a large wick. Setup expires after four 15m bars."
    assert _refuses(digits, lexicon) == _refuses(words, lexicon)
    assert not _refuses(digits, lexicon)


#: Genuine re-basings, which must still refuse. The first two are the R4
#: fixtures' constructions; the rest land inside the term's own matched span,
#: where the pattern's wildcard sits.
GENUINE_REBASINGS = [
    ("complement_comparative", "Enter on a large wick relative to the recent average."),
    (
        "gloss_of_the_ruled_word",
        "I enter on a large wick, and by large I mean twice the 14-period ATR.",
    ),
    ("slot_volatility", "I enter on a large atr wick."),
    ("slot_recent", "I enter on a large recent wick."),
    ("slot_average", "I enter on a large average wick."),
    ("slot_comparative", "I enter on a bigger than atr wick."),
]


@pytest.mark.parametrize(("name", "source"), GENUINE_REBASINGS)
def test_a_genuine_rebasing_still_refuses(name, source, lexicon):
    assert _refuses(source, lexicon), name


def test_a_qualifier_inside_the_terms_own_matched_span_is_not_ignored(lexicon):
    """Blocker 2: the wildcard slot is exactly where a re-basing lands.

    Hits falling inside the matched span used to be dropped as "part of the
    ruled phrase the lexicon already declares". That is false for any pattern
    with a wildcard: ``large_wick`` tolerates up to three words between its
    adjective and its head noun, so "a larger than average wick" matched
    ENTIRELY, the qualifier fell inside the match, and the term resolved while
    stamping a scan result claiming no re-basing was found.
    """
    source = "I enter when I see a larger than average wick on the 15m."
    analysis = _analyse_text(source, lexicon)
    assert analysis.rebased_findings, "the re-basing inside the span was missed"
    finding = analysis.rebased_findings[0]
    assert finding.term.term_id == "large_wick"
    assert any(hit.attachment == "SLOT" for hit in finding.hits)
    # And it is not silently resolved anywhere.
    assert not [f for f in analysis.term_findings if f.term.term_id == "large_wick"]


def test_the_guard_does_not_depend_on_word_order(lexicon):
    """The pair whose behaviour flipped on word order, both refusing now.

    The failing direction was the MORE natural phrasing, which is what made
    the gap easy to walk into.
    """
    qualifier_inside = "I enter when I see a larger than average wick on the 15m."
    qualifier_after = "I enter when I see a wick larger than the average."
    assert _refuses(qualifier_inside, lexicon)
    assert _refuses(qualifier_after, lexicon)


def test_a_resolution_names_the_qualifiers_it_saw_and_passed_over(lexicon):
    """Precision is only honest if the judgement is visible.

    The guard deliberately declines to re-base on an ATR that sizes a stop.
    Saying nothing about it would make the clean scan look like an empty one;
    the artifact has to show what was found and why it did not count.
    """
    request = build_request(
        "Enter on a large wick. My stop is 2 ATR below entry.",
        "TRADER_EXPLANATION",
        "unit test",
    )
    result = intake(request, lexicon=lexicon, generated_at_utc=STAMP)
    assert result.sufficiently_defined
    entry = next(
        e for e in result.document["resolved_terms"] if e["term_id"] == "large_wick"
    )
    scan = entry["resolution"]["basis_conflict_scan"]
    assert scan["result"] == "NO_ATTACHED_REBASING_FOUND"
    seen = scan["declared_qualifiers_seen_unattached"]
    assert any(hit["qualifier_id"] == "volatility_basis" for hit in seen), seen
    assert all(hit["not_treated_as_rebasing_because"].strip() for hit in seen)


def test_the_attachment_ruling_is_declared_data_not_code(lexicon):
    """Reviewable without reading Python, like every other ruling here."""
    attachment = lexicon.attachment
    assert attachment.rule.strip()
    assert {entry["form"] for entry in attachment.forms} == {
        "SLOT",
        "COMPLEMENT",
        "GLOSS",
    }
    assert attachment.complement_categories == ("COMPARATIVE",)
    assert attachment.gloss_constructions
    # The limits say what is NOT caught, in the open, rather than implying
    # completeness the guard cannot deliver.
    limits = lexicon.basis_qualifier_policy["limits"].lower()
    assert "precision" in limits
    assert "known misses" in limits
    # And the prose names the ordinary constructions it deliberately allows.
    not_attached = attachment.not_attached.lower()
    for construction in ("stop", "expir", "moving average"):
        assert construction in not_attached, construction


def test_a_parameterise_pattern_without_a_declared_slot_is_refused_at_load(tmp_path):
    """The slot must be declared, or Blocker 2 comes straight back.

    A PARAMETERISE pattern with a wildcard but no ``basis_slot`` group would
    leave the guard unable to see inside its own match, and a re-basing landing
    in the wildcard would resolve silently. That has to fail the load, not
    degrade quietly.
    """
    source = json.loads(
        (FIXTURES / "lexicon_advisory.json").read_text(encoding="utf-8")
    )
    term = next(t for t in source["terms"] if t["disposition"] == PARAMETERISE)
    term["pattern"] = term["pattern"].replace("(?P<basis_slot>", "(?:")
    broken = tmp_path / "no_slot.json"
    broken.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(LexiconError, match="basis_slot"):
        load_lexicon(broken)


def _lexicon_with_sentences_after(tmp_path, value: int):
    source = json.loads(
        (REPO_ROOT / "hsa" / "intake" / "lexicon.json").read_text(encoding="utf-8")
    )
    source["basis_qualifier_policy"]["window"]["sentences_after"] = value
    target = tmp_path / ("window_%d.json" % value)
    target.write_text(json.dumps(source), encoding="utf-8")
    return load_lexicon(target)


def test_the_declared_window_size_actually_changes_what_the_guard_sees(tmp_path):
    """``sentences_after`` is a declared tunable; prove it is a live one.

    It was previously untested as a VALUE: setting it to 0 or to 99 left the
    whole suite green, and the only assertion on it was that it is an int. A
    declared knob nothing exercises is indistinguishable from a dead one.

    With the guard tuned for precision, this number governs exactly one thing:
    how far a GLOSS may sit from the term it re-defines. SLOT and COMPLEMENT
    attachment cannot cross a sentence terminator, so the window cannot affect
    them. The lexicon's own window description states that, and this is the
    behaviour behind the statement.
    """
    trailing_gloss = "Enter on a large wick. By large I mean twice the ATR."
    inline = "Enter on a large wick relative to the recent average."

    narrow = _lexicon_with_sentences_after(tmp_path, 0)
    wide = _lexicon_with_sentences_after(tmp_path, 1)

    # The next-sentence gloss is reachable only with the window open.
    assert not analyse(trailing_gloss, narrow).rebased_findings
    assert analyse(trailing_gloss, wide).rebased_findings

    # Attachment inside the term's own sentence is unaffected by the window.
    assert analyse(inline, narrow).rebased_findings
    assert analyse(inline, wide).rebased_findings


def test_the_shipped_window_is_wide_enough_for_the_case_it_documents(lexicon):
    """The lexicon cites the trailing gloss as its reason for reaching ahead."""
    assert lexicon.basis_qualifier_policy["window"]["sentences_after"] >= 1
    assert analyse(
        "Enter on a large wick. By large I mean twice the ATR.", lexicon
    ).rebased_findings


def test_the_shipped_window_is_also_bounded_from_above(tmp_path, lexicon):
    """The window is a real bound in BOTH directions, not just a floor.

    A distant gloss is out of reach at the shipped setting and in reach at a
    wider one. That matters twice over: it pins the declared number from above
    as well as below, so widening it is a visible change rather than a silent
    one; and the miss it demonstrates is a REAL limit, which is why
    basis_qualifier_policy['limits'] now names "a gloss further away than
    window.sentences_after" outright instead of implying the guard sees
    everything.
    """
    distant = (
        "Enter on a large wick. I wait for bar close. I never trade the open. "
        "By large I mean twice the ATR."
    )
    assert not analyse(distant, lexicon).rebased_findings
    assert analyse(distant, _lexicon_with_sentences_after(tmp_path, 3)).rebased_findings
    assert "further away than" in lexicon.basis_qualifier_policy["limits"]


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


# --- a wildcard slot is not ruled text ----------------------------------------
#
# A term pattern is part literal and part wildcard. The literal parts are the
# phrase the lexicon rules on; the ``basis_slot`` group is a run of words that
# merely sits between them and that nobody has ruled on. The analyser used to
# treat the whole matched span as ruled and stop scanning inside it, and the
# consequence was the one failure mode this file exists to prevent: a silent
# one. "near resistance" — PID line 115, must never be guessed — disappeared
# with no refusal and no advisory because it landed between "large" and "wick".


#: The reproductions the third audit turned in, verbatim. The control proves
#: the swallowed term is ruled REFUSE and does fire on its own, so the first
#: case is a term being HIDDEN and not a term the lexicon never knew.
SLOT_REPRODUCTIONS = [
    (
        "refuse_term_inside_the_slot",
        "XAUUSD 15m. I enter on a large near resistance wick.",
    ),
    (
        "match_running_across_a_full_stop",
        "XAUUSD 15m. I want a large trade. some wick setups only.",
    ),
    (
        "control_the_same_term_on_its_own",
        "XAUUSD 15m. I enter near resistance.",
    ),
]


@pytest.mark.parametrize(("name", "source"), SLOT_REPRODUCTIONS)
def test_a_wildcard_slot_cannot_swallow_a_refusal(name, source, lexicon):
    assert _refuses(source, lexicon), name


def test_a_refuse_term_in_a_slot_is_named_and_the_term_does_not_resolve(lexicon):
    """Both halves matter, and only together.

    Surfacing "near resistance" is necessary: it is a PID line 115 phrase and
    the source must say so. Stopping ``large_wick`` resolving is necessary too:
    the slot MODIFIES the measurement, so declaring a bounded parameter over
    the top of undefined language there would attach a number to a quantity the
    source has not finished describing.
    """
    source = "XAUUSD 15m. I enter on a large near resistance wick."
    analysis = _analyse_text(source, lexicon)
    assert not analysis.parameterised, "the wick resolved with an unruled slot"

    request = build_request(source, "TRADER_EXPLANATION", "unit test")
    result = intake(request, lexicon=lexicon, generated_at_utc=STAMP)
    assert not result.sufficiently_defined
    items = {item["item_id"]: item for item in result.document["unresolved_items"]}
    assert "near_resistance" in items
    assert "unruled_slot_large_wick" in items
    slot_item = items["unruled_slot_large_wick"]
    assert slot_item["severity"] == "BLOCKING"
    # The refusal quotes the whole construction, not the slot alone: the slot
    # on its own reads as an ordinary refusal and hides the fact that a
    # PARAMETERISE term was sitting around it, about to resolve.
    assert "large near resistance wick" in slot_item["source_language"]
    assert "near resistance" in slot_item["why_unresolved"]


def test_a_declared_marker_in_a_slot_surfaces_instead_of_being_suppressed(lexicon):
    """The other sixteen ways in. Markers were suppressed by the same rule."""
    source = "XAUUSD 15m. I enter on a large healthy wick."
    analysis = _analyse_text(source, lexicon)
    assert [f.marker.marker_id for f in analysis.unknown_findings] == ["health"]
    assert not analysis.parameterised
    assert [f.term.term_id for f in analysis.unruled_slot_findings] == ["large_wick"]


def test_a_refusal_sharing_the_terms_head_noun_is_not_hidden_either(lexicon):
    """The straddling case, which the first fix did not close.

    "no wick confirmation candle" puts ``confirmation_candle`` partly in the
    slot and partly on ``no_wick_candle``'s own ruled head noun. The main
    passes resolve overlaps, so the refusal lost that contest and vanished —
    the same silent exit 0, one phrasing further out. The slot check is a
    direct scan for exactly this reason: it asks whether unresolved language
    TOUCHES the slot, which does not depend on who won an overlap.
    """
    source = "XAUUSD 15m. I need a no wick confirmation candle."
    assert _refuses(source, lexicon)
    analysis = _analyse_text(source, lexicon)
    assert [f.term.term_id for f in analysis.unruled_slot_findings] == ["no_wick_candle"]
    occupants = analysis.unruled_slot_findings[0].occupants
    assert [occupant.identity for occupant in occupants] == ["confirmation_candle"]


@pytest.mark.parametrize("terminator", list(".!?;"))
def test_no_term_match_may_span_a_sentence_boundary(terminator, lexicon):
    source = "XAUUSD 15m. I want a large trade%s some wick setups only." % terminator
    analysis = _analyse_text(source, lexicon)
    assert not analysis.term_findings, terminator
    assert _refuses(source, lexicon), terminator


def test_the_sentence_boundary_rule_does_not_depend_on_the_pattern(lexicon):
    """The rule is enforced on the MATCH, which is what makes it structural.

    Tightening the four shipped patterns so their slots cannot consume a full
    stop protects the four patterns that exist today. This test runs a lexicon
    whose slot is deliberately NOT tightened — the advisory test fixture still
    declares the original ``[a-z0-9.%]`` token class — and shows the pattern
    matching straight across a full stop while the analyser still refuses to
    accept it. A term declared tomorrow with a loose slot is covered by the
    same rule, without anybody remembering this.
    """
    loose = load_lexicon(FIXTURES / "lexicon_advisory.json")
    source = "I want a large trade. some wick setups only."
    normalised = analyse(source, loose).normalised
    raw = loose.term("large_wick").pattern.search(normalised)
    assert raw is not None, "this test needs a pattern that DOES reach across"
    assert "trade." in raw.group(0), raw.group(0)

    assert not analyse(source, loose).term_findings


def test_a_decimal_point_is_not_a_sentence_boundary(lexicon):
    """The exception the rule needs, or "1.5" becomes two sentences."""
    analysis = _analyse_text("XAUUSD 15m. I enter on a large 1.5 wick.", lexicon)
    assert [f.term.term_id for f in analysis.parameterised] == ["large_wick"]
    assert "1.5" in analysis.parameterised[0].occurrences[0].text


def test_no_character_class_in_a_term_pattern_accepts_a_sentence_terminator(lexicon):
    """The data-side half, checked over every term rather than the four fixed.

    Belt and braces beside the match-time rule above: a slot that cannot
    consume a terminator cannot produce a boundary-spanning match in the first
    place. A decimal point still reaches the slot as an explicit escaped
    literal, which is why this looks only at character classes.
    """
    terminators = set(lexicon.sentence_terminators)
    for term in lexicon.terms:
        for klass in re.findall(r"\[(?:[^\]\\]|\\.)*\]", term.raw_pattern):
            literal = re.sub(r"\\.", "", klass[1:-1])
            assert not terminators & set(literal), (term.term_id, klass)


def test_a_term_pattern_may_not_hide_a_wildcard_outside_its_declared_slot(tmp_path):
    """The loader is what makes the slot rule survive the next term.

    The analyser can only decline to treat wildcard text as ruled if it can see
    where the wildcard is, and the declared group is the only thing that tells
    it. An undeclared wildcard is therefore not a style problem; it is this
    defect, re-armed. So the lexicon does not load.
    """
    source = json.loads(
        (FIXTURES / "lexicon_advisory.json").read_text(encoding="utf-8")
    )
    source["terms"][0]["pattern"] = r"\b(?:large|big)(?:[ -][a-z0-9.%]+){0,3}[ -]wicks?\b"
    broken = tmp_path / "undeclared_wildcard.json"
    broken.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(LexiconError, match="outside the declared"):
        load_lexicon(broken)


#: Everything that can land in a modifier slot: every REFUSE term's own
#: phrasing, one word from every declared marker family, and innocuous filler
#: that must NOT trip anything. Deliberately not a list of the strings from the
#: audit report — the point is the class, not the three sentences that exposed
#: it.
_SLOT_PROBES = [
    "",
    "near resistance",
    "at support",
    "into supply",
    "approaching the demand zone",
    "strong trend",
    "weak momentum",
    "good breakout",
    "clean break",
    "confirmation candle",
    "confirmed close",
    "large",
    "strong",
    "good",
    "clean",
    "healthy",
    "near",
    "roughly",
    "significant",
    "sharp",
    "extended",
    "deep",
    "quick",
    "enough",
    "several",
    "ideally",
    "key",
    "15m",
    "rejection",
    "directional",
    "upper",
    "1.5",
]

#: One carrier per shipped term that declares a slot, plus a couple that put a
#: sentence boundary next to the slot.
_SLOT_CARRIERS = [
    "XAUUSD 15m. I enter on a large {} wick.",
    "XAUUSD 15m. I take a no-wick {} candle.",
    "XAUUSD 15m. I need a no wick {} confirmation.",
    "XAUUSD 15m. Only with a strong {} trend.",
    "XAUUSD 15m. Only on a good {} breakout.",
    "XAUUSD 15m. I enter on a large {} wick. My stop is 2 ATR below entry.",
    "XAUUSD 15m. I want a large {} trade. some wick setups only.",
]


def test_no_ruled_term_match_can_hide_a_refuse_term_or_a_marker(lexicon):
    """The class-level guarantee, asserted rather than described.

    ``docs/AMBIGUITY-POLICY.md`` promises "no third path, and no silent one".
    That sentence was false for three audits and nothing failed, because the
    only thing enforcing it was prose. This checks it directly:

    for every source below, every REFUSE term and every discretionary marker
    the lexicon can find in the text is either inside a ruled term's LITERAL
    span — genuinely part of a phrase the lexicon has settled — or it appears
    in the emitted refusal. There is no third outcome, and a term match cannot
    create one by swallowing text into its wildcard.
    """
    refuse_terms = [t for t in lexicon.terms if t.disposition != PARAMETERISE]
    checked = 0
    for carrier in _SLOT_CARRIERS:
        for probe in _SLOT_PROBES:
            source = carrier.format(probe).replace("  ", " ")
            analysis = analyse(source, lexicon)
            norm = analysis.normalised
            spans = analysis.ruled_spans

            hidden = []
            for term in refuse_terms:
                for match in term.pattern.finditer(norm):
                    if match.end() <= match.start():
                        continue
                    if any(s <= match.start() and match.end() <= e for s, e in spans):
                        continue
                    hidden.append(norm[match.start() : match.end()])
            for marker in lexicon.markers:
                for match in marker.pattern.finditer(norm):
                    if match.end() <= match.start():
                        continue
                    if any(s <= match.start() and match.end() <= e for s, e in spans):
                        continue
                    hidden.append(norm[match.start() : match.end()])
            if not hidden:
                continue

            checked += 1
            request = build_request(source, "TRADER_EXPLANATION", "unit test")
            result = intake(request, lexicon=lexicon, generated_at_utc=STAMP)
            assert not result.sufficiently_defined, (source, hidden)
            emitted = json.dumps(result.document).lower()
            for phrase in hidden:
                assert phrase in emitted, (source, phrase)
    assert checked > 100, "the corpus stopped exercising the property"


# --- the ruling document and the emitted document must agree ------------------


def _attribution_checklist() -> str:
    """The "what every draft carries" bullet list, from the policy document.

    Cut at the paragraph that follows it, because that paragraph deliberately
    names a REMOVED field (``hsa_guessed``) and explains why it is gone. The
    checklist is a description of what IS emitted; the paragraph is history.
    """
    text = POLICY.read_text(encoding="utf-8")
    start = text.index("## Attribution: a parameterisation is never silent")
    end = text.index("**There is no `hsa_guessed` field", start)
    return text[start:end]


def test_the_attribution_checklist_names_what_a_draft_actually_emits():
    """A required boot artifact must not describe an output that does not exist.

    ``docs/AMBIGUITY-POLICY.md`` is loaded by ``hsa boot``, so a fresh boot
    reads this checklist as the specification of a draft's attribution block.
    It named the scan result ``NO_DECLARED_REBASING_FOUND`` — the exact
    overclaim this project withdrew, and which the SAME document explains the
    withdrawal of a few lines above. A fresh boot was being told to expect it.

    Written as a comparison rather than a spelling check, so the next stamp or
    key that drifts fails here too.
    """
    checklist = _attribution_checklist()
    quoted = set(re.findall(r"`([^`]+)`", checklist))

    result = _run("example_b_rejection_wick_sequence.txt", "TRADER_EXPLANATION")
    assert result.sufficiently_defined
    entry = result.document["resolved_terms"][0]
    resolution = entry["resolution"]
    scan = resolution["basis_conflict_scan"]
    emitted_keys = set(entry) | set(resolution) | set(scan)

    def values(node):
        if isinstance(node, dict):
            for item in node.values():
                yield from values(item)
        elif isinstance(node, list):
            for item in node:
                yield from values(item)
        elif isinstance(node, str):
            yield node

    emitted_values = set(values(entry))

    # Every stamp-shaped value the checklist names must actually be emitted.
    # This is what catches a retracted name being left in the description.
    stamps = {item for item in quoted if re.fullmatch(r"[A-Z][A-Z_]{3,}", item)}
    assert stamps, "the checklist stopped naming any emitted stamp"
    assert stamps <= emitted_values, sorted(stamps - emitted_values)

    # And every field name it lists must be a field that exists.
    named = {
        item.split(":")[0].strip()
        for item in quoted
        if re.fullmatch(r"[a-z][a-z_]*(:.*)?", item)
    }
    assert named, "the checklist stopped naming any emitted field"
    assert named <= emitted_keys, sorted(named - emitted_keys)
