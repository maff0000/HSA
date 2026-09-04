"""``hsa cer`` against the inventory's own ``evidence.json`` containers.

The inventory layout is ``strategies/<id>/<version>/evidence.json`` and that
file is a CONTAINER: an inventory-local index with no ``$hsa_kind``, holding
an array of full ``cer_reference`` documents. ``hsa cer validate`` used to
accept exactly one reference per file, so pointing the shipped command at the
shipped layout failed with schema errors about a contract the container was
never meant to satisfy.

These tests hold the fix in place. The load-bearing one is
``test_the_shipped_command_validates_the_shipped_inventory_layout``: it runs
the real CLI action over the real inventory files, which is the thing that
did not work.

Two properties are asserted beyond "it parses":

* the two shapes are told apart by the ``$hsa_kind`` discriminator, never by
  filename — the two governed packages happen to use different container
  envelopes, and both are read correctly;
* a failure inside a container names WHICH reference and WHICH field. A
  container with one bad entry that reports only the filename leaves the
  reader to find the entry by hand.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest

from hsa.cer import (
    EVIDENCE_CONTAINER_ARRAY,
    KIND,
    OPAQUE_IDENTITY_FIELDS,
    SOURCE_CONTRACT_FIXTURE,
    EvidenceDocumentShapeError,
    FixtureEvidenceReader,
    is_evidence_container,
    is_fixture,
    locate_reference,
    read_reference_documents,
    split_evidence_document,
    validate_reference_file,
)
from hsa.commands import cer as cer_command
from hsa.contracts import DISCRIMINATOR, read_json_file
from hsa.errors import DocumentInvalidError

REPO = Path(__file__).resolve().parent.parent
STRATEGIES = REPO / "strategies"
FIXTURE_PREFIX = "FIXTURE-"


def _inventory_evidence_files() -> list[Path]:
    return sorted(STRATEGIES.glob("*/*/evidence.json"))


def _parse(argv):
    parser = argparse.ArgumentParser(prog="hsa cer")
    cer_command.add_arguments(parser)
    return parser.parse_args(argv)


def _digest(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


# --------------------------------------------------------------------------
# the shipped command reads the shipped layout
# --------------------------------------------------------------------------


def test_the_inventory_actually_ships_evidence_containers():
    """If this fails the layout moved and the rest of this file is stale."""
    files = _inventory_evidence_files()
    assert files, "strategies/<id>/<version>/evidence.json is the inventory layout"
    for path in files:
        assert is_evidence_container(read_json_file(path)), path


@pytest.mark.parametrize(
    "path", _inventory_evidence_files(), ids=lambda path: path.parent.parent.name
)
def test_the_shipped_command_validates_the_shipped_inventory_layout(capsys, path):
    """`hsa cer validate strategies/<id>/<version>/evidence.json`, end to end.

    This is the finding: the layout the inventory uses and the command the
    project ships could not be used together.
    """
    assert cer_command.run(_parse(["validate", str(path)])) == 0
    out = capsys.readouterr().out
    assert "valid evidence container" in out
    assert "$.%s[0]: valid cer_reference" % EVIDENCE_CONTAINER_ARRAY in out


@pytest.mark.parametrize(
    "path", _inventory_evidence_files(), ids=lambda path: path.parent.parent.name
)
def test_every_reference_in_the_inventory_is_a_valid_labelled_fixture(path):
    found = validate_reference_file(path)
    assert found, "%s holds no references" % path
    for json_path, reference in found:
        assert reference[DISCRIMINATOR] == KIND, json_path
        assert reference["source"] == SOURCE_CONTRACT_FIXTURE, json_path
        assert is_fixture(reference), json_path
        present = [field for field in OPAQUE_IDENTITY_FIELDS if field in reference]
        assert present, "%s %s names no CER identity" % (path, json_path)
        for field in present:
            assert reference[field].startswith(FIXTURE_PREFIX), (
                "%s %s: %s = %r should be prefixed %s"
                % (path, json_path, field, reference[field], FIXTURE_PREFIX)
            )


@pytest.mark.parametrize(
    "path", _inventory_evidence_files(), ids=lambda path: path.parent.parent.name
)
def test_container_references_are_anchored_to_the_directory_they_live_in(path):
    """A package filed under a path that contradicts its own identity is
    unfindable by the identity CER records evidence against."""
    strategy_version = path.parent.name
    strategy_id = path.parent.parent.name
    for json_path, reference in read_reference_documents(path):
        assert reference["strategy_id"] == strategy_id, json_path
        assert reference["strategy_version"] == strategy_version, json_path


# --------------------------------------------------------------------------
# the two shapes, told apart by the discriminator and not by filename
# --------------------------------------------------------------------------


def test_a_single_reference_is_not_a_container():
    document = {
        DISCRIMINATOR: KIND,
        "strategy_id": "gold_context_breakout",
        "strategy_version": "1.0.0",
        "evidence_id": "FIXTURE-EVID-SHAPE-0001",
        "reference_type": "RESEARCH_FINDING",
        "source": SOURCE_CONTRACT_FIXTURE,
        "recorded_at_utc": "2026-09-04T00:00:00Z",
    }
    assert not is_evidence_container(document)
    assert split_evidence_document(document) == [("$", document)]


def test_the_shape_is_decided_by_the_discriminator_not_the_filename(tmp_path):
    """A file called evidence.json holding one reference is one reference."""
    document = {
        DISCRIMINATOR: KIND,
        "strategy_id": "gold_context_breakout",
        "strategy_version": "1.0.0",
        "evidence_id": "FIXTURE-EVID-SHAPE-0002",
        "reference_type": "RESEARCH_FINDING",
        "source": SOURCE_CONTRACT_FIXTURE,
        "recorded_at_utc": "2026-09-04T00:00:00Z",
    }
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert read_reference_documents(path) == [("$", document)]


def test_the_two_governed_packages_use_different_envelopes(tmp_path):
    """Detection must not depend on the container's own metadata keys.

    ``gold_context_breakout`` declares ``document_type`` and
    ``wick_rejection_sequence`` declares ``$hsa_evidence``. Both are read,
    because what identifies a container is the ABSENCE of ``$hsa_kind`` plus
    the presence of the references array — not any envelope field.
    """
    envelopes = [
        set(read_json_file(path)) - {EVIDENCE_CONTAINER_ARRAY}
        for path in _inventory_evidence_files()
    ]
    assert len(envelopes) >= 2
    assert envelopes[0] != envelopes[1], "these two happen to differ; that is the point"

    bare = {EVIDENCE_CONTAINER_ARRAY: []}
    assert is_evidence_container(bare)


def test_split_reports_the_json_path_of_every_reference():
    container = {
        EVIDENCE_CONTAINER_ARRAY: [
            {DISCRIMINATOR: KIND, "n": 0},
            {DISCRIMINATOR: KIND, "n": 1},
            {DISCRIMINATOR: KIND, "n": 2},
        ]
    }
    found = split_evidence_document(container)
    assert [json_path for json_path, _ in found] == [
        "$.references[0]",
        "$.references[1]",
        "$.references[2]",
    ]
    assert [reference["n"] for _, reference in found] == [0, 1, 2]


def test_locate_reference_names_file_and_entry():
    assert locate_reference("evidence.json", "$") == "evidence.json"
    assert (
        locate_reference("evidence.json", "$.references[2]")
        == "evidence.json $.references[2]"
    )


# --------------------------------------------------------------------------
# a failure names which reference and which field
# --------------------------------------------------------------------------


def test_an_invalid_reference_in_a_container_names_the_entry_and_the_field(tmp_path):
    source = read_json_file(_inventory_evidence_files()[0])
    source[EVIDENCE_CONTAINER_ARRAY][2]["reference_type"] = "NOT_A_REFERENCE_TYPE"
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(source, indent=2), encoding="utf-8")

    with pytest.raises(DocumentInvalidError) as raised:
        validate_reference_file(path)

    rendered = str(raised.value)
    assert "$.references[2]" in rendered, "the failure must name WHICH reference"
    assert "reference_type" in rendered, "the failure must name WHICH field"
    assert "NOT_A_REFERENCE_TYPE" in rendered
    assert raised.value.json_path == "$.reference_type"


def test_the_cli_exits_non_zero_on_an_invalid_container(tmp_path):
    source = read_json_file(_inventory_evidence_files()[0])
    del source[EVIDENCE_CONTAINER_ARRAY][1]["recorded_at_utc"]
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(source, indent=2), encoding="utf-8")

    with pytest.raises(DocumentInvalidError) as raised:
        cer_command.run(_parse(["validate", str(path)]))
    assert "$.references[1]" in str(raised.value)


def test_a_non_object_entry_is_refused_by_its_index():
    container = {EVIDENCE_CONTAINER_ARRAY: [{DISCRIMINATOR: KIND}, "not a document"]}
    with pytest.raises(EvidenceDocumentShapeError, match=r"\$\.references\[1\]"):
        split_evidence_document(container, source="evidence.json")


def test_an_unrecognised_document_is_refused_rather_than_guessed_at():
    with pytest.raises(EvidenceDocumentShapeError) as raised:
        split_evidence_document({"nothing": "familiar"}, source="mystery.json")
    rendered = str(raised.value)
    assert "mystery.json" in rendered
    assert DISCRIMINATOR in rendered, "the message names the discriminator"
    assert EVIDENCE_CONTAINER_ARRAY in rendered, "and the container's array"


def test_a_json_list_is_not_a_reference_document():
    with pytest.raises(EvidenceDocumentShapeError):
        split_evidence_document([{DISCRIMINATOR: KIND}])


def test_an_empty_container_is_reported_as_empty_not_silently_passed(capsys, tmp_path):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps({EVIDENCE_CONTAINER_ARRAY: []}), encoding="utf-8")
    assert cer_command.run(_parse(["validate", str(path)])) == 0
    assert "valid evidence container, 0 references" in capsys.readouterr().out


# --------------------------------------------------------------------------
# the reader reads containers too, and still writes nothing
# --------------------------------------------------------------------------


def test_the_evidence_reader_reads_a_container_directory(tmp_path):
    container = read_json_file(STRATEGIES / "gold_context_breakout/1.0.0/evidence.json")
    (tmp_path / "evidence.json").write_text(json.dumps(container), encoding="utf-8")

    reader = FixtureEvidenceReader(tmp_path)
    references = reader.references()
    assert len(references) == len(container[EVIDENCE_CONTAINER_ARRAY])
    assert reader.references_for("gold_context_breakout", "1.0.0") == references
    assert reader.references_for("gold_context_breakout", "9.9.9") == []

    locations = [location for location, _ in reader.items()]
    assert locations[0].endswith("evidence.json $.references[0]"), locations[0]


def test_reading_a_container_writes_nothing(tmp_path, monkeypatch):
    """PID lines 181 and 269: reading evidence must not become storing it."""
    before = {path: _digest(path) for path in [STRATEGIES]}
    monkeypatch.chdir(tmp_path)

    for path in _inventory_evidence_files():
        validate_reference_file(path)
        read_reference_documents(path)

    assert {path: _digest(path) for path in [STRATEGIES]} == before
    assert list(tmp_path.iterdir()) == [], "reading created files of its own"
