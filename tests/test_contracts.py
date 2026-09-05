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


# --- a citation in a frozen contract is a claim about PID.md -----------------

#: What each ``strategy_package`` property IS, in the PID's own words, stated
#: here independently of the schema. The schema says which PID line it cites;
#: ``PID.md`` decides whether that line says this. The same off-by-one that
#: reached product output through ``not_yet_specified`` had also reached the
#: frozen schema descriptions — chain, timing, persistence, expiry and state
#: semantics each cited the bullet above the one they meant, and ``thesis``
#: cited "instrument(s)".
# --- PID citations must point at what they claim ------------------------------
#
# A frozen contract's descriptions are read as authority, and so are a test's
# docstrings: they are what a reader consults instead of counting lines in
# PID.md. The first version of this guard checked ONE file, only the properties
# in the table below, and only their FIRST citation — and eleven wrong
# citations survived it in schemas, packages and tests, including three in the
# very file it was watching. A guard scoped to a subset does not report on the
# rest; it reports nothing about the rest, which reads the same.
#
# So it is widened three ways, and the widening is structural rather than a
# longer list of files somebody remembered:
#
#   1. every contract schema, every property and $def, EVERY citation — with a
#      coverage check that fails when a new citation appears with no
#      expectation, so a description added tomorrow cannot slip past the way
#      these did;
#   2. repository-wide, a citation whose own words name a numbered acceptance
#      criterion must cite that criterion's line;
#   3. repository-wide, a citation whose own words restate a PID doctrine
#      bullet must cite that bullet's line.
#
# (2) and (3) need no table at all: they read the claim out of the citing text
# and the line number out of PID.md, so they cover files nobody has thought
# about yet, which is where the surviving errors were.

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: A citation, in BOTH forms the repository uses. The prose form, "PID line
#: 138", is what the schemas and Python docstrings use; the path form,
#: ``PID.md:138``, is what the boot documents use, and there are two hundred of
#: them. Checking only the first form would have left the larger half of the
#: repository unchecked — the same mistake, one layer up, as checking only the
#: first citation in one file.
_CITATION = re.compile(
    r"(?:PID lines?\s+|PID\.md:)"
    r"(\d+(?:\s*-\s*\d+)?(?:\s*,\s*(?:and\s+)?\d+(?:\s*-\s*\d+)?)*)"
)


def _pid_lines() -> list[str]:
    return (REPO_ROOT / "PID.md").read_text(encoding="utf-8").splitlines()


def _cited_numbers(raw: str) -> set[int]:
    """Every line number one citation names, ranges expanded."""
    numbers: set[int] = set()
    for part in raw.split(","):
        part = part.replace("and", "").strip()
        if "-" in part:
            first, last = part.split("-")
            numbers.update(range(int(first), int(last) + 1))
        elif part:
            numbers.add(int(part))
    return numbers


def _cited_items(raw: str) -> set[int]:
    """Only the line numbers written out singly.

    A RANGE names a passage — "PID lines 110-120" is the ambiguity section, and
    that it happens to contain a bulleted list of example phrases does not make
    it a citation of any one of them. A standalone number is a claim about one
    line, and that is the claim worth checking.
    """
    numbers: set[int] = set()
    for part in raw.split(","):
        part = part.replace("and", "").strip()
        if part and "-" not in part:
            numbers.add(int(part))
    return numbers


def _list_runs(pid: list[str]) -> list[tuple[int, int]]:
    """The line spans of PID.md's enumerated lists.

    Every wrong citation found so far points INTO one of these: the PID states
    its requirements as bullets and numbered criteria, and an off-by-one inside
    a list lands on a neighbouring requirement that reads plausibly. Outside a
    list a citation names a paragraph, where being one line out is visible.
    """
    runs: list[tuple[int, int]] = []
    current: list[int] = []
    for number, line in enumerate(pid, start=1):
        if re.match(r"^(?:\*|\d+\.)\s+\S", line):
            current.append(number)
        elif current:
            runs.append((current[0], current[-1]))
            current = []
    if current:
        runs.append((current[0], current[-1]))
    return runs


def _run_containing(runs, number):
    for run in runs:
        if run[0] <= number <= run[1]:
            return run
    return None


def _item_line(pid: list[str], item: str) -> int:
    """The line of the PID list item whose text is exactly ``item``.

    Resolved from PID.md rather than written down, so the tables below survive
    the PID being re-paragraphed, and fail loudly rather than silently if an
    item they name is ever reworded away.
    """
    found = [
        number
        for number, line in enumerate(pid, start=1)
        if (match := re.match(r"^(?:\*|\d+\.)\s+(.+?)[;.]?\s*$", line))
        and match.group(1).strip().lower() == item.lower()
    ]
    assert len(found) == 1, "PID.md has %d list items reading %r" % (len(found), item)
    return found[0]


