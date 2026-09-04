"""The CER adapter and its contract fixtures (PID lines 160-181).

Two things are under test. First, that every fixture is a valid
``cer_reference`` and is unmistakably labelled ``CONTRACT_FIXTURE``, because
a fixture mistaken for live evidence is the whole failure mode PID line 181
guards against. Second, that the adapter persists nothing — PID line 269
makes a CER datastore an explicit non-goal, so "it reads and validates, and
that is all" is asserted rather than assumed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest

from hsa.cer import (
    IDENTITY_FIELDS,
    KIND,
    OPAQUE_IDENTITY_FIELDS,
    SOURCE_CER_LIVE,
    SOURCE_CONTRACT_FIXTURE,
    SOURCES,
    SUPPORTS,
    CerError,
    EvidenceNotFoundError,
    EvidenceReader,
    FixtureEvidenceReader,
    FixtureUnavailableError,
    build_reference,
    fixtures_dir,
    group_by_reference_type,
    is_fixture,
    open_evidence_reader,
    reference_types,
    validate_reference,
)
from hsa.commands import cer as cer_command
from hsa.contracts import read_json_file, validate_document
from hsa.errors import DocumentInvalidError, HSAError

FIXTURE_PREFIX = "FIXTURE-"


@pytest.fixture
def fixture_paths() -> list[Path]:
    return sorted(fixtures_dir().glob("*.json"))


@pytest.fixture
def fixture_docs(fixture_paths) -> list[dict]:
    return [read_json_file(path) for path in fixture_paths]


@pytest.fixture
def reader() -> EvidenceReader:
    return open_evidence_reader()


def _parse(argv):
    parser = argparse.ArgumentParser(prog="hsa cer")
    cer_command.add_arguments(parser)
    return parser.parse_args(argv)


# --------------------------------------------------------------------------
# the fixture set is the contract proof standing in for a live CER
# --------------------------------------------------------------------------


def test_fixture_directory_is_populated(fixture_paths):
    assert fixture_paths, "the CER fixture set is the stand-in for a live CER"


def test_every_fixture_validates_against_the_frozen_schema(fixture_paths):
    for path in fixture_paths:
        document = read_json_file(path)
        assert validate_document(document, kind=KIND, source=str(path)) == KIND


def test_every_fixture_declares_itself_a_contract_fixture(fixture_docs):
    """PID line 181: the distinction is declared, never inferred."""
    for document in fixture_docs:
        assert document["source"] == SOURCE_CONTRACT_FIXTURE
        assert is_fixture(document)


def test_no_fixture_claims_to_be_live_evidence(fixture_docs):
    assert not any(
        document["source"] == SOURCE_CER_LIVE for document in fixture_docs
    )


def test_fixture_identities_are_unmistakably_fixture_identities(fixture_docs):
    """Even read out of context, a fixture identity cannot pass for a real one."""
    for document in fixture_docs:
        present = [
            field for field in OPAQUE_IDENTITY_FIELDS if field in document
        ]
        assert present, "a reference must name at least one CER identity"
        for field in present:
            assert document[field].startswith(FIXTURE_PREFIX), (
                "%s = %r should be prefixed %s" % (field, document[field], FIXTURE_PREFIX)
            )


def test_fixtures_cover_every_canonical_reference_type(fixture_docs):
    """PID lines 175-179: source analysis, hypotheses, lineage, findings,
    and evidence supporting promotion / revision / rejection."""
    covered = {document["reference_type"] for document in fixture_docs}
    assert covered == set(reference_types())


def test_fixtures_cover_every_supported_decision(fixture_docs):
    covered = {document["supports"] for document in fixture_docs}
    assert covered == set(SUPPORTS)


def test_fixtures_cover_a_run_that_produced_evidence(fixture_docs):
    with_run = [document for document in fixture_docs if "run_id" in document]
    assert with_run
    assert any("evidence_id" in document for document in with_run)


def test_fixtures_cover_version_lineage_across_two_versions(fixture_docs):
    lineage_refs = [
        document
        for document in fixture_docs
        if document["reference_type"] == "VERSION_LINEAGE"
    ]
    versions = {document["strategy_version"] for document in lineage_refs}
    assert len(versions) >= 2, "lineage needs at least two versions to be lineage"


def test_every_fixture_timestamp_is_utc(fixture_docs):
    """UTC everywhere (PID line 225)."""
    for document in fixture_docs:
        assert document["recorded_at_utc"].endswith("Z")


def test_fixtures_are_anchored_to_a_strategy_and_a_version(fixture_docs):
    """Identity is always id plus version (PID lines 166-167)."""
    for document in fixture_docs:
        assert document["strategy_id"]
        assert document["strategy_version"]


def test_fixtures_are_readable_json_with_no_surprises(fixture_paths):
    for path in fixture_paths:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert parsed["$hsa_kind"] == KIND


# --------------------------------------------------------------------------
# build_reference
# --------------------------------------------------------------------------


def test_build_reference_produces_a_valid_document():
    document = build_reference(
        "gold_context_breakout",
        "1.0.0",
        "RESEARCH_FINDING",
        SOURCE_CONTRACT_FIXTURE,
        "2026-09-04T00:00:00Z",
        run_id="FIXTURE-RUN-GOLD-0003",
        summary="A finding.",
        supports="INFORMATIONAL",
    )
    assert validate_document(document) == KIND
    assert document["$hsa_kind"] == KIND
    assert "evidence_id" not in document, "unset identities are omitted, not null"


def test_build_reference_refuses_a_reference_naming_no_evidence():
    """A document that names a strategy but no evidence is not a reference."""
    with pytest.raises(DocumentInvalidError) as caught:
        build_reference(
            "gold_context_breakout",
            "1.0.0",
            "SOURCE_ANALYSIS",
            SOURCE_CONTRACT_FIXTURE,
            "2026-09-04T00:00:00Z",
        )
    assert "at least one of" in str(caught.value)


def test_build_reference_refuses_an_undeclared_source():
    """There is no third state between CER_LIVE and CONTRACT_FIXTURE."""
    with pytest.raises(DocumentInvalidError):
        build_reference(
            "gold_context_breakout",
            "1.0.0",
            "SOURCE_ANALYSIS",
            "PROBABLY_REAL",
            "2026-09-04T00:00:00Z",
            evidence_id="FIXTURE-EVID-X",
        )


def test_build_reference_refuses_a_non_utc_timestamp():
    with pytest.raises(DocumentInvalidError):
        build_reference(
            "gold_context_breakout",
            "1.0.0",
            "SOURCE_ANALYSIS",
            SOURCE_CONTRACT_FIXTURE,
            "2026-09-04T00:00:00+01:00",
            evidence_id="FIXTURE-EVID-X",
        )


def test_build_reference_refuses_an_unknown_reference_type():
    with pytest.raises(DocumentInvalidError):
        build_reference(
            "gold_context_breakout",
            "1.0.0",
            "VIBES",
            SOURCE_CONTRACT_FIXTURE,
            "2026-09-04T00:00:00Z",
            evidence_id="FIXTURE-EVID-X",
        )


def test_validate_reference_accepts_the_w1_fixture(valid_doc):
    assert validate_reference(valid_doc("cer_reference"))["$hsa_kind"] == KIND


def test_validate_reference_rejects_the_w1_invalid_fixture(invalid_doc):
    with pytest.raises(DocumentInvalidError):
        validate_reference(invalid_doc("cer_reference"))


def test_reference_types_come_from_the_frozen_contract():
    """Restating the enum in Python would let the adapter drift from it."""
    defs = read_json_file(fixtures_dir().parent.parent / "common.defs.json")
    assert list(reference_types()) == defs["$defs"]["cer_reference_type"]["enum"]


def test_the_canonical_identity_set_is_the_pid_set():
    """PID lines 166-171."""
    assert IDENTITY_FIELDS == (
        "strategy_id",
        "strategy_version",
        "experiment_id",
        "run_id",
        "evidence_id",
        "artifact_id",
    )
    assert set(OPAQUE_IDENTITY_FIELDS).issubset(set(IDENTITY_FIELDS))
    assert "strategy_id" not in OPAQUE_IDENTITY_FIELDS


def test_there_are_exactly_two_sources():
    assert SOURCES == (SOURCE_CER_LIVE, SOURCE_CONTRACT_FIXTURE)


# --------------------------------------------------------------------------
# the seam
# --------------------------------------------------------------------------


def test_open_evidence_reader_returns_an_evidence_reader(reader):
    assert isinstance(reader, EvidenceReader)
    assert isinstance(reader, FixtureEvidenceReader)
    assert reader.source == SOURCE_CONTRACT_FIXTURE


def test_the_seam_declares_the_interface_a_live_client_must_implement():
    """Three read methods, no writes."""
    for method in ("references", "references_for", "reference"):
        assert callable(getattr(EvidenceReader, method))
    with pytest.raises(NotImplementedError):
        EvidenceReader().references()


def test_reader_resolves_references_for_a_strategy(reader):
    found = reader.references_for("gold_context_breakout")
    assert found
    assert all(
        document["strategy_id"] == "gold_context_breakout" for document in found
    )


def test_reader_resolves_references_for_one_version(reader):
    found = reader.references_for("gold_context_breakout", "1.1.0")
    assert found
    assert {document["strategy_version"] for document in found} == {"1.1.0"}


def test_reader_resolves_one_reference_by_evidence_id(reader):
    document = reader.reference("FIXTURE-EVID-GOLD-0001-PROMO")
    assert document["reference_type"] == "PROMOTION_EVIDENCE"
    assert document["supports"] == "PROMOTION"


def test_reader_refuses_to_invent_missing_evidence(reader):
    with pytest.raises(EvidenceNotFoundError) as caught:
        reader.reference("EVID-DOES-NOT-EXIST")
    assert "does not fabricate evidence" in str(caught.value)


def test_reader_returns_nothing_for_an_unknown_strategy(reader):
    assert reader.references_for("no_such_strategy") == []


def test_reader_refuses_a_fixture_that_claims_to_be_live(tmp_path):
    """A CER_LIVE document in the fixture directory is a labelling failure."""
    document = {
        "$hsa_kind": KIND,
        "strategy_id": "gold_context_breakout",
        "strategy_version": "1.0.0",
        "evidence_id": "EVID-REAL-0001",
        "reference_type": "PROMOTION_EVIDENCE",
        "source": SOURCE_CER_LIVE,
        "recorded_at_utc": "2026-09-04T00:00:00Z",
    }
    (tmp_path / "pretends_to_be_live.json").write_text(json.dumps(document))
    with pytest.raises(CerError, match="declares source"):
        FixtureEvidenceReader(tmp_path).references()


def test_reader_refuses_an_invalid_fixture(tmp_path):
    (tmp_path / "broken.json").write_text(
        json.dumps({"$hsa_kind": KIND, "strategy_id": "gold_context_breakout"})
    )
    with pytest.raises(DocumentInvalidError):
        FixtureEvidenceReader(tmp_path).references()


def test_reader_refuses_a_missing_directory(tmp_path):
    with pytest.raises(FixtureUnavailableError):
        FixtureEvidenceReader(tmp_path / "nope")


def test_fixture_directory_env_override_is_honoured(tmp_path, monkeypatch):
    """Location is supplied externally; nothing is baked into the source."""
    monkeypatch.setenv("HSA_CER_FIXTURES_DIR", str(tmp_path))
    assert fixtures_dir() == tmp_path


def test_fixture_directory_env_override_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setenv("HSA_CER_FIXTURES_DIR", str(tmp_path / "missing"))
    with pytest.raises(FixtureUnavailableError, match="not a directory"):
        fixtures_dir()


def test_cer_errors_are_hsa_errors_so_the_cli_maps_them():
    assert issubclass(CerError, HSAError)
    assert issubclass(FixtureUnavailableError, CerError)
    assert issubclass(EvidenceNotFoundError, CerError)


# --------------------------------------------------------------------------
# no evidence store — PID lines 181 and 269
# --------------------------------------------------------------------------


def _digest(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_reading_evidence_writes_nothing(reader, tmp_path, monkeypatch):
    """The adapter must not become the evidence store the PID forbids."""
    directory = fixtures_dir()
    before = _digest(directory)

    monkeypatch.chdir(tmp_path)
    reader.references()
    reader.references_for("gold_context_breakout", "1.0.0")
    reader.reference("FIXTURE-EVID-GOLD-0001-PROMO")
    group_by_reference_type(reader.references())
    build_reference(
        "gold_context_breakout",
        "1.0.0",
        "RESEARCH_FINDING",
        SOURCE_CONTRACT_FIXTURE,
        "2026-09-04T00:00:00Z",
        run_id="FIXTURE-RUN-GOLD-0009",
    )

    assert _digest(directory) == before, "the fixture set was modified"
    assert list(tmp_path.iterdir()) == [], "the adapter created files of its own"


@pytest.mark.parametrize("module", ["hsa/cer.py", "hsa/commands/cer.py"])
def test_the_cer_modules_contain_no_persistence_primitives(module):
    """A CER datastore is an explicit non-goal (PID line 269).

    A guard, not a proof: it catches the obvious ways "just a little local
    evidence storage" gets added later.
    """
    source = Path(__file__).resolve().parent.parent / module
    text = source.read_text(encoding="utf-8")
    for forbidden in (
        "sqlite3",
        "shelve",
        "pickle",
        "dbm",
        ".write_text(",
        ".write_bytes(",
        ".mkdir(",
        "json.dump(",
    ):
        assert forbidden not in text, "%s uses %s" % (module, forbidden)


# --------------------------------------------------------------------------
# grouping
# --------------------------------------------------------------------------


def test_group_by_reference_type_uses_canonical_order(reader):
    grouped = group_by_reference_type(reader.references())
    assert list(grouped) == [
        reference_type
        for reference_type in reference_types()
        if reference_type in grouped
    ]


def test_group_by_reference_type_omits_empty_groups():
    grouped = group_by_reference_type([])
    assert grouped == {}


# --------------------------------------------------------------------------
# the hsa cer command
# --------------------------------------------------------------------------


def test_command_module_satisfies_the_module_contract():
    assert cer_command.NAME == "cer"
    assert isinstance(cer_command.HELP, str) and cer_command.HELP
    assert callable(cer_command.add_arguments)
    assert callable(cer_command.run)


def test_command_is_registered_or_awaiting_the_pl():
    """The PL wires the registry; this passes either way, meaningfully."""
    from hsa.commands import COMMANDS

    if "cer" not in COMMANDS:
        pytest.skip("hsa cer not yet wired into COMMANDS by the PL")
    assert COMMANDS["cer"] is cer_command


def test_cer_list_reports_the_fixture_source(capsys):
    assert cer_command.run(_parse(["list"])) == 0
    out = capsys.readouterr().out
    assert "CONTRACT_FIXTURE" in out
    assert "CER is not live" in out
    assert "PROMOTION_EVIDENCE" in out


def test_cer_list_filters_by_strategy_and_decision(capsys):
    assert (
        cer_command.run(
            _parse(
                [
                    "list",
                    "--strategy",
                    "wick_rejection_sequence",
                    "--supports",
                    "REJECTION",
                ]
            )
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "1 reference" in out
    assert "REJECTION_EVIDENCE" in out
    assert "gold_context_breakout" not in out


def test_cer_list_filters_by_reference_type(capsys):
    assert cer_command.run(_parse(["list", "--type", "VERSION_LINEAGE"])) == 0
    out = capsys.readouterr().out
    assert "VERSION_LINEAGE (2)" in out


def test_cer_list_refuses_an_unknown_reference_type():
    with pytest.raises(CerError, match="no such reference_type"):
        cer_command.run(_parse(["list", "--type", "VIBES"]))


def test_cer_list_says_so_when_nothing_matches(capsys):
    assert cer_command.run(_parse(["list", "--strategy", "no_such_strategy"])) == 0
    assert "(none matched)" in capsys.readouterr().out


def test_cer_show_prints_one_reference(capsys):
    assert cer_command.run(_parse(["show", "FIXTURE-EVID-WICK-0001-REJECT"])) == 0
    out = capsys.readouterr().out
    assert "wick_rejection_sequence" in out
    assert "REJECTION_EVIDENCE" in out
    assert "CONTRACT_FIXTURE" in out


def test_cer_show_raises_for_unknown_evidence():
    with pytest.raises(EvidenceNotFoundError):
        cer_command.run(_parse(["show", "EVID-NOPE"]))


def test_cer_validate_checks_every_fixture(capsys, fixture_paths):
    assert cer_command.run(_parse(["validate"])) == 0
    out = capsys.readouterr().out
    assert "%d fixtures valid and labelled CONTRACT_FIXTURE" % len(fixture_paths) in out


def test_cer_validate_checks_named_files(capsys, fixture_paths):
    assert cer_command.run(_parse(["validate", str(fixture_paths[0])])) == 0
    assert "valid cer_reference" in capsys.readouterr().out


def test_cer_validate_reports_an_invalid_document(invalid_path):
    with pytest.raises(DocumentInvalidError):
        cer_command.run(_parse(["validate", str(invalid_path("cer_reference"))]))


def test_cer_lineage_shows_versions_and_their_evidence(capsys, valid_doc, tmp_path):
    from hsa.versioning import (
        STATUS_PROMOTED,
        apply_status_transition,
        derive_candidate,
    )

    promoted = apply_status_transition(valid_doc("strategy_package"), STATUS_PROMOTED)
    candidate = derive_candidate(promoted, "Widen the confirmation window.")

    paths = []
    for package in (promoted, candidate):
        path = tmp_path / ("%s.json" % package["strategy_version"])
        path.write_text(json.dumps(package, indent=2), encoding="utf-8")
        paths.append(str(path))

    assert cer_command.run(_parse(["lineage", *paths])) == 0
    out = capsys.readouterr().out
    assert "strategy_id gold_context_breakout — 2 versions" in out
    assert "1.0.0  [PROMOTED]" in out
    assert "1.1.0  [CANDIDATE]" in out
    assert "supersedes 1.0.0 — Widen the confirmation window." in out
    assert "original version, supersedes nothing" in out
    assert "PROMOTION_EVIDENCE" in out
    assert "REVISION_EVIDENCE" in out


def test_cer_lineage_can_skip_evidence(capsys, valid_doc, tmp_path):
    path = tmp_path / "package.json"
    path.write_text(json.dumps(valid_doc("strategy_package")), encoding="utf-8")
    assert cer_command.run(_parse(["lineage", "--no-evidence", str(path)])) == 0
    out = capsys.readouterr().out
    assert "1.0.0  [CANDIDATE]" in out
    assert "evidence:" not in out


def test_cer_reads_from_an_explicit_fixture_directory(capsys, tmp_path):
    document = {
        "$hsa_kind": KIND,
        "strategy_id": "gold_context_breakout",
        "strategy_version": "1.0.0",
        "evidence_id": "FIXTURE-EVID-ISOLATED",
        "reference_type": "RESEARCH_FINDING",
        "source": SOURCE_CONTRACT_FIXTURE,
        "recorded_at_utc": "2026-09-04T00:00:00Z",
        "supports": "INFORMATIONAL",
    }
    (tmp_path / "one.json").write_text(json.dumps(document), encoding="utf-8")
    assert cer_command.run(_parse(["--fixtures", str(tmp_path), "list"])) == 0
    out = capsys.readouterr().out
    assert "1 reference" in out
    assert "FIXTURE-EVID-ISOLATED" in out
