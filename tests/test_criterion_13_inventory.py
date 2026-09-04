"""Acceptance criterion 13 against the REAL strategy inventory.

> **PID line 262** — *produce a separately versioned candidate rather than
> mutate an existing promoted strategy.*

``tests/test_versioning.py`` proves criterion 13 over synthetic documents.
This file proves it over ``strategies/gold_context_breakout/1.0.0/`` — the
governed package the repository actually ships — and holds the honesty
invariants that decide when the inventory may hold a second version.

WHY THERE IS NO ``strategies/gold_context_breakout/1.1.0/`` YET
--------------------------------------------------------------
Landing a real 1.1.0 candidate in the inventory needs a promoted parent:
``derive_candidate`` refuses a parent that was never promoted, because a
version that has not been through the gates is not frozen, so it is edited
directly rather than superseded (``docs/VERSIONING.md`` §3). 1.0.0 is a
``CANDIDATE``, and it cannot honestly become anything else — its own
``acceptance_criteria`` demand at least 100 qualifying matches, a measured
expectancy and an ungated control arm, and HSA has no backtester, no market
data and no live CER with which to produce any of that. Promoting it to
unblock a test would be manufacturing the exact verdict the fixtures were
just reworded to stop claiming.

So this file proves everything about criterion 13 that is honestly
provable today, and is written so that it gains teeth rather than needing a
rewrite the day a genuine promotion happens:

* the governed refusal, run against the real on-disk package;
* the positive path — derivation of a 1.1.0 candidate with a substantive
  parameter revision — run against the real package's content, with the
  promotion done IN MEMORY as a declared test scaffold that is never
  written anywhere;
* ``strategies/gold_context_breakout/1.0.0/`` byte-identical throughout;
* an inventory invariant that fails if any package is ever marked promoted
  without live CER evidence behind it, and a derivation invariant that
  checks any superseding version the inventory does come to hold.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from hsa.cer import SOURCE_CER_LIVE
from hsa.contracts import read_json_file, validate_document
from hsa.semantics import Catalogue, check_package
from hsa.versioning import (
    CARRIED_FORWARD_REFERENCE_TYPES,
    GATE_VERDICT_REFERENCE_TYPES,
    STATUS_CANDIDATE,
    STATUS_PROMOTED,
    SUPERSEDABLE_STATUSES,
    PromotedVersionImmutableError,
    VersioningError,
    apply_status_transition,
    derive_candidate,
    identity_of,
    lineage,
    refuse_in_place_mutation,
    status_of,
    supersedes_of,
)

REPO = Path(__file__).resolve().parent.parent
STRATEGIES = REPO / "strategies"
GOLD = STRATEGIES / "gold_context_breakout"
GOLD_1_0_0 = GOLD / "1.0.0"

#: The revision this file proposes when it exercises the positive path. It
#: is substantive on purpose: shortening the window a latched 4H context
#: stays usable changes which setups the chain can ever emit, and it touches
#: four coupled locations, which is precisely why a revision is a new version
#: rather than an edit.
PROPOSED_WINDOW_BARS = 12

PROPOSED_RATIONALE = (
    "The thesis is that the 4H regime carries information about the next 5M "
    "breakout. A 30-bar latch keeps a context usable for five trading days, "
    "which is longer than the regime claim itself is argued to hold, so the "
    "gate may be admitting setups the thesis does not actually cover. The "
    "proposal is to shorten the latch to %d closed 4H bars and re-evaluate "
    "the ungated control arm against it. This is a claim about the thesis, "
    "not about how often the strategy fires (PID line 196)."
    % PROPOSED_WINDOW_BARS
)


def _digest(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _inventory_packages() -> list[Path]:
    return sorted(STRATEGIES.glob("*/*/package.json"))


def _revised_expiry(expiry: dict, previous: int) -> dict:
    revised = copy.deepcopy(expiry)
    revised["expires_after_bars"] = PROPOSED_WINDOW_BARS
    revised["expiry_rule"] = revised["expiry_rule"].replace(
        "%d closed 4H bars" % previous,
        "%d closed 4H bars" % PROPOSED_WINDOW_BARS,
    )
    return revised


def _proposed_changes(package: dict) -> dict:
    """The substantive revision, as a ``derive_candidate`` changes mapping.

    ``context_window_bars`` governs ``expiry.expires_after_bars``, the prose
    in ``expiry.expiry_rule``, and the same expiry block on the EMBEDDED
    chain, which the package must agree with (PID lines 135-137). Four
    coupled locations move together; a candidate that changed one of them
    would be internally inconsistent, and ``hsa.semantics.check_package``
    says so. That coupling is the practical reason a revision is a new
    version rather than an edit.
    """
    parameters = copy.deepcopy(package["parameters"])
    window = next(
        parameter
        for parameter in parameters
        if parameter["name"] == "context_window_bars"
    )
    previous = window["default"]
    window["default"] = PROPOSED_WINDOW_BARS
    window["description"] = (
        "%s Revised from %d to %d in this candidate: %s"
        % (window["description"], previous, PROPOSED_WINDOW_BARS, PROPOSED_RATIONALE)
    )

    chain = copy.deepcopy(package["chain"])
    chain["expiry"] = _revised_expiry(chain["expiry"], previous)

    return {
        "parameters": parameters,
        "expiry": _revised_expiry(package["expiry"], previous),
        "chain": chain,
    }


@pytest.fixture
def gold_package() -> dict:
    return read_json_file(GOLD_1_0_0 / "package.json")


# --------------------------------------------------------------------------
# what the inventory holds, and what it may claim
# --------------------------------------------------------------------------


def test_the_inventory_holds_the_example_a_package():
    """If this fails the inventory moved and the rest of this file is stale."""
    assert (GOLD_1_0_0 / "package.json").is_file()
    assert identity_of(read_json_file(GOLD_1_0_0 / "package.json")) == (
        "gold_context_breakout",
        "1.0.0",
    )


def test_no_package_is_marked_promoted_without_live_cer_evidence():
    """The invariant that makes a fabricated promotion fail the suite.

    Promotion is an evidence-gated act (``docs/VERSIONING.md`` §1). CER is
    not live, so no package may carry a status that claims it passed a gate.
    The moment CER goes live and a real promotion happens, this test still
    passes — it asks for CER_LIVE promotion evidence, not for CANDIDATE.
    """
    for path in _inventory_packages():
        package = read_json_file(path)
        status = status_of(package)
        if status not in SUPERSEDABLE_STATUSES:
            continue
        promotion_evidence = [
            reference
            for reference in package.get("cer_references", [])
            if reference.get("reference_type") == "PROMOTION_EVIDENCE"
            and reference.get("source") == SOURCE_CER_LIVE
        ]
        assert promotion_evidence, (
            "%s is %s but carries no CER_LIVE promotion evidence. A status is "
            "not a gate: promotion is an evidence-gated act (PID line 189)."
            % (path.relative_to(REPO), status)
        )


def test_any_superseding_version_the_inventory_holds_is_a_governed_derivation():
    """Vacuously true today; the check that a real 1.1.0 must satisfy.

    Written now rather than alongside the future 1.1.0, so the rules a
    derived version must meet are on the record before anyone derives one.
    """
    packages = {path: read_json_file(path) for path in _inventory_packages()}
    by_identity = {identity_of(package): package for package in packages.values()}

    for path, package in packages.items():
        supersedes = supersedes_of(package)
        if supersedes is None:
            continue
        where = path.relative_to(REPO)
        strategy_id, _ = identity_of(package)

        assert supersedes.get("strategy_id") == strategy_id, (
            "%s supersedes a different strategy; a lineage crosses versions, "
            "never strategies" % where
        )
        rationale = supersedes.get("rationale")
        assert isinstance(rationale, str) and rationale.strip(), (
            "%s records no rationale; a redesign always says why" % where
        )

        parent_identity = (strategy_id, supersedes.get("strategy_version"))
        parent = by_identity.get(parent_identity)
        assert parent is not None, (
            "%s supersedes %s, which is not in the inventory: the superseded "
            "version is kept, never replaced in place" % (where, parent_identity)
        )
        assert status_of(parent) in SUPERSEDABLE_STATUSES, (
            "%s supersedes a version that was never promoted. A candidate is "
            "not frozen, so it is edited directly rather than superseded "
            "(docs/VERSIONING.md §3)." % where
        )
        assert status_of(package) == STATUS_CANDIDATE, (
            "%s supersedes an earlier version but is not a CANDIDATE; a "
            "derived version has to earn its own verdict" % where
        )
        inherited = {
            reference.get("reference_type")
            for reference in package.get("cer_references", [])
        }
        assert not inherited.intersection(GATE_VERDICT_REFERENCE_TYPES), (
            "%s inherited a verdict from the version it supersedes; it must "
            "pass the governed evidence gates again (PID line 189)" % where
        )


# --------------------------------------------------------------------------
# the governed refusal, against the real package
# --------------------------------------------------------------------------


def test_deriving_from_the_real_candidate_package_is_refused(gold_package):
    """Criterion 13's protection, exercised on the shipped inventory.

    This is why no 1.1.0 exists. The refusal is correct behaviour and must
    not be weakened to make a candidate easier to produce.
    """
    assert status_of(gold_package) == STATUS_CANDIDATE

    with pytest.raises(VersioningError) as raised:
        derive_candidate(gold_package, PROPOSED_RATIONALE)

    rendered = str(raised.value)
    assert "gold_context_breakout 1.0.0" in rendered
    assert "it is CANDIDATE, not a promoted version" in rendered


def test_the_promotion_gate_for_the_real_package_is_not_satisfiable_today(
    gold_package,
):
    """The concrete reason 1.0.0 cannot honestly be promoted.

    Its own acceptance criteria — declared before any evidence existed, so
    they cannot be moved to fit a result — require a measured population.
    HSA has no backtester, no market data feed and no live CER, all of which
    are explicit PID non-goals or not-yet-live.
    """
    criteria = {
        criterion["criterion_id"]: criterion
        for criterion in gold_package["acceptance_criteria"]
    }
    sample = criteria["sufficient_qualifying_sample"]
    assert sample["comparator"] == ">="
    assert sample["threshold"] >= gold_package["evidence_requirements"][
        "minimum_sample_size"
    ]

    assert "PROMOTION_EVIDENCE" in gold_package["evidence_requirements"][
        "required_cer_evidence_types"
    ]
    live = [
        reference
        for reference in gold_package["cer_references"]
        if reference["source"] == SOURCE_CER_LIVE
    ]
    assert live == [], "no reference on this package resolves in a live CER"


# --------------------------------------------------------------------------
# the positive path, over the real package's content
# --------------------------------------------------------------------------


@pytest.fixture
def scaffold_promoted(gold_package) -> dict:
    """1.0.0 with ``lifecycle.status`` PROMOTED, IN MEMORY ONLY.

    A TEST SCAFFOLD, not a promotion. Nothing here is written to disk, and
    ``test_the_inventory_is_byte_identical_after_all_of_this`` proves it.
    It exists so criterion 13's positive path can be exercised against the
    real package's content instead of a synthetic document.
    """
    return apply_status_transition(gold_package, STATUS_PROMOTED)


def test_the_scaffold_is_a_permitted_transition_and_nothing_more(
    gold_package, scaffold_promoted
):
    assert status_of(scaffold_promoted) == STATUS_PROMOTED
    assert status_of(gold_package) == STATUS_CANDIDATE, "the input was mutated"
    without_status = copy.deepcopy(scaffold_promoted)
    without_status["lifecycle"]["status"] = STATUS_CANDIDATE
    assert without_status == gold_package, "the scaffold changed the specification"


def test_a_derived_candidate_is_a_new_version_carrying_a_real_revision(
    gold_package, scaffold_promoted
):
    candidate = derive_candidate(
        scaffold_promoted,
        PROPOSED_RATIONALE,
        bump="MINOR",
        changes=_proposed_changes(gold_package),
        created_at_utc="2026-09-04T00:00:00Z",
    )

    assert candidate["strategy_id"] == "gold_context_breakout", "identity survives"
    assert candidate["strategy_version"] == "1.1.0"
    assert candidate["lifecycle"]["status"] == STATUS_CANDIDATE

    supersedes = candidate["lifecycle"]["supersedes"]
    assert supersedes["strategy_id"] == "gold_context_breakout"
    assert supersedes["strategy_version"] == "1.0.0"
    assert supersedes["rationale"] == PROPOSED_RATIONALE

    window = next(
        parameter
        for parameter in candidate["parameters"]
        if parameter["name"] == "context_window_bars"
    )
    assert window["default"] == PROPOSED_WINDOW_BARS
    assert candidate["expiry"]["expires_after_bars"] == PROPOSED_WINDOW_BARS
    assert candidate["chain"]["expiry"]["expires_after_bars"] == PROPOSED_WINDOW_BARS
    assert "%d closed 4H bars" % PROPOSED_WINDOW_BARS in candidate["expiry"][
        "expiry_rule"
    ]
    assert candidate != gold_package, "a cosmetic version bump is not a revision"


def test_a_derived_candidate_inherits_no_verdict(gold_package, scaffold_promoted):
    """PID line 189: it must pass the governed evidence gates AGAIN."""
    parent_types = {
        reference["reference_type"] for reference in gold_package["cer_references"]
    }
    candidate = derive_candidate(
        scaffold_promoted,
        PROPOSED_RATIONALE,
        changes=_proposed_changes(gold_package),
        created_at_utc="2026-09-04T00:00:00Z",
    )
    candidate_types = {
        reference["reference_type"] for reference in candidate["cer_references"]
    }

    assert not candidate_types.intersection(GATE_VERDICT_REFERENCE_TYPES)
    assert candidate_types == parent_types.intersection(
        CARRIED_FORWARD_REFERENCE_TYPES
    )


def test_a_derived_candidate_validates_structurally_and_semantically(
    gold_package, scaffold_promoted
):
    """Exactly as 1.0.0 does: frozen schema, then the cross-field rules."""
    candidate = derive_candidate(
        scaffold_promoted,
        PROPOSED_RATIONALE,
        changes=_proposed_changes(gold_package),
        created_at_utc="2026-09-04T00:00:00Z",
    )
    assert validate_document(candidate, source="derived 1.1.0") == "strategy_package"
    assert check_package(candidate, catalogue=Catalogue.from_directory()) == []


def test_the_two_versions_form_a_lineage(gold_package, scaffold_promoted):
    candidate = derive_candidate(
        scaffold_promoted,
        PROPOSED_RATIONALE,
        changes=_proposed_changes(gold_package),
        created_at_utc="2026-09-04T00:00:00Z",
    )
    links = lineage([candidate, scaffold_promoted])
    assert [link.strategy_version for link in links] == ["1.0.0", "1.1.0"]
    assert links[0].supersedes_version is None
    assert links[1].supersedes_version == "1.0.0"
    assert links[1].rationale == PROPOSED_RATIONALE


def test_the_same_revision_applied_in_place_is_refused(gold_package, scaffold_promoted):
    """The other half of criterion 13: the edit that must never happen."""
    edited = copy.deepcopy(scaffold_promoted)
    edited.update(_proposed_changes(gold_package))

    with pytest.raises(PromotedVersionImmutableError) as raised:
        refuse_in_place_mutation(
            scaffold_promoted,
            edited,
            source=str(GOLD_1_0_0.relative_to(REPO) / "package.json"),
        )

    rendered = str(raised.value)
    assert "gold_context_breakout 1.0.0" in rendered
    assert "$.expiry.expires_after_bars: 30 -> %d" % PROPOSED_WINDOW_BARS in rendered
    assert "derive_candidate()" in rendered


# --------------------------------------------------------------------------
# 1.0.0 is untouched by every one of the above
# --------------------------------------------------------------------------


def test_the_inventory_is_byte_identical_after_all_of_this(tmp_path, monkeypatch):
    """Nothing above writes to the inventory — the in-memory promotion least
    of all. HSA proposes versions; Git records them (PID line 226)."""
    before = _digest(GOLD_1_0_0)
    assert before, "the 1.0.0 directory is empty"
    monkeypatch.chdir(tmp_path)

    package = read_json_file(GOLD_1_0_0 / "package.json")
    with pytest.raises(VersioningError):
        derive_candidate(package, PROPOSED_RATIONALE)

    promoted = apply_status_transition(package, STATUS_PROMOTED)
    candidate = derive_candidate(
        promoted,
        PROPOSED_RATIONALE,
        changes=_proposed_changes(package),
        created_at_utc="2026-09-04T00:00:00Z",
    )
    validate_document(candidate, source="derived 1.1.0")
    check_package(candidate, catalogue=Catalogue.from_directory())
    lineage([promoted, candidate])

    assert _digest(GOLD_1_0_0) == before, "the 1.0.0 directory changed"
    assert json.loads((GOLD_1_0_0 / "package.json").read_text(encoding="utf-8")) == (
        package
    )
    assert list(tmp_path.iterdir()) == [], "the exercise created files of its own"
