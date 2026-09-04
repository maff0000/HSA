"""Tests for ``hsa boot`` and the boot manifest.

Almost every test here builds its own manifest and its own artifact tree
under ``tmp_path``. That is deliberate: the boot set names artifacts owned by
other work items (the atomic catalogue, the composition doctrine, the
ambiguity policy, the CER contract, the strategy inventory) which do not
exist while those work items are still in flight. A test suite that asserted
on them would fail for reasons that have nothing to do with the boot gate.

The tests that touch the *real* manifest therefore assert only two things:
that the manifest is itself well formed, and that the artifacts this work
item is responsible for resolve.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hsa.cli import EXIT_ERROR, EXIT_OK, main
from hsa.commands import COMMANDS
from hsa.commands import boot as boot_module
from hsa.commands.boot import (
    STATUS_EMPTY,
    STATUS_MISSING,
    STATUS_OK,
    STATUS_UNREADABLE,
    STATUS_WRONG_TYPE,
    BootIncompleteError,
    ManifestError,
    boot,
    check_artifact,
    default_root,
    load_manifest,
    manifest_path,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_MANIFEST = REPO_ROOT / "docs" / "boot-manifest.json"

#: Artifacts this work item (W2A) owns or inherits from the frozen contract
#: spine. Only these may be asserted to exist; everything else in the real
#: manifest belongs to a work item that may not have landed yet.
OWNED_PATHS = (
    "docs/HSA-ROLE.md",
    "docs/HELIOS-STRATEGY-BLUEPRINT.md",
    "docs/BOOT.md",
    "contracts/README.md",
    "contracts/common.defs.json",
    "contracts/atomic_strategy.schema.json",
    "contracts/chain.schema.json",
    "contracts/strategy_package.schema.json",
    "contracts/cer_reference.schema.json",
    "contracts/not_sufficiently_defined.schema.json",
)


# --- helpers -----------------------------------------------------------------


def _entry(entry_id: str, path: str, **extra) -> dict:
    entry = {
        "id": entry_id,
        "title": entry_id.replace("-", " "),
        "path": path,
        "type": "file",
        "required": True,
        "pid": "PID.md:208",
        "why": "test fixture entry",
    }
    entry.update(extra)
    return entry


def _write_manifest(tmp_path: Path, entries, **overrides) -> Path:
    document = {"manifest_version": "1", "artifacts": list(entries)}
    document.update(overrides)
    target = tmp_path / "boot-manifest.json"
    target.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return target


def _populate(root: Path, entries) -> None:
    """Create every artifact an entry list declares, so the boot is clean."""
    for entry in entries:
        target = root / entry["path"]
        if entry["type"] == "directory":
            target.mkdir(parents=True, exist_ok=True)
            (target / "example.json").write_text("{}\n", encoding="utf-8")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# %s\n\ncontent\n" % entry["id"], encoding="utf-8")


@pytest.fixture
def boot_tree(tmp_path):
    """A complete, healthy boot: a manifest plus every artifact it declares."""
    entries = [
        _entry("role", "docs/HSA-ROLE.md"),
        _entry("blueprint", "docs/HELIOS-STRATEGY-BLUEPRINT.md"),
        _entry("schema", "contracts/thing.schema.json"),
        _entry(
            "catalogue",
            "catalogue/atomic/",
            type="directory",
            expect_glob="*",
            min_matches=1,
        ),
        _entry("inventory", "strategies/", type="directory", required=False),
    ]
    root = tmp_path / "repo"
    root.mkdir()
    _populate(root, entries)
    manifest = _write_manifest(tmp_path, entries)
    return manifest, root, entries


@pytest.fixture(autouse=True)
def register_boot(monkeypatch):
    """Register ``boot`` in the CLI registry for the duration of each test.

    ``hsa/commands/__init__.py`` is wired centrally by the PL, so these tests
    must pass whether or not that line is uncommented yet. Setting the item
    to the same module the registry will hold is a no-op once it is.
    """
    monkeypatch.setitem(COMMANDS, "boot", boot_module)


def _boot_argv(manifest: Path, root: Path, *extra: str) -> list[str]:
    return ["boot", "--manifest", str(manifest), "--root", str(root), *extra]


# --- the command module contract ---------------------------------------------


def test_boot_satisfies_the_command_module_contract():
    assert boot_module.NAME == "boot"
    assert isinstance(boot_module.HELP, str) and boot_module.HELP
    assert callable(boot_module.add_arguments)
    assert callable(boot_module.run)


# --- a healthy boot ----------------------------------------------------------


def test_a_complete_boot_reports_ok(boot_tree):
    manifest, root, entries = boot_tree
    report = boot(manifest, root)
    assert report["ok"] is True
    assert report["failures"] == []
    assert len(report["loaded"]) == len(entries)


def test_a_complete_boot_exits_zero(boot_tree, capsys):
    manifest, root, _ = boot_tree
    assert main(_boot_argv(manifest, root)) == EXIT_OK
    out = capsys.readouterr().out
    assert "HSA booted" in out
    assert "0 required missing" in out


def test_the_report_lists_every_declared_artifact(boot_tree, capsys):
    manifest, root, entries = boot_tree
    main(_boot_argv(manifest, root))
    out = capsys.readouterr().out
    for entry in entries:
        assert entry["path"] in out


def test_boot_timestamp_is_utc(boot_tree):
    manifest, root, _ = boot_tree
    report = boot(manifest, root)
    assert report["booted_at"].endswith("Z")
    assert "T" in report["booted_at"]


# --- a missing required artifact fails the boot ------------------------------


def test_a_missing_required_artifact_fails_the_boot(boot_tree):
    manifest, root, _ = boot_tree
    (root / "docs" / "HELIOS-STRATEGY-BLUEPRINT.md").unlink()
    report = boot(manifest, root)
    assert report["ok"] is False
    assert [f["path"] for f in report["failures"]] == [
        "docs/HELIOS-STRATEGY-BLUEPRINT.md"
    ]
    assert report["failures"][0]["status"] == STATUS_MISSING


def test_a_missing_required_artifact_exits_non_zero(boot_tree, capsys):
    manifest, root, _ = boot_tree
    (root / "docs" / "HELIOS-STRATEGY-BLUEPRINT.md").unlink()
    code = main(_boot_argv(manifest, root))
    assert code != EXIT_OK
    assert code == EXIT_ERROR


def test_the_failure_message_names_the_missing_path(boot_tree, capsys):
    manifest, root, _ = boot_tree
    (root / "docs" / "HELIOS-STRATEGY-BLUEPRINT.md").unlink()
    main(_boot_argv(manifest, root))
    captured = capsys.readouterr()
    assert "docs/HELIOS-STRATEGY-BLUEPRINT.md" in captured.err
    assert "boot incomplete" in captured.err
    assert "1 required artifact could not be loaded" in captured.err
    assert "MISSING" in captured.out


def test_every_missing_required_path_is_named_not_just_the_first(boot_tree):
    manifest, root, _ = boot_tree
    (root / "docs" / "HSA-ROLE.md").unlink()
    (root / "docs" / "HELIOS-STRATEGY-BLUEPRINT.md").unlink()
    with pytest.raises(BootIncompleteError) as caught:
        boot_module.run(
            _parse(_boot_argv(manifest, root))
        )
    assert sorted(caught.value.missing_paths) == [
        "docs/HELIOS-STRATEGY-BLUEPRINT.md",
        "docs/HSA-ROLE.md",
    ]


def _parse(argv):
    from hsa.cli import build_parser

    return build_parser().parse_args(argv)


def test_an_empty_required_file_is_not_loaded_doctrine(boot_tree):
    manifest, root, _ = boot_tree
    (root / "docs" / "HSA-ROLE.md").write_text("   \n\n", encoding="utf-8")
    report = boot(manifest, root)
    assert report["ok"] is False
    assert report["failures"][0]["status"] == STATUS_EMPTY
    assert "empty" in report["failures"][0]["detail"]


def test_a_required_file_that_is_not_utf8_text_fails(boot_tree):
    manifest, root, _ = boot_tree
    (root / "docs" / "HSA-ROLE.md").write_bytes(b"\xff\xfe\x00not text")
    report = boot(manifest, root)
    assert report["ok"] is False
    assert report["failures"][0]["status"] == STATUS_UNREADABLE


def test_a_file_entry_that_is_actually_a_directory_fails(boot_tree):
    manifest, root, _ = boot_tree
    target = root / "docs" / "HSA-ROLE.md"
    target.unlink()
    target.mkdir()
    report = boot(manifest, root)
    assert report["failures"][0]["status"] == STATUS_WRONG_TYPE


def test_a_required_directory_below_min_matches_fails(boot_tree):
    manifest, root, _ = boot_tree
    for child in (root / "catalogue" / "atomic").iterdir():
        child.unlink()
    report = boot(manifest, root)
    assert report["ok"] is False
    assert report["failures"][0]["path"] == "catalogue/atomic/"
    assert report["failures"][0]["status"] == STATUS_EMPTY


def test_a_missing_required_directory_fails(boot_tree):
    manifest, root, _ = boot_tree
    for child in (root / "catalogue" / "atomic").iterdir():
        child.unlink()
    (root / "catalogue" / "atomic").rmdir()
    report = boot(manifest, root)
    assert report["failures"][0]["status"] == STATUS_MISSING


# --- a missing optional artifact warns and still boots -----------------------


def test_a_missing_optional_artifact_still_boots(boot_tree):
    manifest, root, _ = boot_tree
    (root / "strategies" / "example.json").unlink()
    (root / "strategies").rmdir()
    report = boot(manifest, root)
    assert report["ok"] is True
    assert report["failures"] == []
    assert [w["path"] for w in report["warnings"]] == ["strategies/"]


def test_a_missing_optional_artifact_exits_zero_with_a_warning(boot_tree, capsys):
    manifest, root, _ = boot_tree
    (root / "strategies" / "example.json").unlink()
    (root / "strategies").rmdir()
    assert main(_boot_argv(manifest, root)) == EXIT_OK
    out = capsys.readouterr().out
    assert "warn" in out
    assert "strategies/" in out
    assert "optional" in out
    assert "1 optional absent" in out
    assert "HSA booted" in out


def test_an_empty_optional_directory_is_only_a_warning(boot_tree):
    manifest, root, _ = boot_tree
    for child in (root / "strategies").iterdir():
        child.unlink()
    report = boot(manifest, root)
    assert report["ok"] is True


# --- output modes ------------------------------------------------------------


def test_json_output_is_machine_readable_with_digests(boot_tree, capsys):
    manifest, root, _ = boot_tree
    assert main(_boot_argv(manifest, root, "--json")) == EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True
    assert report["booted_at"].endswith("Z")
    files = [a for a in report["artifacts"] if a["type"] == "file"]
    assert files and all(len(a["sha256"]) == 64 for a in files)


def test_quiet_suppresses_the_loaded_lines_but_not_problems(boot_tree, capsys):
    manifest, root, _ = boot_tree
    (root / "strategies" / "example.json").unlink()
    (root / "strategies").rmdir()
    assert main(_boot_argv(manifest, root, "--quiet")) == EXIT_OK
    out = capsys.readouterr().out
    assert "docs/HSA-ROLE.md" not in out
    assert "strategies/" in out


def test_a_root_that_is_not_a_directory_fails_loudly(boot_tree, tmp_path, capsys):
    manifest, _, _ = boot_tree
    code = main(_boot_argv(manifest, tmp_path / "absent"))
    assert code == EXIT_ERROR
    assert "boot root is not a directory" in capsys.readouterr().err


# --- locating the manifest ---------------------------------------------------


def test_manifest_is_found_from_the_checkout_without_configuration(monkeypatch):
    monkeypatch.delenv(boot_module.MANIFEST_ENV, raising=False)
    assert manifest_path().resolve() == REAL_MANIFEST.resolve()


def test_environment_override_is_honoured(tmp_path, monkeypatch):
    other = _write_manifest(tmp_path, [_entry("role", "docs/HSA-ROLE.md")])
    monkeypatch.setenv(boot_module.MANIFEST_ENV, str(other))
    assert manifest_path() == other


def test_a_bad_environment_override_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setenv(boot_module.MANIFEST_ENV, str(tmp_path / "nope.json"))
    with pytest.raises(ManifestError) as caught:
        manifest_path()
    assert boot_module.MANIFEST_ENV in str(caught.value)


def test_an_explicit_missing_manifest_fails_loudly(tmp_path):
    with pytest.raises(ManifestError) as caught:
        manifest_path(tmp_path / "nope.json")
    assert "boot manifest not found" in str(caught.value)


def test_default_root_is_the_repository_root(tmp_path):
    manifest = tmp_path / "docs" / "boot-manifest.json"
    manifest.parent.mkdir()
    manifest.write_text("{}", encoding="utf-8")
    assert default_root(manifest) == tmp_path.resolve()


# --- a manifest that cannot be trusted checks nothing ------------------------


@pytest.mark.parametrize(
    "payload, expected",
    [
        ("[]", "must be a JSON object"),
        ('{"artifacts": []}', "manifest_version"),
        ('{"manifest_version": "1"}', "declares no artifacts"),
        ('{"manifest_version": "1", "artifacts": []}', "declares no artifacts"),
        ("{ not json", "not valid JSON"),
    ],
)
def test_a_malformed_manifest_is_rejected(tmp_path, payload, expected):
    target = tmp_path / "boot-manifest.json"
    target.write_text(payload, encoding="utf-8")
    with pytest.raises(ManifestError) as caught:
        load_manifest(target)
    assert expected in str(caught.value)


@pytest.mark.parametrize(
    "entry, expected",
    [
        ({"title": "t", "path": "a", "type": "file", "required": True}, "has no id"),
        ({"id": "a", "path": "a", "type": "file", "required": True}, "has no title"),
        ({"id": "a", "title": "t", "type": "file", "required": True}, "has no path"),
        ({"id": "a", "title": "t", "path": "a", "required": True}, "has no type"),
        (
            {"id": "a", "title": "t", "path": "a", "type": "socket", "required": True},
            "expected one of",
        ),
        (
            {"id": "a", "title": "t", "path": "a", "type": "file"},
            "required as true or false",
        ),
        (
            {"id": "a", "title": "t", "path": "a", "type": "file", "required": "yes"},
            "required as true or false",
        ),
        (
            {"id": "a", "title": "t", "path": "/etc/passwd", "type": "file",
             "required": True},
            "repository-relative",
        ),
        (
            {"id": "a", "title": "t", "path": "../secrets", "type": "file",
             "required": True},
            "escape the repository",
        ),
        (
            {"id": "a", "title": "t", "path": "a", "type": "directory",
             "required": True, "min_matches": -1},
            "non-negative integer",
        ),
    ],
)
def test_a_malformed_entry_is_rejected(tmp_path, entry, expected):
    manifest = _write_manifest(tmp_path, [entry])
    with pytest.raises(ManifestError) as caught:
        load_manifest(manifest)
    assert expected in str(caught.value)


def test_duplicate_artifact_ids_are_rejected(tmp_path):
    manifest = _write_manifest(
        tmp_path, [_entry("role", "docs/a.md"), _entry("role", "docs/b.md")]
    )
    with pytest.raises(ManifestError) as caught:
        load_manifest(manifest)
    assert "duplicate artifact id" in str(caught.value)


def test_a_broken_manifest_checks_nothing_rather_than_booting_clean(tmp_path):
    target = tmp_path / "boot-manifest.json"
    target.write_text('{"manifest_version": "1", "artifacts": []}', encoding="utf-8")
    with pytest.raises(ManifestError):
        boot(target, tmp_path)


# --- the real manifest -------------------------------------------------------


def test_the_real_manifest_is_valid_and_structurally_sound():
    manifest = load_manifest(REAL_MANIFEST)
    assert manifest["manifest_version"]
    assert len(manifest["artifacts"]) >= 7


def test_the_real_manifest_covers_the_pid_boot_set():
    """PID.md:208-216 lists seven things a fresh boot must be able to load."""
    ids = {entry["id"] for entry in load_manifest(REAL_MANIFEST)["artifacts"]}
    for required_id in (
        "hsa-role",
        "strategy-blueprint",
        "contract-strategy-package",
        "atomic-catalogue",
        "composition-doctrine",
        "cer-contract",
        "strategy-inventory",
    ):
        assert required_id in ids, "boot set is missing %s" % required_id


def test_only_pid_sanctioned_entries_are_optional():
    """Optionality that is not traceable to the PID stops boot being a gate.

    PID.md:216 qualifies the strategy inventory with "where available", and
    PID.md:181 makes CER fixtures a stand-in used only while CER is not live.
    Nothing else in the boot set may be optional.
    """
    optional = {
        entry["id"]
        for entry in load_manifest(REAL_MANIFEST)["artifacts"]
        if not entry["required"]
    }
    assert optional == {"strategy-inventory", "cer-fixtures"}


def test_every_real_entry_cites_the_pid_and_says_why():
    for entry in load_manifest(REAL_MANIFEST)["artifacts"]:
        assert entry.get("pid"), "%s cites no PID line" % entry["id"]
        assert "PID.md:" in entry["pid"]
        assert entry.get("why"), "%s does not say why it is in the boot set" % entry["id"]


def test_directory_entries_are_written_as_directories():
    for entry in load_manifest(REAL_MANIFEST)["artifacts"]:
        if entry["type"] == "directory":
            assert entry["path"].endswith("/"), entry["id"]


def test_the_artifacts_this_work_item_owns_resolve():
    """Only W2A's own artifacts and the frozen contract spine.

    The rest of the boot set belongs to work items that may not have landed
    yet; asserting on them here would fail for the wrong reason.
    """
    manifest = load_manifest(REAL_MANIFEST)
    by_path = {entry["path"]: entry for entry in manifest["artifacts"]}
    for path in OWNED_PATHS:
        assert path in by_path, "%s is not declared in the boot manifest" % path
        result = check_artifact(REPO_ROOT, by_path[path])
        assert result["status"] == STATUS_OK, "%s: %s" % (path, result["detail"])


def test_the_agent_definition_exists_and_boots_before_working():
    """PID.md:204 — HSA must be explicitly bootable as a dedicated AI role."""
    agent = REPO_ROOT / ".claude" / "agents" / "hsa.md"
    assert agent.is_file()
    text = agent.read_text(encoding="utf-8")
    assert text.startswith("---")
    for field in ("name: hsa", "description:", "tools:"):
        assert field in text
    assert "hsa.cli boot" in text
    assert "docs/HELIOS-STRATEGY-BLUEPRINT.md" in text
