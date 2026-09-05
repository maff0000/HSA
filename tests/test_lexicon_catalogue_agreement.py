"""Intake's ruling and the catalogue's realisation of it must not drift.

``docs/AMBIGUITY-POLICY.md`` is what lets HSA parameterise "large wick"
instead of refusing it. That ruling is only worth anything if the number
intake hands over is the number the catalogue actually implements. If the two
diverge, HSA keeps *claiming* a ratified basis while the strategy quietly runs
on a different one — which is the silent guess PID line 39 forbids, wearing
the paperwork of a ratified parameter.

The two files were written independently and nothing mechanically linked them.
They used different parameter names (``min_wick_to_range_ratio`` against
``wick_to_range_ratio_min``) and different allowed ranges (0.3-0.9 against
0.3-0.95). Matching on names would have been a convention, and a convention
that was already broken. So the link is DECLARED, in the lexicon, as
``realised_by``: it names the catalogue ``strategy_id``, ``strategy_version``
and parameter that each ruled parameter is implemented as. This module is the
enforcement.

It fails when:

* a PARAMETERISE term declares a parameter with no realisation;
* a link names a catalogue entry, version or parameter that does not exist;
* the two sides disagree on type, units, default or allowed range;
* the two sides stop describing the same measurement basis;
* the catalogue entry stops providing a fact the declared basis is derived
  from, or starts consuming one the lexicon has not accounted for;
* a REFUSE term claims a realisation it was refused.

This is also the only place that reads both files. Intake must not depend on
the catalogue at runtime: the lexicon is a self-contained ruling, and making
``hsa intake`` load the catalogue would couple the refusal path to strategy
inventory. The coupling belongs in a test, not in the product.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hsa.intake import load_lexicon
from hsa.intake.lexicon import PARAMETERISE, REFUSE, LexiconError

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOGUE_DIR = REPO_ROOT / "catalogue" / "atomic"
POLICY = REPO_ROOT / "docs" / "AMBIGUITY-POLICY.md"


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def lexicon():
    """The SHIPPED lexicon, not a fixture copy.

    The governed ruling is the file intake loads by default. A candidate
    lexicon supplied through ``HSA_INTAKE_LEXICON`` is a reviewer's working
    copy and is deliberately not what this module asserts on.
    """
    return load_lexicon()


@pytest.fixture(scope="module")
def catalogue() -> dict:
    entries = {}
    for path in sorted(CATALOGUE_DIR.glob("*.json")):
        document = _load(path)
        entries[document["strategy_id"]] = document
    assert entries, "catalogue/atomic contains no entries"
    return entries


# --- the checks, as functions, so they can be shown to fire ------------------


def resolve_catalogue_parameter(link, catalogue) -> tuple[dict | None, list[str]]:
    """The linked catalogue parameter, or the reasons it could not be found."""
    strategy_id = link["catalogue_strategy_id"]
    entry = catalogue.get(strategy_id)
    if entry is None:
        return None, [
            "names catalogue strategy %r, which catalogue/atomic does not hold"
            % strategy_id
        ]
    if entry["strategy_version"] != link["catalogue_strategy_version"]:
        return None, [
            "pins %s %s but the catalogue holds version %s"
            % (
                strategy_id,
                link["catalogue_strategy_version"],
                entry["strategy_version"],
            )
        ]
    for parameter in entry["parameters"]:
        if parameter["name"] == link["catalogue_parameter"]:
            return parameter, []
    return None, [
        "names parameter %r, which %s does not declare (it declares: %s)"
        % (
            link["catalogue_parameter"],
            strategy_id,
            ", ".join(p["name"] for p in entry["parameters"]),
        )
    ]


def parameter_disagreements(term, link, lexicon_parameter, catalogue_parameter):
    """Every way the ruling and its realisation can contradict each other."""
    found = []
    for key in ("type", "units", "default"):
        if lexicon_parameter[key] != catalogue_parameter[key]:
            found.append(
                "%s: lexicon declares %s=%r, catalogue declares %s=%r"
                % (
                    key,
                    lexicon_parameter["name"],
                    lexicon_parameter[key],
                    catalogue_parameter["name"],
                    catalogue_parameter[key],
                )
            )

    lexicon_domain = lexicon_parameter.get("allowed_range")
    catalogue_domain = catalogue_parameter.get("allowed_range")
    if lexicon_domain != catalogue_domain:
        # Compared whole, ``step`` included. A grid one side enforces and the
        # other does not is a real divergence: evidence swept off-grid on the
        # realisation would be evidence for a value intake calls impermissible.
        found.append(
            "allowed_range: lexicon declares %r, catalogue declares %r"
            % (lexicon_domain, catalogue_domain)
        )

    # Measurement basis. Prose cannot be compared mechanically, so the link
    # declares the phrases that must survive on BOTH sides. This is a canary,
    # not a proof: it fires when either side is rewritten onto a different
    # quantity, denominator or comparator, which is the drift that matters.
    lexicon_prose = " ".join(
        [term.measurement_basis or "", lexicon_parameter["description"]]
    ).lower()
    catalogue_prose = catalogue_parameter["description"].lower()
    for phrase in link["basis_phrases"]:
        lowered = phrase.lower()
        if lowered not in lexicon_prose:
            found.append(
                "measurement basis: %r is absent from the lexicon's own prose "
                "for %s" % (phrase, lexicon_parameter["name"])
            )
        if lowered not in catalogue_prose:
            found.append(
                "measurement basis: %r is absent from the catalogue's "
                "description of %s" % (phrase, catalogue_parameter["name"])
            )
    return found


def hermes_disagreements(relationship, entry):
    """Whether the documented basis/derivation relationship still holds."""
    found = []
    catalogue_fields = {field["field"] for field in entry["required_hermes_fields"]}
    derived_from: set[str] = set()
    for derivation in relationship["derivations"]:
        for source in derivation["derived_from"]:
            derived_from.add(source)
            if source not in catalogue_fields:
                found.append(
                    "%s is derived from %r, which %s does not consume"
                    % (derivation["basis_field"], source, entry["strategy_id"])
                )
    declared_only = {field["field"] for field in relationship["catalogue_only_fields"]}
    unaccounted = catalogue_fields - derived_from - declared_only
    if unaccounted:
        found.append(
            "%s consumes %s, which the lexicon neither derives a basis field "
            "from nor declares as catalogue-only"
            % (entry["strategy_id"], ", ".join(sorted(unaccounted)))
        )
    stale = declared_only - catalogue_fields
    if stale:
        found.append(
            "the lexicon declares %s as catalogue-only, but %s does not "
            "consume it" % (", ".join(sorted(stale)), entry["strategy_id"])
        )
    return found


# --- the link exists at all --------------------------------------------------


def test_every_ruled_parameter_declares_its_realisation(lexicon):
    """A parameterised term with no declared realisation is the defect itself.

    Intake would hand over a number with nothing saying which implementation
    is supposed to honour it, which is the state this module was written to
    end.
    """
    for term in lexicon.terms:
        if term.disposition != PARAMETERISE:
            continue
        linked = {link["lexicon_parameter"] for link in term.realised_by}
        declared = {parameter["name"] for parameter in term.parameters}
        assert declared <= linked, "%s: no realised_by for %s" % (
            term.term_id,
            ", ".join(sorted(declared - linked)),
        )
        assert term.hermes_basis_relationship is not None, (
            "%s declares a realisation but never states how its basis fields "
            "relate to the fields the realisation consumes" % term.term_id
        )


#: The keys by which a lexicon entry claims a catalogue realisation. Named
#: once so the check and its non-vacuity proof cannot drift apart.
_REALISATION_KEYS = ("realised_by", "hermes_basis_relationship")


def _realisation_claims(entry: dict) -> list[str]:
    """Which realisation keys ``entry`` declares, in declaration order."""
    return [key for key in _REALISATION_KEYS if key in entry]


def test_a_refused_term_claims_no_realisation():
    """A refusal has no measurement basis, so it can have no realisation.

    Read off the lexicon FILE, and deliberately WITHOUT the ``lexicon``
    fixture. Two independent reasons, and the second one was missed once:

    * The loaded object cannot answer the question. ``Term.realised_by``
      defaults to ``()`` and ``hermes_basis_relationship`` to ``None``, and
      the loader's REFUSE branch assigns neither, so asserting on the Term
      restates a dataclass default rather than checking the declaration.
    * Taking the fixture put the answer out of this test's reach anyway.
      ``load_lexicon()`` REFUSES the violation — the REFUSE branch of
      ``_load_term`` in ``hsa/intake/lexicon.py`` raises on either key — so
      planting one made fixture setup raise: this module reported 18 ERRORs
      and this test, the one named for the rule, never ran its body. That was
      measured, not assumed. R8 removed exactly this coupling from
      ``test_parameterised_terms_declare_a_basis_and_bounded_parameters`` in
      ``tests/test_ambiguity.py`` and left this one in place.

    So the guard and this test used to mask each other: the guard was the only
    thing enforcing the rule, and had no test that could fail; this test was
    named for the rule and could only ever error. Against the file it now
    fails, here, naming the term and what it claimed.
    ``test_the_loader_also_refuses_a_declared_realisation`` covers the guard.
    """
    declared = _load(REPO_ROOT / "hsa" / "intake" / "lexicon.json")["terms"]
    checked = 0
    for entry in declared:
        if entry.get("disposition") != REFUSE:
            continue
        assert not _realisation_claims(entry), (
            "%s is REFUSE but declares %s. A refusal has no ratified "
            "measurement basis, so there is nothing for a catalogue entry to "
            "implement" % (entry["term_id"], ", ".join(_realisation_claims(entry)))
        )
        checked += 1
    assert checked, "no REFUSE term in the lexicon; this test asserted nothing"


def test_that_refusal_check_would_see_a_declared_realisation():
    """Non-vacuity: plant the thing the test above forbids, and see it caught.

    Asserted on the PREDICATE, over the file, with no ``lexicon`` fixture —
    for the same reason the test above drops it. An earlier version of this
    docstring said a planted REFUSE realisation "loads without complaint and
    the loaded Term shows no trace of it". The first half was never true: the
    loader has refused it since R3. What IS true is that the Term is a
    useless witness either way, because the loader's REFUSE branch assigns
    neither field, so a Term can only ever show the dataclass defaults. That
    is why the declaration is the thing checked.
    """
    declared = _load(REPO_ROOT / "hsa" / "intake" / "lexicon.json")["terms"]
    entry = next(
        item for item in declared if item.get("disposition") == REFUSE
    )

    assert _realisation_claims(entry) == []
    planted = copy.deepcopy(entry)
    planted["realised_by"] = [
        {"strategy_id": "wick_rejection", "lexicon_parameter": "invented"}
    ]
    planted["hermes_basis_relationship"] = {"invented": True}
    assert _realisation_claims(planted) == [
        "realised_by",
        "hermes_basis_relationship",
    ]


@pytest.mark.parametrize("key", _REALISATION_KEYS)
def test_the_loader_also_refuses_a_declared_realisation(tmp_path, key):
    """The guard in ``hsa/intake/lexicon.py`` had no test that could fail.

    It is real and it works in shipped code, but the only test named for the
    rule took the ``lexicon`` fixture, so a planted violation raised during
    fixture setup and errored the module instead of failing the test. The
    guard was therefore enforcing an invariant nothing independently
    exercised. This runs the loader against a planted file on disk and
    requires it to refuse, per key, naming the key it refused.

    Written on a tmp_path copy: the shipped lexicon is never mutated, and
    ``load_lexicon(path)`` is the same entry point ``$HSA_INTAKE_LEXICON``
    reaches, so this is the real load path and not a re-implementation.
    """
    document = _load(REPO_ROOT / "hsa" / "intake" / "lexicon.json")
    entry = next(
        item for item in document["terms"] if item.get("disposition") == REFUSE
    )
    # Start from a term that claims nothing, so the refusal below is provably
    # a refusal of ``key`` and not of some other claim already on the entry.
    for other in _REALISATION_KEYS:
        entry.pop(other, None)
    entry[key] = (
        [{"catalogue_strategy_id": "wick_rejection", "lexicon_parameter": "invented"}]
        if key == "realised_by"
        else {"invented": True}
    )
    planted = tmp_path / "lexicon.json"
    planted.write_text(json.dumps(document, indent=2), encoding="utf-8")

    # The planted file really does declare it, so a refusal below is a
    # refusal of this, and not of some unrelated malformation.
    assert _realisation_claims(_load(planted)["terms"][
        document["terms"].index(entry)
    ]) == [key]

    with pytest.raises(LexiconError) as raised:
        load_lexicon(planted)
    assert key in str(raised.value), str(raised.value)
    assert entry["term_id"] in str(raised.value), str(raised.value)


# --- the link resolves, and the two sides agree ------------------------------


def test_every_declared_link_resolves_in_the_catalogue(lexicon, catalogue):
    for term in lexicon.terms:
        for link in term.realised_by:
            parameter, problems = resolve_catalogue_parameter(link, catalogue)
            assert parameter is not None, "%s realised_by %s" % (
                term.term_id,
                "; ".join(problems),
            )


def test_ruling_and_realisation_agree_on_every_linked_parameter(lexicon, catalogue):
    """The whole point: same basis, same default, same allowed range."""
    checked = 0
    for term in lexicon.terms:
        parameters = {p["name"]: p for p in term.parameters}
        for link in term.realised_by:
            catalogue_parameter, problems = resolve_catalogue_parameter(
                link, catalogue
            )
            assert catalogue_parameter is not None, problems
            found = parameter_disagreements(
                term,
                link,
                parameters[link["lexicon_parameter"]],
                catalogue_parameter,
            )
            assert not found, "%s %s vs %s %s disagree:\n  %s" % (
                term.term_id,
                link["lexicon_parameter"],
                link["catalogue_strategy_id"],
                link["catalogue_parameter"],
                "\n  ".join(found),
            )
            checked += 1
    assert checked, "no links were checked; the enforcement would be vacuous"


def test_the_two_wick_rulings_are_linked_by_name(lexicon):
    """Pin the specific pair the defect was found in, so a future edit that
    drops the link fails here rather than passing an empty loop."""
    links = {
        (link["lexicon_parameter"], link["catalogue_parameter"])
        for term in lexicon.terms
        for link in term.realised_by
    }
    assert ("min_wick_to_range_ratio", "wick_to_range_ratio_min") in links
    assert ("max_wick_to_range_ratio", "wick_to_range_ratio_max") in links


# --- HERMES: intake declares the basis, the catalogue declares the derivation -


def test_the_basis_fields_are_derivable_from_what_the_catalogue_consumes(
    lexicon, catalogue
):
    """The documented relationship, enforced so it cannot rot.

    Intake declares ``candle.wick_upper`` / ``candle.wick_lower`` /
    ``candle.range``; the catalogue entries consume ``candle.open/high/low/
    close`` plus ``atr``. Both lists are correct for their own purpose, and
    they are reconciled rather than aligned: every basis field is derived from
    facts the realisation supplies, and every fact the realisation consumes is
    either used by a derivation or declared catalogue-only with a reason.
    """
    checked = 0
    for term in lexicon.terms:
        relationship = term.hermes_basis_relationship
        if relationship is None:
            continue
        for link in term.realised_by:
            entry = catalogue[link["catalogue_strategy_id"]]
            found = hermes_disagreements(relationship, entry)
            assert not found, "%s vs %s:\n  %s" % (
                term.term_id,
                entry["strategy_id"],
                "\n  ".join(found),
            )
            checked += 1
    assert checked, "no basis relationships were checked"


def test_the_policy_document_states_every_declared_derivation(lexicon):
    """The prose and the data must not drift, the same way the rulings table
    and the lexicon must not (see ``tests/test_ambiguity.py``).

    ``docs/AMBIGUITY-POLICY.md`` is what a human reads. If a derivation were
    changed in the lexicon and not in the document, HSA's stated doctrine
    would describe a relationship it no longer holds to.
    """
    text = POLICY.read_text(encoding="utf-8")
    assert "basis fields" in text.lower()
    assert "derivation fields" in text.lower()
    seen = 0
    for term in lexicon.terms:
        relationship = term.hermes_basis_relationship
        if relationship is None:
            continue
        for derivation in relationship["derivations"]:
            assert derivation["expression"] in text, (
                "docs/AMBIGUITY-POLICY.md does not state the derivation %r"
                % derivation["expression"]
            )
            seen += 1
    assert seen, "no derivations were checked"


# --- guard the guard: every check above is shown to fire ---------------------
#
# A test that only ever sees agreeing inputs proves nothing. Each case below
# mutates a COPY of the real data by exactly one value and asserts the
# corresponding check reports it.


@pytest.fixture
def linked(lexicon, catalogue):
    """The real large_wick link, as mutable copies."""
    term = lexicon.term("large_wick")
    link = copy.deepcopy(dict(term.realised_by[0]))
    lexicon_parameter = copy.deepcopy(dict(term.parameters[0]))
    catalogue_parameter, problems = resolve_catalogue_parameter(link, catalogue)
    assert catalogue_parameter is not None, problems
    return term, link, lexicon_parameter, copy.deepcopy(catalogue_parameter)


def test_a_moved_default_is_caught(linked):
    term, link, lexicon_parameter, catalogue_parameter = linked
    assert parameter_disagreements(
        term, link, lexicon_parameter, catalogue_parameter
    ) == []
    catalogue_parameter["default"] = catalogue_parameter["default"] + 0.05
    found = parameter_disagreements(term, link, lexicon_parameter, catalogue_parameter)
    assert any("default" in line for line in found), found


def test_a_widened_allowed_range_is_caught(linked):
    term, link, lexicon_parameter, catalogue_parameter = linked
    domain = dict(catalogue_parameter["allowed_range"])
    domain["maximum"] = domain["maximum"] + 0.05
    catalogue_parameter["allowed_range"] = domain
    found = parameter_disagreements(term, link, lexicon_parameter, catalogue_parameter)
    assert any("allowed_range" in line for line in found), found


def test_a_reintroduced_step_is_caught(linked):
    """The original defect included a grid on one side only."""
    term, link, lexicon_parameter, catalogue_parameter = linked
    lexicon_parameter["allowed_range"] = dict(
        lexicon_parameter["allowed_range"], step=0.05
    )
    found = parameter_disagreements(term, link, lexicon_parameter, catalogue_parameter)
    assert any("allowed_range" in line for line in found), found


def test_a_changed_unit_is_caught(linked):
    term, link, lexicon_parameter, catalogue_parameter = linked
    catalogue_parameter["units"] = catalogue_parameter["units"] + "_changed"
    found = parameter_disagreements(term, link, lexicon_parameter, catalogue_parameter)
    assert any("units" in line for line in found), found


def test_a_changed_measurement_basis_is_caught(linked):
    """The realisation re-based onto ATR instead of the bar range."""
    term, link, lexicon_parameter, catalogue_parameter = linked
    catalogue_parameter["description"] = (
        "Minimum length of the rejecting wick divided by atr over atr_period."
    )
    found = parameter_disagreements(term, link, lexicon_parameter, catalogue_parameter)
    assert any("measurement basis" in line for line in found), found


def test_a_link_to_a_missing_catalogue_entry_is_caught(linked, catalogue):
    _, link, _, _ = linked
    link["catalogue_strategy_id"] = "no_such_strategy"
    parameter, problems = resolve_catalogue_parameter(link, catalogue)
    assert parameter is None
    assert "does not hold" in " ".join(problems), problems


def test_a_link_to_a_missing_catalogue_parameter_is_caught(linked, catalogue):
    _, link, _, _ = linked
    link["catalogue_parameter"] = "no_such_parameter"
    parameter, problems = resolve_catalogue_parameter(link, catalogue)
    assert parameter is None
    assert "does not declare" in " ".join(problems), problems


def test_a_link_to_an_unheld_version_is_caught(linked, catalogue):
    _, link, _, _ = linked
    link["catalogue_strategy_version"] = "9.9.9"
    parameter, problems = resolve_catalogue_parameter(link, catalogue)
    assert parameter is None
    assert "the catalogue holds version" in " ".join(problems), problems


def test_a_basis_field_the_catalogue_stopped_supplying_is_caught(lexicon, catalogue):
    relationship = lexicon.term("large_wick").hermes_basis_relationship
    entry = copy.deepcopy(catalogue["rejection_wick"])
    entry["required_hermes_fields"] = [
        field
        for field in entry["required_hermes_fields"]
        if field["field"] != "candle.open"
    ]
    found = hermes_disagreements(relationship, entry)
    assert any("candle.open" in line for line in found), found


def test_an_unaccounted_catalogue_field_is_caught(lexicon, catalogue):
    relationship = lexicon.term("large_wick").hermes_basis_relationship
    entry = copy.deepcopy(catalogue["rejection_wick"])
    entry["required_hermes_fields"].append(
        {"field": "volume.bar_volume", "purpose": "unaccounted", "timeframe": "15M"}
    )
    found = hermes_disagreements(relationship, entry)
    assert any("volume.bar_volume" in line for line in found), found