def _repository_files():
    """Every file that can carry a citation, in a fixed order."""
    for base, directories, files in os.walk(REPO_ROOT):
        directories[:] = sorted(
            d for d in directories if d not in (".git", "__pycache__", ".pytest_cache")
        )
        for name in sorted(files):
            if not name.endswith((".py", ".json", ".md", ".txt")):
                continue
            path = Path(base) / name
            if path.name == "PID.md" and path.parent == REPO_ROOT:
                continue
            yield path


def _citation_segments(line: str):
    """Each citation on ``line`` with the words that belong to it.

    A description often cites several lines for several reasons in one
    sentence. Attributing the whole line to every citation would make one
    correct citation excuse a wrong one beside it — which is the bug this is
    looking for — so each citation gets the text between its neighbours.
    """
    citations = list(_CITATION.finditer(line))
    for index, citation in enumerate(citations):
        start = citations[index - 1].end() if index else 0
        end = citations[index + 1].start() if index + 1 < len(citations) else len(line)
        before = line[start : citation.start()]
        after = line[citation.end() : end]
        yield citation, (before + " " + after).lower()


# --- (1) the contract schemas -------------------------------------------------

#: What each schema property means, in the PID's own words. A citation into one
#: of PID.md's enumerated lists from this property's description must land on a
#: line saying this. Keyed by (schema file, property name).
#: What each schema property is entitled to claim, in the PID's own words. A
#: standalone line citation from this property's description, landing inside
#: one of PID.md's enumerated lists, must be a line saying one of these.
#:
#: A property may legitimately cite two different bullets for two different
#: claims — ``strategy_package.atomic_strategies`` cites the required-output
#: bullet for what it holds and the atomic-doctrine bullet for what each entry
#: must be — so this is a SET, and it therefore cannot catch two of a
#: property's own citations being swapped with each other. It catches a
#: citation landing on a line the property never claims, which is what all
#: eleven surviving errors were. The doctrine check below is per-citation and
#: does catch swaps within the atomic-doctrine list.
SCHEMA_PROPERTY_MEANS = {
    ("strategy_package.schema.json", "thesis"): ("economic/trading thesis",),
    ("strategy_package.schema.json", "intended_horizon"): (
        "intended horizon/style",
        "do not force a strategy to trade outside its preferred market shape",
    ),
    ("strategy_package.schema.json", "required_hermes_fields"): (
        "required HERMES fields",
    ),
    ("strategy_package.schema.json", "atomic_strategies"): (
        "atomic strategy definitions",
        "independently testable",
    ),
    ("strategy_package.schema.json", "timeframe_roles"): ("semantic timeframe roles",),
    ("strategy_package.schema.json", "chain"): ("chain definition",),
    ("strategy_package.schema.json", "timing"): ("timing/persistence/expiry",),
    ("strategy_package.schema.json", "persistence"): ("timing/persistence/expiry",),
    ("strategy_package.schema.json", "expiry"): ("timing/persistence/expiry",),
    ("strategy_package.schema.json", "state_semantics"): ("state semantics",),
    ("strategy_package.schema.json", "invalidation_conditions"): (
        "invalidation/validity conditions",
    ),
    ("strategy_package.schema.json", "validity_conditions"): (
        "invalidation/validity conditions",
        "dormancy is not failure",
    ),
    ("strategy_package.schema.json", "parameters"): (
        "parameter definitions and allowed ranges",
    ),
    ("strategy_package.schema.json", "output_contract"): ("expected output contract",),
    ("strategy_package.schema.json", "deterministic_test_cases"): (
        "deterministic test cases",
    ),
    ("strategy_package.schema.json", "evidence_requirements"): (
        "backtest/evidence requirements",
    ),
    ("strategy_package.schema.json", "acceptance_criteria"): (
        "acceptance/rejection criteria",
    ),
    ("strategy_package.schema.json", "rejection_criteria"): (
        "acceptance/rejection criteria",
    ),
    ("strategy_package.schema.json", "provenance"): (
        "provenance to original strategy source",
    ),
    ("strategy_package.schema.json", "cer_references"): (
        "CER identity/evidence references",
    ),
    ("strategy_package.schema.json", "lifecycle"): (
        "produce a separately versioned candidate rather than mutate an "
        "existing promoted strategy",
    ),
    ("chain.schema.json", "state_semantics"): ("state", "state semantics"),
    ("chain.schema.json", "timing"): ("timing/sequence", "timing/persistence/expiry"),
    ("chain.schema.json", "persistence"): (
        "persistence",
        "timing/persistence/expiry",
    ),
    ("chain.schema.json", "expiry"): ("expiry", "timing/persistence/expiry"),
    ("chain.schema.json", "explanation_contract"): (
        "explicit reason for match/non-match",
    ),
    ("chain.schema.json", "composition_assertions"): (
        "component strategy identity/version",
    ),
    ("common.defs.json", "direction_semantics"): ("direction", "direction semantics"),
    ("common.defs.json", "provenance"): ("provenance to original strategy source",),
    ("common.defs.json", "parameter"): ("parameter definitions and allowed ranges",),
    ("common.defs.json", "output_contract"): ("expected output contract",),
    ("common.defs.json", "utc_timestamp"): ("UTC everywhere",),
    ("common.defs.json", "hermes_field"): (
        "required HERMES fields",
        "mechanically driven by HERMES facts",
        "map required facts to HERMES outputs",
        "identify measurable market facts",
    ),
    ("atomic_strategy.schema.json", "thesis"): ("economic/trading thesis",),
    ("atomic_strategy.schema.json", "instruments"): (
        "do not force a strategy to trade outside its preferred market shape",
    ),
    ("atomic_strategy.schema.json", "required_hermes_fields"): (
        "mechanically driven by HERMES facts",
    ),
    ("atomic_strategy.schema.json", "parameters"): (
        "parameter definitions and allowed ranges",
    ),
    ("cer_reference.schema.json", "supports"): (
        "evidence references supporting promotion",
    ),
}


