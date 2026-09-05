"""Tests for the atomic strategy catalogue in ``catalogue/atomic``.

Two jobs. First, every entry must be a valid ``atomic_strategy`` against the
frozen contract. Second — and this is where the PID's ambiguity discipline
actually bites — every entry must be free of unquantified discretionary
language, checked mechanically against a word list rather than by review.

PID line 110 requires HSA to turn discretionary language into measurable
definitions, and lines 112-118 name *large wick*, *near resistance*, *strong
trend*, *confirmation candle* and *good breakout* as things that must not be
guessed. A reviewer reading a hundred-line JSON document will not reliably
notice the one adjective that slipped through. A test will.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from hsa.contracts import validate_document
from hsa.semantics import Catalogue

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOGUE_DIR = REPO_ROOT / "catalogue" / "atomic"

#: Concepts PID line 55 names as canonical atomic strategy examples, mapped to
#: the catalogue entry that covers each.
PID_LINE_55_COVERAGE = {
    "golden/death cross": "golden_cross",
    "breakout": "range_breakout",
    "proximity to swing high/low": "swing_level_proximity",
    "rejection wick": "rejection_wick",
    "no-wick candle": "no_wick_candle",
    "engulfing": "engulfing_candle",
    "momentum": "momentum_thrust",
    "volatility expansion": "volatility_expansion",
    "structure break": "structure_break",
    "retest": "level_retest",
    "compression": "range_compression",
}


def _entry_paths() -> list[Path]:
    paths = sorted(CATALOGUE_DIR.glob("*.json"))
    assert paths, "catalogue/atomic contains no entries"
    return paths


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


ENTRY_PATHS = _entry_paths()
ENTRY_IDS = [path.stem for path in ENTRY_PATHS]


@pytest.fixture(params=ENTRY_PATHS, ids=ENTRY_IDS)
def entry_path(request) -> Path:
    return request.param


@pytest.fixture
def entry(entry_path: Path) -> dict:
    return _load(entry_path)


# --- the discretionary-language scan -----------------------------------------

#: Keys whose string values are human-readable prose and are therefore scanned.
#: Everything else in an entry is identifiers, numbers or test data, where a
#: word list would produce noise rather than signal.
PROSE_KEYS = frozenset(
    {
        "title",
        "description",
        "thesis",
        "purpose",
        "direction_rule",
        "source_reference",
        "notes",
    }
)

#: Discretionary terms. A catalogue entry containing one of these has stated a
#: judgement where it owed a measurement.
#:
#: Deliberately EXCLUDED, because each names something the catalogue has
#: already quantified rather than a judgement left to the reader:
#:   fast, slow       — bounded by the fast_period / slow_period parameters
#:   clear, clears    — used as a verb meaning "exceeds the threshold"
#:   high, low        — technical nouns here (swing high, range low)
#:   extreme          — a noun here (a swing extreme, the bar's extreme);
#:                      the magnitude sense is banned as "extremely"
#:   rather           — occurs only in the construction "rather than"
#:   likely           — a thesis is a probabilistic claim by nature; the
#:                      measurable rule is stated separately and precisely
DISCRETIONARY_TERMS = frozenset(
    {
        # magnitude
        "large", "larger", "largest", "big", "bigger", "biggest", "huge",
        "massive", "sizeable", "sizable", "small", "smaller", "smallest",
        "tiny", "minor", "major", "extremely", "heavy", "heavily",
        "deep", "deeply", "shallow", "tight", "tightly", "loose", "wide",
        "widely", "narrow", "dramatic", "pronounced", "marked", "notable",
        "substantial", "considerable", "significant", "significantly",
        # quality
        "strong", "stronger", "strongest", "strongly", "weak", "weaker",
        "weakest", "good", "better", "best", "bad", "worse", "worst", "nice",
        "clean", "cleanly", "obvious", "clearly", "decisive", "decisively",
        "sharp", "sharply", "quick", "quickly", "rapid", "rapidly",
        "aggressive", "aggressively", "meaningful", "healthy", "solid",
        "decent", "robust", "proper", "reasonable", "appropriate", "adequate",
        "sufficient", "optimal", "ideal",
        # proximity
        "near", "nearby", "far",
        # hedges
        "about", "around", "approximately", "roughly", "somewhat", "fairly",
        "quite", "several", "few", "many", "some", "enough", "various",
        "typically", "usually", "generally", "often", "sometimes", "normally",
        "occasionally",
    }
)

#: Multi-word hedges a single-word list cannot catch.
DISCRETIONARY_PHRASES = (
    "close to",
    "far from",
    "a lot",
    "as needed",
    "if needed",
    "or so",
    "and so on",
)

_WORD_RE = re.compile(r"[a-z]+")


def _scan(text: str) -> list[str]:
    """Discretionary terms found in ``text``, lowercased, in order."""
    lowered = text.lower()
    hits = [word for word in _WORD_RE.findall(lowered) if word in DISCRETIONARY_TERMS]
    hits.extend(phrase for phrase in DISCRETIONARY_PHRASES if phrase in lowered)
    return hits


def _prose(node, path: str = "$"):
    """Yield ``(json_path, text)`` for every prose-bearing string in ``node``."""
    if isinstance(node, dict):
        for key, value in node.items():
            child = "%s.%s" % (path, key)
            if key in PROSE_KEYS and isinstance(value, str):
                yield child, value
            else:
                yield from _prose(value, child)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _prose(item, "%s[%d]" % (path, index))


def test_the_scanner_catches_the_pid_examples():
    """Guard the guard: a broken scanner must not pass the catalogue vacuously.

    Every discretionary phrase PID lines 112-118 names is checked here, so a
    word list that was emptied or a regex that stopped matching fails this
    test before it can silently bless the catalogue.
    """
    assert _scan("a large wick") == ["large"]
    assert _scan("price near resistance") == ["near"]
    assert _scan("a strong trend") == ["strong"]
    assert _scan("a good breakout") == ["good"]
    assert _scan("wait for a big enough move") == ["big", "enough"]
    assert _scan("price is close to the level") == ["close to"]
    assert _scan("LARGE and Strong") == ["large", "strong"]
    # A quantified statement must survive untouched.
    assert _scan("wick_to_range_ratio_min default 0.6, allowed 0.3 to 0.95") == []


def test_prose_walker_finds_nested_text():
    """The walker must reach prose nested in arrays, not only at the top."""
    document = {
        "title": "top",
        "parameters": [{"name": "p", "description": "nested"}],
        "given_hermes_facts": {"description": "still found"},
    }
    found = dict(_prose(document))
    assert found["$.title"] == "top"
    assert found["$.parameters[0].description"] == "nested"


def test_entry_contains_no_discretionary_language(entry, entry_path):
    """A catalogue entry with an unquantified adjective is a defect.

    Scanned prose only — identifiers, numbers and test data are excluded, and
    so are the doctrine documents, which legitimately quote these terms in
    order to prohibit them.
    """
    offences = []
    for path, text in _prose(entry):
        for hit in _scan(text):
            offences.append("%s uses %r in: %s" % (path, hit, text))
    assert not offences, "%s contains discretionary language:\n  %s" % (
        entry_path.name,
        "\n  ".join(offences),
    )


# --- structural conformance --------------------------------------------------


def test_entry_validates_against_the_frozen_schema(entry, entry_path):
    assert validate_document(entry, source=str(entry_path)) == "atomic_strategy"


def test_entry_filename_matches_its_strategy_id(entry, entry_path):
    assert entry["strategy_id"] == entry_path.stem


def test_entry_declares_atomic_doctrine(entry):
    assert all(entry["doctrine_assertions"].values())


def _peer_strategy_ids(entry: dict) -> list[str]:
    """Every ``strategy_id`` in ``entry`` that is not the entry's own.

    The entry's TOP-LEVEL ``strategy_id`` is excluded, and that exclusion is
    the point. This walk used to start at the entry itself, so the first key it
    reached was the entry's own id and the assertion it made there was
    ``own == own`` — an assertion that cannot fail, executed for every entry in
    the catalogue, in a test whose name promises a peer-reference check.
    """
    own = entry["strategy_id"]
    found: list[str] = []

    def walk(node, top: bool) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "strategy_id" and not top and value != own:
                    found.append(value)
                walk(value, False)
        elif isinstance(node, list):
            for item in node:
                walk(item, False)

    walk(entry, True)
    return found


def test_entry_references_no_other_strategy(entry):
    """PID line 59: the only strategy_id in an atomic document is its own.

    The schema forbids a peer-reference property; this checks that no such
    reference smuggled itself in under a key the schema does allow.

    The walk is proved to REACH nested structure before its emptiness is
    concluded from: a walker that silently stopped at the top level would
    return nothing and this test would pass on a catalogue full of peer
    references.
    """
    assert not _peer_strategy_ids(entry)

    planted = copy.deepcopy(entry)
    planted["parameters"][0]["strategy_id"] = "some_other_strategy"
    assert _peer_strategy_ids(planted) == ["some_other_strategy"], (
        "the walk no longer reaches nested structure, so its empty result "
        "above proves nothing"
    )


# --- catalogue-level authoring rules -----------------------------------------


def test_every_hermes_field_declares_a_timeframe(entry):
    """PID line 22: required facts map onto HERMES outputs, on a timeframe.

    The schema leaves ``timeframe`` optional because a package-level
    declaration may span several. A catalogue entry is one strategy on one
    timeframe and must say which.
    """
    for field in entry["required_hermes_fields"]:
        assert "timeframe" in field, "%s declares no timeframe" % field["field"]


def test_numeric_parameter_defaults_lie_within_their_allowed_range(entry):
    """The schema requires a default and a range but cannot compare them."""
    for parameter in entry["parameters"]:
        allowed = parameter.get("allowed_range")
        if allowed is None:
            continue
        default = parameter["default"]
        assert isinstance(default, (int, float)) and not isinstance(default, bool)
        assert allowed["minimum"] <= default <= allowed["maximum"], (
            "%s default %r is outside %r"
            % (parameter["name"], default, allowed)
        )


def test_enumerated_parameter_defaults_are_allowed_values(entry):
    for parameter in entry["parameters"]:
        allowed = parameter.get("allowed_values")
        if allowed is None:
            continue
        assert parameter["default"] in allowed, (
            "%s default %r is not among %r"
            % (parameter["name"], parameter["default"], allowed)
        )


def test_entry_has_both_a_matching_and_a_non_matching_test_case(entry):
    """Determinism is a claim until a case pins it, both ways (PID line 50).

    An entry with only matching cases has not been shown to discriminate.
    """
    outcomes = {
        case["expected_output"].get("matched")
        for case in entry["deterministic_test_cases"]
    }
    assert True in outcomes, "no matching test case"
    assert False in outcomes, "no non-matching test case"


def test_entry_test_case_ids_are_unique(entry):
    ids = [case["case_id"] for case in entry["deterministic_test_cases"]]
    assert len(ids) == len(set(ids))


def test_entry_records_that_thresholds_were_architect_set(entry):
    """Provenance must stop a default being mistaken for a result later."""
    notes = entry["provenance"].get("notes", "")
    assert "architect" in notes.lower(), "provenance does not record who set the defaults"


def test_parameter_names_are_unique_within_an_entry(entry):
    names = [parameter["name"] for parameter in entry["parameters"]]
    assert len(names) == len(set(names))


def test_output_contract_declares_its_reason_field_as_an_output(entry):
    """A chain builds its explanation out of these, so the field must exist."""
    contract = entry["output_contract"]
    names = {field["name"] for field in contract["fields"]}
    assert contract["reason_field"] in names


# --- the catalogue as a whole ------------------------------------------------


def test_catalogue_loads_through_the_public_api():
    catalogue = Catalogue.from_directory(CATALOGUE_DIR)
    assert len(catalogue) == len(ENTRY_PATHS)
    assert catalogue.source == CATALOGUE_DIR


def test_catalogue_identities_are_unique():
    seen = set()
    for path in ENTRY_PATHS:
        document = _load(path)
        key = (document["strategy_id"], document["strategy_version"])
        assert key not in seen, "duplicate identity %r" % (key,)
        seen.add(key)


def test_catalogue_covers_every_atomic_example_named_at_pid_line_55():
    held = {path.stem for path in ENTRY_PATHS}
    missing = {
        concept: strategy_id
        for concept, strategy_id in PID_LINE_55_COVERAGE.items()
        if strategy_id not in held
    }
    assert not missing, "PID line 55 concepts with no catalogue entry: %r" % missing


def test_every_catalogue_entry_is_reachable_by_identity():
    catalogue = Catalogue.from_directory(CATALOGUE_DIR)
    for document in catalogue:
        assert (
            catalogue.get(document["strategy_id"], document["strategy_version"])
            is document
        )
