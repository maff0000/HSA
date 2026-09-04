"""Strategy version lifecycle and lineage (PID lines 183-200).

The governing rule under test: a promoted version is immutable, and a
proposed modification is a separately versioned candidate that must pass the
governed evidence gates again (PID lines 185-189, acceptance criterion 13 at
PID line 262). The refusal is exercised as real behaviour, not asserted from
a docstring.
"""

from __future__ import annotations

import copy
import json

import pytest

from hsa.contracts import validate_document
from hsa.errors import HSAError
from hsa.versioning import (
    ALLOWED_STATUS_TRANSITIONS,
    CARRIED_FORWARD_REFERENCE_TYPES,
    GATE_VERDICT_REFERENCE_TYPES,
    STATUS_CANDIDATE,
    STATUS_DORMANT,
    STATUS_PROMOTED,
    STATUS_RETIRED,
    PromotedVersionImmutableError,
    VersioningError,
    apply_status_transition,
    bump_version,
    derive_candidate,
    describe_in_place_mutation,
    format_version,
    identity_of,
    is_promoted,
    lineage,
    parse_version,
    refuse_in_place_mutation,
    status_of,
    supersedes_of,
    utc_now,
)

RATIONALE = (
    "Evidence shows the trigger fires late in fast markets; the candidate "
    "widens the confirmation window and must earn promotion on its own."
)


@pytest.fixture
def promoted_package(valid_doc):
    """The W1 package fixture, taken through promotion."""
    return apply_status_transition(valid_doc("strategy_package"), STATUS_PROMOTED)


# --------------------------------------------------------------------------
# semver
# --------------------------------------------------------------------------


def test_parse_version_returns_comparable_parts():
    assert parse_version("1.2.3") == (1, 2, 3)
    assert parse_version("0.1.0") < parse_version("1.0.0")
    assert parse_version("1.9.0") < parse_version("1.10.0")


@pytest.mark.parametrize("bad", ["1.0", "1.0.0.0", "v1.0.0", "1.0.x", "01.0.0", 100])
def test_parse_version_refuses_non_semver(bad):
    with pytest.raises(VersioningError):
        parse_version(bad)


def test_format_version_round_trips():
    assert format_version(parse_version("2.11.4")) == "2.11.4"


@pytest.mark.parametrize(
    ("part", "expected"),
    [("MAJOR", "2.0.0"), ("MINOR", "1.4.0"), ("PATCH", "1.3.8")],
)
def test_bump_version(part, expected):
    assert bump_version("1.3.7", part) == expected


def test_bump_version_refuses_unknown_part():
    with pytest.raises(VersioningError, match="unknown version part"):
        bump_version("1.0.0", "REVISION")


def test_utc_now_is_contract_shaped_utc():
    """UTC is canonical (PID line 225); local time never reaches a document."""
    stamp = utc_now()
    assert stamp.endswith("Z")
    assert validate_document(
        {
            "$hsa_kind": "cer_reference",
            "strategy_id": "gold_context_breakout",
            "strategy_version": "1.0.0",
            "evidence_id": "FIXTURE-EVID-TIMESTAMP-CHECK",
            "reference_type": "RESEARCH_FINDING",
            "source": "CONTRACT_FIXTURE",
            "recorded_at_utc": stamp,
        }
    )


# --------------------------------------------------------------------------
# identity and status
# --------------------------------------------------------------------------


def test_identity_is_id_plus_version(valid_doc):
    """Acceptance criterion 10, PID line 259."""
    assert identity_of(valid_doc("strategy_package")) == (
        "gold_context_breakout",
        "1.0.0",
    )


def test_status_is_never_guessed(valid_doc):
    package = valid_doc("strategy_package")
    del package["lifecycle"]
    with pytest.raises(VersioningError, match="no lifecycle object"):
        status_of(package)


def test_is_promoted_covers_every_post_promotion_status(promoted_package):
    assert is_promoted(promoted_package)
    assert is_promoted(apply_status_transition(promoted_package, STATUS_DORMANT))
    assert is_promoted(apply_status_transition(promoted_package, STATUS_RETIRED))


def test_a_candidate_is_not_promoted(valid_doc):
    package = valid_doc("strategy_package")
    assert status_of(package) == STATUS_CANDIDATE
    assert not is_promoted(package)


# --------------------------------------------------------------------------
# derive_candidate — acceptance criterion 13
# --------------------------------------------------------------------------


def test_derived_candidate_is_a_valid_strategy_package(promoted_package):
    candidate = derive_candidate(promoted_package, RATIONALE)
    assert validate_document(candidate) == "strategy_package"


