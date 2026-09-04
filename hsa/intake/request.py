"""Reading a raw strategy description into an intake request.

PID lines 101-108 name six intake sources, and ``common.defs.json`` pins
them as the ``source_type`` enum. Both intake outcomes require provenance,
so the source type is never inferred from the text: it is either declared in
a structured request file or passed explicitly on the command line. Guessing
it would be the same class of mistake as guessing a trading rule.

Two input forms are accepted:

``<file>.json``
    A structured intake request. This is the natural form for the
    ``EXISTING_SPECIFICATION`` source, and the only form that can carry its
    own ``intake_id``, ``title`` and provenance notes.

any other file
    The raw text itself — a pasted trader explanation, transcript or note.
    ``--source-type`` is then required; ``--source-reference`` defaults to
    the file path, which is a fact about where the text came from rather
    than an assumption about it.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from hsa.intake.errors import IntakeRequestError

__all__ = ["SOURCE_TYPES", "read_request", "build_request", "derive_intake_id"]

#: One per PID lines 102-108, matching common.defs.json#/$defs/source_type.
SOURCE_TYPES: tuple[str, ...] = (
    "MATT_OBSERVATION",
    "TRADER_EXPLANATION",
    "REPORT_OR_BOOK",
    "VIDEO_DERIVED",
    "EXTERNAL_STRATEGY",
    "EXISTING_SPECIFICATION",
)

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_TEXT_KEYS = ("text", "description", "raw_description")


def derive_intake_id(source_reference: str, text: str) -> str:
    """Derive a stable, contract-shaped intake id.

    Deterministic on purpose: re-running intake over the same source
    produces the same id, so a refusal and the resubmission that answers it
    can be tied together (``not_sufficiently_defined.schema.json``,
    ``intake_id``).
    """
    stem = Path(source_reference).stem
    slug = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)[:48].rstrip("_")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    candidate = "intake_%s_%s" % (slug, digest) if slug else "intake_%s" % digest
    candidate = candidate[:64]
    if not _ID_PATTERN.match(candidate):
        candidate = "intake_%s" % digest
    return candidate


def build_request(
    text: str,
    source_type: str,
    source_reference: str,
    intake_id: str | None = None,
    title: str | None = None,
    excerpt: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Assemble and check an intake request."""
    if not isinstance(text, str) or not text.strip():
        raise IntakeRequestError(
            "the strategy description is empty; there is nothing to analyse"
        )
    if source_type not in SOURCE_TYPES:
        raise IntakeRequestError(
            "unknown source_type %r; must be one of: %s (PID lines 102-108)"
            % (source_type, ", ".join(SOURCE_TYPES))
        )
    if not source_reference or not source_reference.strip():
        raise IntakeRequestError("source_reference is required; provenance is mandatory")

    resolved_id = intake_id or derive_intake_id(source_reference, text)
    if not _ID_PATTERN.match(resolved_id):
        raise IntakeRequestError(
            "intake_id %r does not match the contract pattern "
            "^[a-z][a-z0-9_]{2,63}$" % resolved_id
        )
    request: dict[str, Any] = {
        "intake_id": resolved_id,
        "source_type": source_type,
        "source_reference": source_reference.strip(),
        "text": text,
    }
    for key, value in (("title", title), ("excerpt", excerpt), ("notes", notes)):
        if value:
            request[key] = value
    return request


def _from_json(payload: Any, path: Path, cli_source_type: str | None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise IntakeRequestError(
            "%s must be a JSON object holding an intake request" % path
        )
    text = None
    for key in _TEXT_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            text = value
            break
    if text is None:
        raise IntakeRequestError(
            "%s carries no strategy description; expected one of %s as a "
            "non-empty string" % (path, ", ".join(_TEXT_KEYS))
        )
    source_type = payload.get("source_type") or cli_source_type
    if not source_type:
        raise IntakeRequestError(
            "%s declares no source_type and none was given on the command "
            "line. Provenance is mandatory and HSA does not infer it "
            "(PID lines 102-108)." % path
        )
    return build_request(
        text=text,
        source_type=source_type,
        source_reference=payload.get("source_reference") or str(path),
        intake_id=payload.get("intake_id"),
        title=payload.get("title"),
        excerpt=payload.get("excerpt"),
        notes=payload.get("notes"),
    )


def read_request(
    path: str | Path,
    source_type: str | None = None,
    source_reference: str | None = None,
    intake_id: str | None = None,
) -> dict[str, Any]:
    """Read a raw strategy description file into an intake request."""
    target = Path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise IntakeRequestError("no such file: %s" % target) from exc
    except IsADirectoryError as exc:
        raise IntakeRequestError("%s is a directory, not a file" % target) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise IntakeRequestError("could not read %s: %s" % (target, exc)) from exc

    if target.suffix.lower() == ".json":
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise IntakeRequestError(
                "%s is not valid JSON: %s (line %d, column %d)"
                % (target, exc.msg, exc.lineno, exc.colno)
            ) from exc
        request = _from_json(payload, target, source_type)
        if source_reference:
            request["source_reference"] = source_reference
        if intake_id:
            request["intake_id"] = intake_id
            if not _ID_PATTERN.match(intake_id):
                raise IntakeRequestError(
                    "intake_id %r does not match the contract pattern "
                    "^[a-z][a-z0-9_]{2,63}$" % intake_id
                )
        return request

    if not source_type:
        raise IntakeRequestError(
            "%s is raw text, so --source-type is required. HSA does not infer "
            "provenance from the text (PID lines 102-108); one of: %s"
            % (target, ", ".join(SOURCE_TYPES))
        )
    return build_request(
        text=raw,
        source_type=source_type,
        source_reference=source_reference or str(target),
        intake_id=intake_id,
    )