def _schema_nodes():
    """Every named property and $def in every contract schema."""
    for path in sorted(contracts_dir().glob("*.json")):
        schema = read_json_file(path)
        for group in ("properties", "$defs"):
            for name, node in (schema.get(group) or {}).items():
                if isinstance(node, dict):
                    yield path.name, name, node.get("description", "") or ""


def test_every_pid_citation_in_every_contract_schema_points_at_what_it_claims():
    """A frozen contract's descriptions are read as authority. They must hold.

    Every schema, every property and $def, and EVERY citation — not the first.
    ``chain.timing`` cited "PID lines 75, 136": line 75 is *timing/sequence*
    and correct, line 136 is *direction semantics* and was not, and checking
    only the first citation is exactly why the second one survived.
    """
    pid = _pid_lines()
    runs = _list_runs(pid)
    unexpected = []
    wrong = []
    for filename, name, description in _schema_nodes():
        cited = set()
        for citation in _CITATION.finditer(description):
            cited |= _cited_items(citation.group(1))
        into_lists = sorted(number for number in cited if _run_containing(runs, number))
        if not into_lists:
            continue
        key = (filename, name)
        if key not in SCHEMA_PROPERTY_MEANS:
            unexpected.append(key)
            continue
        expected = SCHEMA_PROPERTY_MEANS[key]
        for number in into_lists:
            line = pid[number - 1].lower()
            if not any(phrase.lower() in line for phrase in expected):
                wrong.append(
                    "%s.%s cites PID line %d, which says %r; it claims %s"
                    % (
                        filename,
                        name,
                        number,
                        pid[number - 1].strip(),
                        " or ".join(repr(phrase) for phrase in expected),
                    )
                )
    assert not wrong, "\n".join(wrong)
    assert not unexpected, (
        "these schema descriptions cite a PID list line and have no expectation "
        "here, so nothing is checking them: %s"
        % ", ".join("%s.%s" % key for key in sorted(unexpected))
    )


# --- (2) a named acceptance criterion cites its own line ----------------------


def test_a_citation_that_names_an_acceptance_criterion_cites_its_line():
    """Repository-wide, and it needs no table: the claim is in the text.

    ``test_criterion_11_the_package_has_end_to_end_deterministic_cases`` cited
    PID line 261, which is criterion 12. Nothing was watching test docstrings,
    so it read as authority and was wrong.
    """
    pid = _pid_lines()
    runs = _list_runs(pid)
    criteria = {}
    for number, line in enumerate(pid, start=1):
        match = re.match(r"^(\d+)\.\s+\S", line)
        if match and _run_containing(runs, number) == _run_containing(
            runs, _item_line(pid, "identify ambiguity rather than guessing")
        ):
            criteria[int(match.group(1))] = number
    assert len(criteria) >= 13, "the acceptance criteria list was not found"
    lowest, highest = min(criteria.values()), max(criteria.values())

    named = re.compile(r"criterion[_ ](\d+)", re.I)
    wrong = []
    for path in _repository_files():
        enclosing = None
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            if line.lstrip().startswith("def "):
                match = named.search(line)
                enclosing = int(match.group(1)) if match else None
            for citation, segment in _citation_segments(line):
                cited = _cited_numbers(citation.group(1))
                if not any(lowest <= number_ <= highest for number_ in cited):
                    continue
                inline = named.search(segment)
                claimed = int(inline.group(1)) if inline else enclosing
                if claimed is None or claimed not in criteria:
                    continue
                if criteria[claimed] not in cited:
                    wrong.append(
                        "%s:%d names criterion %d (PID line %d) but cites %s"
                        % (
                            path.relative_to(REPO_ROOT),
                            number,
                            claimed,
                            criteria[claimed],
                            sorted(cited),
                        )
                    )
    assert not wrong, "\n".join(wrong)