def test_derived_candidate_preserves_identity_and_bumps_version(promoted_package):
    """Identity is preserved across versions (PID line 259)."""
    candidate = derive_candidate(promoted_package, RATIONALE)
    assert candidate["strategy_id"] == promoted_package["strategy_id"]
    assert candidate["strategy_version"] == "1.1.0"
    assert candidate["lifecycle"]["status"] == STATUS_CANDIDATE


def test_derived_candidate_records_supersedes(promoted_package):
    candidate = derive_candidate(promoted_package, RATIONALE)
    supersedes = supersedes_of(candidate)
    assert supersedes == {
        "strategy_id": "gold_context_breakout",
        "strategy_version": "1.0.0",
        "rationale": RATIONALE,
    }


def test_derive_candidate_does_not_touch_the_promoted_package(promoted_package):
    before = copy.deepcopy(promoted_package)
    derive_candidate(promoted_package, RATIONALE, changes={"title": "Reworked"})
    assert promoted_package == before


def test_derived_candidate_applies_the_proposed_modification(promoted_package):
    candidate = derive_candidate(
        promoted_package,
        RATIONALE,
        changes={"title": "Gold context breakout, widened confirmation"},
    )
    assert candidate["title"] == "Gold context breakout, widened confirmation"
    assert validate_document(candidate) == "strategy_package"


def test_derived_candidate_inherits_no_gate_verdict_evidence(promoted_package):
    """PID line 189: the candidate must pass the evidence gates AGAIN.

    Inheriting the parent's promotion evidence would let a modification keep
    an approval it never earned.
    """
    promoted_package["cer_references"].append(
        {
            "$hsa_kind": "cer_reference",
            "strategy_id": "gold_context_breakout",
            "strategy_version": "1.0.0",
            "evidence_id": "FIXTURE-EVID-GOLD-0001-PROMO",
            "reference_type": "PROMOTION_EVIDENCE",
            "source": "CONTRACT_FIXTURE",
            "recorded_at_utc": "2026-09-02T16:20:00Z",
            "supports": "PROMOTION",
        }
    )
    candidate = derive_candidate(promoted_package, RATIONALE)
    inherited = {
        reference["reference_type"] for reference in candidate["cer_references"]
    }
    assert not inherited.intersection(GATE_VERDICT_REFERENCE_TYPES)
    assert inherited.issubset(set(CARRIED_FORWARD_REFERENCE_TYPES))
    assert "SOURCE_ANALYSIS" in inherited


def test_derived_candidate_carries_its_own_lineage_reference(promoted_package):
    lineage_reference = {
        "$hsa_kind": "cer_reference",
        "strategy_id": "gold_context_breakout",
        "strategy_version": "1.1.0",
        "experiment_id": "FIXTURE-EXP-GOLD-0002",
        "reference_type": "VERSION_LINEAGE",
        "source": "CONTRACT_FIXTURE",
        "recorded_at_utc": "2026-09-03T10:00:00Z",
        "supports": "INFORMATIONAL",
    }
    candidate = derive_candidate(
        promoted_package, RATIONALE, lineage_reference=lineage_reference
    )
    assert lineage_reference in candidate["cer_references"]
    assert validate_document(candidate) == "strategy_package"


def test_derive_candidate_refuses_a_never_promoted_parent(valid_doc):
    package = valid_doc("strategy_package")
    with pytest.raises(VersioningError, match="not a promoted version"):
        derive_candidate(package, RATIONALE)


@pytest.mark.parametrize("rationale", ["", "   ", None])
def test_derive_candidate_refuses_an_empty_rationale(promoted_package, rationale):
    with pytest.raises(VersioningError, match="non-empty rationale"):
        derive_candidate(promoted_package, rationale)


@pytest.mark.parametrize(
    "smuggled",
    [{"strategy_version": "1.0.0"}, {"strategy_id": "other"}, {"lifecycle": {}}],
)
def test_derive_candidate_refuses_identity_smuggled_through_changes(
    promoted_package, smuggled
):
    """An in-place edit must not be able to disguise itself as a candidate."""
    with pytest.raises(VersioningError, match="changes may not set"):
        derive_candidate(promoted_package, RATIONALE, changes=smuggled)


@pytest.mark.parametrize(
    ("bump", "expected"), [("MAJOR", "2.0.0"), ("MINOR", "1.1.0"), ("PATCH", "1.0.1")]
)
def test_derive_candidate_honours_the_bump(promoted_package, bump, expected):
    candidate = derive_candidate(promoted_package, RATIONALE, bump=bump)
    assert candidate["strategy_version"] == expected


# --------------------------------------------------------------------------
# in-place mutation refusal — PID lines 185-187
# --------------------------------------------------------------------------


