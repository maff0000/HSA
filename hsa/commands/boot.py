"""``hsa boot`` — load and verify the durable HSA boot doctrine.

PID.md lines 202-218 require HSA to be explicitly bootable, its durable
authority to live in Git rather than chat memory, and the boot path to be
documented and repeatable. This command is the machine half of that: it
reads ``docs/boot-manifest.json``, verifies every artifact the manifest
declares, loads it, and reports what was loaded.

It is a **gate**, not a greeting. A boot that succeeds with half its
doctrine absent would let a fresh session start work believing it holds
doctrine it never read, which is the exact failure PID.md line 7 exists to
prevent. So a missing, unreadable or empty *required* artifact fails the
boot loudly and names the path. Artifacts the PID genuinely allows to be
absent — the strategy inventory, "where available" (PID.md:216), and the CER
fixtures that stand in only while CER is not live (PID.md:181) — are marked
``required: false`` in the manifest and produce a warning instead.

Exit codes are owned by ``hsa.cli``, not here (see the module contract in
``hsa/commands/__init__.py``). A failed boot raises ``BootIncompleteError``,
an ``HSAError``, which ``hsa.cli`` maps to exit code 3 — its category for a
deliberate error such as an unreadable file. Exit code 1 is reserved there
for contract-validation failure, which a boot failure is not.

The manifest, not this module, is the single declaration of what boot means:
adding an artifact to the boot set is a manifest edit, never a code edit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from hsa.contracts import read_json_file
from hsa.errors import HSAError

NAME = "boot"
HELP = "load and verify the durable HSA boot doctrine, failing if any required artifact is missing"

#: Optional environment override for the manifest location. Supplied
#: externally; no deployment-specific path is baked into this source file.
MANIFEST_ENV = "HSA_BOOT_MANIFEST"

#: Where the manifest lives inside a checkout, relative to the repository
#: root. This is repository layout, not configuration.
MANIFEST_RELATIVE = Path("docs") / "boot-manifest.json"

_VALID_TYPES = ("file", "directory")

#: Status values a checked artifact can carry. Only ``ok`` counts as loaded.
STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_EMPTY = "empty"
STATUS_UNREADABLE = "unreadable"
STATUS_WRONG_TYPE = "wrong-type"

__all__ = [
    "NAME",
    "HELP",
    "MANIFEST_ENV",
    "MANIFEST_RELATIVE",
    "BootIncompleteError",
    "ManifestError",
    "add_arguments",
    "run",
    "manifest_path",
    "load_manifest",
    "check_artifact",
    "boot",
]


class ManifestError(HSAError):
    """The boot manifest itself is missing, malformed or self-inconsistent.

    Distinct from a missing artifact: this means the declaration of what
    boot means cannot be trusted, so nothing is checked against it.
    """


class BootIncompleteError(HSAError):
    """A required boot artifact is missing, unreadable or empty.

    Carries the failing entries rather than only a message, so a caller can
    act on the list. Belongs alongside the other typed errors in
    ``hsa/errors.py``; it lives here because work item W2A does not own that
    file, and moving it there later is a pure relocation.
    """

    def __init__(self, failures: Iterable[Mapping[str, Any]]) -> None:
        self.failures = [dict(failure) for failure in failures]
        super().__init__(self._render())

    @property
    def missing_paths(self) -> list[str]:
        return [failure["path"] for failure in self.failures]

    def _render(self) -> str:
        count = len(self.failures)
        lines = [
            "boot incomplete: %d required artifact%s could not be loaded"
            % (count, "" if count == 1 else "s")
        ]
        for failure in self.failures:
            lines.append(
                "  %s: %s (%s)"
                % (failure["path"], failure["status"], failure["detail"])
            )
        lines.append(
            "HSA has not booted. Its doctrine is incomplete, so it must not "
            "engineer a strategy in this state."
        )
        return "\n".join(lines)


# --- locating and parsing the manifest ---------------------------------------


def manifest_path(override: str | os.PathLike | None = None) -> Path:
    """Resolve the boot manifest, failing loudly if it cannot be found.

    Precedence: an explicit ``override`` (the ``--manifest`` option), then
    the ``HSA_BOOT_MANIFEST`` environment variable, then the manifest found
    by walking up from this file to the repository root — which is what
    makes the command work from a plain checkout with no configuration.
    """
    if override is not None:
        candidate = Path(override).expanduser()
        if not candidate.is_file():
            raise ManifestError("boot manifest not found: %s" % candidate)
        return candidate

    from_env = os.environ.get(MANIFEST_ENV)
    if from_env:
        candidate = Path(from_env).expanduser()
        if not candidate.is_file():
            raise ManifestError(
                "%s is set to %s but that is not a file"
                % (MANIFEST_ENV, candidate)
            )
        return candidate

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / MANIFEST_RELATIVE
        if candidate.is_file():
            return candidate

    raise ManifestError(
        "could not locate %s above %s; set %s"
        % (MANIFEST_RELATIVE, here, MANIFEST_ENV)
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ManifestError(message)


def _check_entry(entry: Any, index: int, seen: set) -> dict:
    where = "artifacts[%d]" % index
    _require(isinstance(entry, Mapping), "%s is not a JSON object" % where)

    for field in ("id", "title", "path", "type"):
        _require(
            isinstance(entry.get(field), str) and entry[field],
            "%s has no %s" % (where, field),
        )
    entry_id = entry["id"]
    _require(entry_id not in seen, "duplicate artifact id %r" % entry_id)
    seen.add(entry_id)

    _require(
        entry["type"] in _VALID_TYPES,
        "%s (%s) has type %r, expected one of: %s"
        % (where, entry_id, entry["type"], ", ".join(_VALID_TYPES)),
    )
    _require(
        isinstance(entry.get("required"), bool),
        "%s (%s) must declare required as true or false" % (where, entry_id),
    )

    path = entry["path"]
    _require(
        not Path(path).is_absolute(),
        "%s (%s) path %r must be repository-relative" % (where, entry_id, path),
    )
    _require(
        ".." not in Path(path).parts,
        "%s (%s) path %r must not escape the repository" % (where, entry_id, path),
    )

    min_matches = entry.get("min_matches", 0)
    _require(
        isinstance(min_matches, int)
        and not isinstance(min_matches, bool)
        and min_matches >= 0,
        "%s (%s) min_matches must be a non-negative integer" % (where, entry_id),
    )
    return dict(entry)


def load_manifest(path: str | os.PathLike) -> dict:
    """Read and structurally check the manifest at ``path``.

    The manifest is repository data, not one of the frozen contract kinds in
    ``contracts/``, so it carries no ``$hsa_kind`` and is checked here rather
    than by ``hsa.contracts``. Anything wrong with it raises
    ``ManifestError``: a manifest that cannot be trusted must not silently
    check nothing.
    """
    target = Path(path)
    try:
        document = read_json_file(target)
    except HSAError as exc:
        raise ManifestError("boot manifest %s: %s" % (target, exc)) from exc

    _require(
        isinstance(document, Mapping),
        "boot manifest %s must be a JSON object" % target,
    )
    _require(
        isinstance(document.get("manifest_version"), str)
        and document["manifest_version"],
        "boot manifest %s has no manifest_version" % target,
    )
    artifacts = document.get("artifacts")
    _require(
        isinstance(artifacts, list) and artifacts,
        "boot manifest %s declares no artifacts" % target,
    )

    seen: set = set()
    checked = [
        _check_entry(entry, index, seen) for index, entry in enumerate(artifacts)
    ]
    manifest = dict(document)
    manifest["artifacts"] = checked
    return manifest


def default_root(manifest_file: Path) -> Path:
    """Repository root implied by a manifest at ``<root>/docs/boot-manifest.json``."""
    return manifest_file.resolve().parent.parent


# --- checking one artifact ----------------------------------------------------


def _human_bytes(count: int) -> str:
    if count < 1024:
        return "%d B" % count
    if count < 1024 * 1024:
        return "%.1f KB" % (count / 1024)
    return "%.1f MB" % (count / (1024 * 1024))


def _check_file(target: Path, entry: Mapping[str, Any], result: dict) -> dict:
    if not target.exists():
        result["status"] = STATUS_MISSING
        result["detail"] = "no such file"
        return result
    if not target.is_file():
        result["status"] = STATUS_WRONG_TYPE
        result["detail"] = "declared as a file but is not one"
        return result
    try:
        payload = target.read_bytes()
    except OSError as exc:
        result["status"] = STATUS_UNREADABLE
        result["detail"] = "could not read: %s" % exc
        return result

    result["bytes"] = len(payload)
    if not payload.strip():
        result["status"] = STATUS_EMPTY
        result["detail"] = "file is empty; doctrine that is not written is not loaded"
        return result

    if entry.get("text", True):
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            result["status"] = STATUS_UNREADABLE
            result["detail"] = "is not valid UTF-8 text: %s" % exc
            return result
        result["lines"] = len(text.splitlines())
        result["summary"] = "%s, %d lines" % (_human_bytes(len(payload)), result["lines"])
    else:
        result["summary"] = _human_bytes(len(payload))

    result["sha256"] = hashlib.sha256(payload).hexdigest()
    result["status"] = STATUS_OK
    result["detail"] = "loaded"
    return result


def _check_directory(target: Path, entry: Mapping[str, Any], result: dict) -> dict:
    if not target.exists():
        result["status"] = STATUS_MISSING
        result["detail"] = "no such directory"
        return result
    if not target.is_dir():
        result["status"] = STATUS_WRONG_TYPE
        result["detail"] = "declared as a directory but is not one"
        return result

    pattern = entry.get("expect_glob", "*")
    try:
        matches = sorted(str(match.name) for match in target.glob(pattern))
    except OSError as exc:
        result["status"] = STATUS_UNREADABLE
        result["detail"] = "could not list: %s" % exc
        return result

    minimum = int(entry.get("min_matches", 0))
    result["matches"] = len(matches)
    result["entries"] = matches
    if len(matches) < minimum:
        result["status"] = STATUS_EMPTY
        result["detail"] = (
            "holds %d entr%s matching %r, expected at least %d"
            % (len(matches), "y" if len(matches) == 1 else "ies", pattern, minimum)
        )
        return result

    result["summary"] = "%d entr%s" % (len(matches), "y" if len(matches) == 1 else "ies")
    result["status"] = STATUS_OK
    result["detail"] = "loaded"
    return result


def check_artifact(root: Path, entry: Mapping[str, Any]) -> dict:
    """Verify one manifest entry against ``root`` and return a result dict."""
    target = root / entry["path"]
    result: dict[str, Any] = {
        "id": entry["id"],
        "title": entry["title"],
        "path": entry["path"],
        "type": entry["type"],
        "required": bool(entry["required"]),
        "resolved_path": str(target),
        "status": STATUS_MISSING,
        "detail": "",
        "summary": "",
        "pid": entry.get("pid", ""),
        "why": entry.get("why", ""),
    }
    if entry["type"] == "file":
        return _check_file(target, entry, result)
    return _check_directory(target, entry, result)


# --- the boot itself ----------------------------------------------------------


def boot(manifest_file: Path, root: Path) -> dict:
    """Load the manifest and check every artifact. Never raises on failure.

    Returns the full boot report; ``run`` decides what to do with it. Keeping
    the decision out of here is what lets tests assert on the report.
    """
    manifest = load_manifest(manifest_file)
    results = [check_artifact(root, entry) for entry in manifest["artifacts"]]
    failures = [
        result
        for result in results
        if result["required"] and result["status"] != STATUS_OK
    ]
    warnings = [
        result
        for result in results
        if not result["required"] and result["status"] != STATUS_OK
    ]
    return {
        "booted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "manifest": str(manifest_file),
        "manifest_version": manifest["manifest_version"],
        "root": str(root),
        "artifacts": results,
        "loaded": [r for r in results if r["status"] == STATUS_OK],
        "failures": failures,
        "warnings": warnings,
        "ok": not failures,
    }


def _render_report(report: Mapping[str, Any], quiet: bool) -> list[str]:
    lines: list[str] = []
    if not quiet:
        lines.append("HSA boot — %s" % report["booted_at"])
        lines.append(
            "manifest: %s (version %s)"
            % (report["manifest"], report["manifest_version"])
        )
        lines.append("root:     %s" % report["root"])
        lines.append("")

    width = max(
        (len(result["path"]) for result in report["artifacts"]), default=0
    )
    for result in report["artifacts"]:
        if result["status"] == STATUS_OK:
            if quiet:
                continue
            marker = "ok"
            trailer = result["summary"]
        elif result["required"]:
            # "MISSING" is the common case and worth naming precisely; an
            # artifact that is present but empty or unreadable is a FAILED
            # one, and the trailer says which.
            marker = "MISSING" if result["status"] == STATUS_MISSING else "FAILED"
            trailer = "REQUIRED — %s" % result["detail"]
        else:
            marker = "warn"
            trailer = "optional — %s" % result["detail"]
        lines.append(
            "  [%s] %s  %s"
            % (marker.center(7), result["path"].ljust(width), trailer)
        )

    if not quiet:
        lines.append("")
    lines.append(
        "%d artifacts declared: %d loaded, %d required missing, %d optional absent"
        % (
            len(report["artifacts"]),
            len(report["loaded"]),
            len(report["failures"]),
            len(report["warnings"]),
        )
    )
    return lines


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--manifest",
        metavar="<file>",
        default=None,
        help=(
            "boot manifest to use. Defaults to %s, or to %s when set."
            % (MANIFEST_RELATIVE, MANIFEST_ENV)
        ),
    )
    parser.add_argument(
        "--root",
        metavar="<dir>",
        default=None,
        help=(
            "directory the manifest paths are relative to. Defaults to the "
            "repository root implied by the manifest's own location."
        ),
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit the boot report as JSON, including a sha256 per loaded file",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="report only problems and the summary line",
    )


def run(args: argparse.Namespace) -> int:
    manifest_file = manifest_path(args.manifest)
    root = (
        Path(args.root).expanduser().resolve()
        if args.root
        else default_root(manifest_file)
    )
    if not root.is_dir():
        raise ManifestError("boot root is not a directory: %s" % root)

    report = boot(manifest_file, root)

    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=False))
    else:
        print("\n".join(_render_report(report, quiet=args.quiet)))

    # The report goes to stdout and the failure to stderr; flush so the two
    # stay in order when a terminal or a log interleaves them.
    sys.stdout.flush()

    if report["failures"]:
        raise BootIncompleteError(report["failures"])

    if not args.as_json and not args.quiet:
        print("")
        print(
            "HSA booted. Read the loaded artifacts in the order above before "
            "engineering a strategy; see docs/BOOT.md."
        )
    return 0