# --- (3) a citation that restates a doctrine bullet cites its line ------------

#: How the repository words each atomic-strategy and portfolio doctrine bullet,
#: mapped to the PID's own wording. The LINE numbers are resolved from PID.md,
#: so this table states only the synonym, never a line.
DOCTRINE_RESTATEMENTS = {
    r"independently testable": "independently testable",
    r"self[-\s]contained": "self-contained",
    r"determin(?:istic|ism)": "deterministic",
    r"execution[-\s]blind": "execution-blind",
    r"unaware of other strategies": "unaware of other strategies",
    r"mechanically driven by hermes": "mechanically driven by HERMES facts",
    r"tuned? (?:merely )?to restore trade frequency": (
        "do not tune merely to restore trade frequency"
    ),
    r"dormancy is not failure": "dormancy is not failure",
    r"overfitting": "avoid overfitting",
}


def test_a_citation_that_restates_a_pid_doctrine_bullet_cites_its_line():
    """The other half, also table-free where it counts.

    A schema description saying "determinism" while citing the *independently
    testable* bullet, and a test docstring saying "independently testable"
    while citing the *small* bullet. Both read as authority, both sat in files
    the old guard did not open, and both are caught by asking the one question
    that needs no per-site expectation: the text names a doctrine bullet, so
    does the line it cites?

    Note this check is run over its own file too, which is why the examples
    above are described rather than quoted — a quoted wrong citation here would
    be a wrong citation here.
    """
    pid = _pid_lines()
    runs = _list_runs(pid)
    targets = {
        pattern: _item_line(pid, item)
        for pattern, item in DOCTRINE_RESTATEMENTS.items()
    }
    wrong = []
    for path in _repository_files():
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            for citation, segment in _citation_segments(line):
                cited = _cited_numbers(citation.group(1))
                for pattern, target in targets.items():
                    if not re.search(pattern, segment):
                        continue
                    if target in cited:
                        continue
                    # Only a citation into the SAME list is claiming to be this
                    # bullet. One pointing elsewhere is citing something else.
                    run = _run_containing(runs, target)
                    if any(_run_containing(runs, number_) == run for number_ in cited):
                        wrong.append(
                            "%s:%d restates %r (PID line %d) but cites %s"
                            % (
                                path.relative_to(REPO_ROOT),
                                number,
                                DOCTRINE_RESTATEMENTS[pattern],
                                target,
                                sorted(cited),
                            )
                        )
    assert not wrong, "\n".join(wrong)


def test_the_widened_citation_guard_would_catch_the_errors_it_was_widened_for():
    """Non-vacuity: the checks are run against the wrong citations themselves.

    Every one of these was live in the repository and passed the narrow guard.
    If a check stops seeing its own case, it has stopped working.
    """
    pid = _pid_lines()
    runs = _list_runs(pid)

    # (1) a second citation, in a file the old guard never opened.
    assert "direction semantics" in pid[136 - 1].lower()
    assert "timing/persistence/expiry" in pid[137 - 1].lower()

    # (3) the doctrine bullets that were mis-cited.
    assert _item_line(pid, "independently testable") == 49
    assert _item_line(pid, "deterministic") == 50
    assert _item_line(pid, "small") == 47
    assert _run_containing(runs, 47) == _run_containing(runs, 49)

    # A restatement citing the neighbouring bullet is detected. Assembled
    # rather than written out, so this file does not itself contain the wrong
    # citation it is demonstrating.
    line = "determinism is a claim until pinned (PID line %d)" % 49
    detected = False
    for _citation, segment in _citation_segments(line):
        detected |= bool(re.search(r"determin(?:istic|ism)", segment))
    assert detected, "the segment split stopped seeing the claim beside a citation"