def test_in_place_mutation_of_a_promoted_version_is_refused(promoted_package):
    tampered = copy.deepcopy(promoted_package)
    tampered["parameters"][0]["default"] = 999

    with pytest.raises(PromotedVersionImmutableError) as caught:
        refuse_in_place_mutation(promoted_package, tampered)

    message = str(caught.value)
    assert "refusing in-place modification of gold_context_breakout 1.0.0" in message
    assert "promoted versions are immutable (PID lines 185-187)" in message
    assert "$.parameters[0].default: 1 -> 999" in message
    assert "separately versioned candidate" in message
    assert "acceptance criterion 13" in message
    assert caught.value.changes[0].path == "$.parameters[0].default"
    assert caught.value.changes[0].before == 1
    assert caught.value.changes[0].after == 999


def test_refusal_names_every_change_it_refuses(promoted_package):
    tampered = copy.deepcopy(promoted_package)
    tampered["thesis"] = "Reworded."
    tampered["instruments"] = ["XAUUSD", "EURUSD"]

    with pytest.raises(PromotedVersionImmutableError) as caught:
        refuse_in_place_mutation(promoted_package, tampered)

    paths = {change.path for change in caught.value.changes}
    assert paths == {"$.thesis", "$.instruments"}
    assert "2 changes refused" in str(caught.value)


def test_refusal_is_an_hsa_error_so_the_cli_maps_it(promoted_package):
    """``hsa.cli`` owns exit codes; it needs only ``HSAError``."""
    tampered = copy.deepcopy(promoted_package)
    tampered["thesis"] = "Reworded."
    with pytest.raises(HSAError):
        refuse_in_place_mutation(promoted_package, tampered)


def test_refusal_reports_the_source_when_given(promoted_package):
    tampered = copy.deepcopy(promoted_package)
    tampered["thesis"] = "Reworded."
    with pytest.raises(PromotedVersionImmutableError) as caught:
        refuse_in_place_mutation(
            promoted_package, tampered, source="strategies/gold/1.0.0.json"
        )
    assert "strategies/gold/1.0.0.json" in str(caught.value)


def test_an_unchanged_promoted_package_is_not_a_mutation(promoted_package):
    refuse_in_place_mutation(promoted_package, copy.deepcopy(promoted_package))
    assert describe_in_place_mutation(promoted_package, promoted_package) == []


def test_a_new_version_is_never_an_in_place_mutation(promoted_package):
    """The correct path stays open: change the version, not the document."""
    candidate = derive_candidate(promoted_package, RATIONALE)
    refuse_in_place_mutation(promoted_package, candidate)
    assert describe_in_place_mutation(promoted_package, candidate) == []


def test_editing_a_candidate_is_allowed(valid_doc):
    """Only PROMOTED versions are frozen; a candidate is still being written."""
    package = valid_doc("strategy_package")
    edited = copy.deepcopy(package)
    edited["thesis"] = "Sharper thesis."
    assert describe_in_place_mutation(package, edited) == []


def test_comparing_different_strategies_is_refused(promoted_package):
    other = copy.deepcopy(promoted_package)
    other["strategy_id"] = "wick_rejection_sequence"
    with pytest.raises(VersioningError, match="different strategies"):
        describe_in_place_mutation(promoted_package, other)


# --------------------------------------------------------------------------
# lifecycle transitions — dormancy is not failure (PID lines 195, 197)
# --------------------------------------------------------------------------


def test_a_promoted_version_may_go_dormant_and_reactivate(promoted_package):
    dormant = apply_status_transition(promoted_package, STATUS_DORMANT)
    assert status_of(dormant) == STATUS_DORMANT
    assert validate_document(dormant) == "strategy_package"

    reactivated = apply_status_transition(dormant, STATUS_PROMOTED)
    assert status_of(reactivated) == STATUS_PROMOTED


def test_going_dormant_is_not_an_in_place_mutation(promoted_package):
    """Activation state moves; the specification does not."""
    dormant = apply_status_transition(promoted_package, STATUS_DORMANT)
    assert describe_in_place_mutation(promoted_package, dormant) == []


def test_a_status_change_plus_a_content_edit_is_still_refused(promoted_package):
    """A permitted transition does not smuggle a specification edit through."""
    tampered = apply_status_transition(promoted_package, STATUS_DORMANT)
    tampered["thesis"] = "Reworded."
    with pytest.raises(PromotedVersionImmutableError) as caught:
        refuse_in_place_mutation(promoted_package, tampered)
    assert {change.path for change in caught.value.changes} == {"$.thesis"}


def test_nothing_ever_returns_to_candidate(promoted_package):
    with pytest.raises(VersioningError, match="refusing lifecycle transition"):
        apply_status_transition(promoted_package, STATUS_CANDIDATE)


def test_a_retired_version_transitions_nowhere(promoted_package):
    retired = apply_status_transition(promoted_package, STATUS_RETIRED)
    with pytest.raises(VersioningError, match="allowed from RETIRED is nothing"):
        apply_status_transition(retired, STATUS_PROMOTED)


def test_a_demotion_disguised_as_a_status_change_is_refused(promoted_package):
    """Hand-editing status back to CANDIDATE is an in-place mutation."""
    tampered = copy.deepcopy(promoted_package)
    tampered["lifecycle"]["status"] = STATUS_CANDIDATE
    with pytest.raises(PromotedVersionImmutableError) as caught:
        refuse_in_place_mutation(promoted_package, tampered)
    assert {change.path for change in caught.value.changes} == {
        "$.lifecycle.status"
    }


def test_transition_table_never_leads_back_to_candidate():
    for allowed in ALLOWED_STATUS_TRANSITIONS.values():
        assert STATUS_CANDIDATE not in allowed


def test_transition_to_the_same_status_is_a_no_op(promoted_package):
    assert apply_status_transition(promoted_package, STATUS_PROMOTED) == (
        promoted_package
    )


def test_unknown_status_is_refused(promoted_package):
    with pytest.raises(VersioningError, match="unknown lifecycle status"):
        apply_status_transition(promoted_package, "ARCHIVED")


# --------------------------------------------------------------------------
# lineage
# --------------------------------------------------------------------------


def test_lineage_resolves_across_a_promoted_version_and_its_candidate(
    promoted_package,
):
    candidate = derive_candidate(promoted_package, RATIONALE)
    links = lineage([candidate, promoted_package])

    assert [link.strategy_version for link in links] == ["1.0.0", "1.1.0"]
    assert links[0].status == STATUS_PROMOTED
    assert links[0].supersedes_version is None
    assert links[1].status == STATUS_CANDIDATE
    assert links[1].supersedes_version == "1.0.0"
    assert links[1].rationale == RATIONALE


def test_lineage_orders_by_semver_not_string(promoted_package):
    versions = ["1.0.0", "1.2.0", "1.10.0", "2.0.0"]
    packages = []
    for version in versions:
        package = copy.deepcopy(promoted_package)
        package["strategy_version"] = version
        packages.append(package)
    assert [link.strategy_version for link in lineage(reversed(packages))] == versions


def test_lineage_refuses_a_mixed_strategy(promoted_package):
    other = copy.deepcopy(promoted_package)
    other["strategy_id"] = "wick_rejection_sequence"
    with pytest.raises(VersioningError, match="across different strategies"):
        lineage([promoted_package, other])


def test_lineage_refuses_a_duplicate_version(promoted_package):
    with pytest.raises(VersioningError, match="duplicate version"):
        lineage([promoted_package, copy.deepcopy(promoted_package)])


def test_lineage_of_a_single_original(valid_doc):
    links = lineage([valid_doc("strategy_package")])
    assert len(links) == 1
    assert links[0].supersedes_version is None


# --------------------------------------------------------------------------
# acceptance criterion 13, end to end (PID line 262)
# --------------------------------------------------------------------------


def test_acceptance_criterion_13_end_to_end(promoted_package, tmp_path):
    """Propose a modification to a promoted strategy; get a new version.

    The promoted document on disk must be byte-identical afterwards: the
    modification produced a separately versioned candidate and did not tweak
    the live strategy in place (PID lines 185-189).
    """
    promoted_path = tmp_path / "gold_context_breakout-1.0.0.json"
    promoted_path.write_text(
        json.dumps(promoted_package, indent=2) + "\n", encoding="utf-8"
    )
    before = promoted_path.read_bytes()

    # The tempting move: edit the promoted package. Refused.
    proposed = copy.deepcopy(promoted_package)
    proposed["parameters"][0]["default"] = 999
    with pytest.raises(PromotedVersionImmutableError):
        refuse_in_place_mutation(promoted_package, proposed, source=str(promoted_path))

    # The governed move: a separately versioned candidate.
    candidate = derive_candidate(
        promoted_package,
        RATIONALE,
        changes={
            "parameters": [
                {**promoted_package["parameters"][0], "default": 999},
                *promoted_package["parameters"][1:],
            ]
        },
    )
    candidate_path = tmp_path / "gold_context_breakout-1.1.0.json"
    candidate_path.write_text(
        json.dumps(candidate, indent=2) + "\n", encoding="utf-8"
    )

    assert validate_document(candidate) == "strategy_package"
    assert candidate["strategy_version"] == "1.1.0"
    assert candidate["lifecycle"]["status"] == STATUS_CANDIDATE
    assert candidate["parameters"][0]["default"] == 999
    assert supersedes_of(candidate)["strategy_version"] == "1.0.0"

    # The promoted version is untouched, on disk and in memory.
    assert promoted_path.read_bytes() == before
    assert promoted_package["parameters"][0]["default"] == 1
    assert [link.strategy_version for link in lineage([promoted_package, candidate])] == [
        "1.0.0",
        "1.1.0",
    ]
