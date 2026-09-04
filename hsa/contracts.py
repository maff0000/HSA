"""Loading and validation of the frozen HSA JSON Schema contracts.

This is the shared helper every HSA command imports. Its public surface is
deliberately small and is treated as frozen by the work items built on top
of it:

    DISCRIMINATOR                      the "$hsa_kind" property name
    KINDS                              the canonical document kinds
    contracts_dir()                    resolved contracts/ directory
    schema_path(kind)                  Path to one contract schema
    load_schema(kind)                  parsed schema as a dict
    detect_kind(document)              kind from the document's discriminator
    validate_document(document, ...)   validate, returning the kind
    read_json_file(path)               parse a JSON document from disk

Contracts reference one another across files (a strategy package embeds
full atomic strategy, chain and CER reference documents, and every contract
shares ``common.defs.json``). Resolution is entirely offline: every schema
in the directory is loaded into a local store keyed by its ``$id`` and
handed to the validator, so nothing is ever fetched over the network.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, RefResolver
from jsonschema import exceptions as js_exceptions

from hsa.errors import (
    DocumentInvalidError,
    DocumentReadError,
    MissingDiscriminatorError,
    SchemaLoadError,
    UnknownKindError,
)

__all__ = [
    "DISCRIMINATOR",
    "KINDS",
    "CONTRACTS_DIR_ENV",
    "contracts_dir",
    "schema_path",
    "load_schema",
    "detect_kind",
    "validate_document",
    "read_json_file",
]

#: Property every HSA document carries to identify its own contract.
DISCRIMINATOR = "$hsa_kind"

#: The canonical document kinds. Each maps to contracts/<kind>.schema.json
#: and to the ``$hsa_kind`` const inside that schema. Frozen surface: adding
#: a kind is a contract change, not an implementation detail.
KINDS: tuple[str, ...] = (
    "atomic_strategy",
    "chain",
    "strategy_package",
    "cer_reference",
    "not_sufficiently_defined",
)

#: Optional environment override for the contracts directory. Supplied
#: externally; there is no configuration baked into this source file beyond
#: the repository-relative default used when running from a checkout.
CONTRACTS_DIR_ENV = "HSA_CONTRACTS_DIR"

_SCHEMA_SUFFIX = ".schema.json"

_schema_cache: dict[str, dict] = {}
_store_cache: dict[str, dict] | None = None
_validator_cache: dict[str, Draft202012Validator] = {}


def contracts_dir() -> Path:
    """Resolve the contracts directory, failing loudly if it is absent.

    ``HSA_CONTRACTS_DIR`` wins if set. Otherwise the directory is found by
    walking up from this file to the repository root, which is what makes
    the CLI work from a plain checkout without any configuration.
    """
    override = os.environ.get(CONTRACTS_DIR_ENV)
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_dir():
            raise SchemaLoadError(
                "%s is set to %s but that is not a directory"
                % (CONTRACTS_DIR_ENV, candidate)
            )
        return candidate

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "contracts"
        if (candidate / ("atomic_strategy" + _SCHEMA_SUFFIX)).is_file():
            return candidate

    raise SchemaLoadError(
        "could not locate the contracts directory above %s; set %s"
        % (here, CONTRACTS_DIR_ENV)
    )


def schema_path(kind: str) -> Path:
    """Path to the schema file for ``kind``."""
    if kind not in KINDS:
        raise UnknownKindError(kind, KINDS)
    return contracts_dir() / (kind + _SCHEMA_SUFFIX)


def _read_schema_file(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as handle:
            schema = json.load(handle)
    except FileNotFoundError as exc:
        raise SchemaLoadError("contract schema not found: %s" % path) from exc
    except json.JSONDecodeError as exc:
        raise SchemaLoadError(
            "contract schema %s is not valid JSON: %s" % (path, exc)
        ) from exc
    if not isinstance(schema, dict):
        raise SchemaLoadError(
            "contract schema %s must be a JSON object" % path
        )
    return schema


def load_schema(kind: str) -> dict:
    """Return the parsed schema for ``kind``.

    The result is cached and shared; treat it as read-only.
    """
    if kind not in KINDS:
        raise UnknownKindError(kind, KINDS)
    if kind not in _schema_cache:
        _schema_cache[kind] = _read_schema_file(schema_path(kind))
    return _schema_cache[kind]


def _store() -> dict[str, dict]:
    """Every schema in the contracts directory, keyed by ``$id``.

    Includes ``common.defs.json``, which is shared definitions rather than a
    document kind, so cross-file ``$ref`` resolves without network access.
    """
    global _store_cache
    if _store_cache is None:
        store: dict[str, dict] = {}
        for path in sorted(contracts_dir().glob("*.json")):
            schema = _read_schema_file(path)
            schema_id = schema.get("$id")
            if not schema_id:
                raise SchemaLoadError("contract schema %s has no $id" % path)
            store[schema_id] = schema
        if not store:
            raise SchemaLoadError(
                "no contract schemas found in %s" % contracts_dir()
            )
        _store_cache = store
    return _store_cache


def _validator(kind: str) -> Draft202012Validator:
    if kind not in _validator_cache:
        schema = load_schema(kind)
        resolver = RefResolver(
            base_uri=schema.get("$id", ""),
            referrer=schema,
            store=_store(),
        )
        _validator_cache[kind] = Draft202012Validator(schema, resolver=resolver)
    return _validator_cache[kind]


def detect_kind(document: Any) -> str:
    """Return the contract kind declared by ``document``.

    Raises ``MissingDiscriminatorError`` when the document does not declare
    one, and ``UnknownKindError`` when it declares one HSA does not know.
    Neither case is guessed.
    """
    if not isinstance(document, Mapping):
        raise MissingDiscriminatorError(
            DISCRIMINATOR,
            "document is a %s, not a JSON object" % type(document).__name__,
        )
    if DISCRIMINATOR not in document:
        raise MissingDiscriminatorError(
            DISCRIMINATOR, "no %s property present" % DISCRIMINATOR
        )
    kind = document[DISCRIMINATOR]
    if not isinstance(kind, str) or kind not in KINDS:
        raise UnknownKindError(kind, KINDS)
    return kind


def _format_path(error: js_exceptions.ValidationError) -> str:
    """Render a validator error location as a readable JSON path."""
    rendered = "$"
    for part in error.absolute_path:
        if isinstance(part, int):
            rendered += "[%d]" % part
        else:
            rendered += "." + str(part)
    return rendered


def _most_specific(
    error: js_exceptions.ValidationError,
) -> js_exceptions.ValidationError:
    """Descend into anyOf/oneOf context for the most useful sub-error.

    Combinator keywords otherwise report at the parent location, which hides
    the field that actually failed.
    """
    while error.context:
        better = js_exceptions.best_match(error.context)
        if better is None:
            break
        error = better
    return error


def _combinator_summary(error: js_exceptions.ValidationError) -> str | None:
    """Summarise an anyOf/oneOf whose branches are all required-property sets.

    Reporting one arbitrary branch of such a combinator is actively
    misleading: telling someone that experiment_id is required, when any one
    of four CER identities would do, sends them to fix the wrong thing.
    Returns None for combinators this cannot summarise honestly.
    """
    if error.validator not in ("anyOf", "oneOf") or not error.context:
        return None
    names: list[str] = []
    for sub_error in error.context:
        if sub_error.validator != "required":
            return None
        if list(sub_error.absolute_path) != list(error.absolute_path):
            return None
        names.extend(str(name) for name in sub_error.validator_value)
    if not names:
        return None
    quantifier = "exactly one of" if error.validator == "oneOf" else "at least one of"
    return "%s %s is required" % (quantifier, ", ".join(dict.fromkeys(names)))


def validate_document(
    document: Any,
    kind: str | None = None,
    source: str | None = None,
) -> str:
    """Validate ``document`` against its HSA contract and return its kind.

    ``kind`` forces a contract; when omitted it is auto-detected from the
    document's ``$hsa_kind`` discriminator. ``source`` is an optional label
    (usually a file path) used in error messages.

    Raises ``DocumentInvalidError`` carrying the failing JSON path on
    failure; returns the validated kind on success.
    """
    resolved_kind = kind if kind is not None else detect_kind(document)
    if resolved_kind not in KINDS:
        raise UnknownKindError(resolved_kind, KINDS)

    errors = sorted(
        _validator(resolved_kind).iter_errors(document),
        key=js_exceptions.relevance,
    )
    if not errors:
        return resolved_kind

    failures = []
    for error in errors:
        summary = _combinator_summary(error)
        if summary is not None:
            failures.append(
                {
                    "path": _format_path(error),
                    "message": summary,
                    "schema_path": "/".join(
                        str(part) for part in error.absolute_schema_path
                    ),
                }
            )
            continue
        specific = _most_specific(error)
        failures.append(
            {
                "path": _format_path(specific),
                "message": specific.message,
                "schema_path": "/".join(
                    str(part) for part in specific.absolute_schema_path
                ),
            }
        )
    raise DocumentInvalidError(resolved_kind, failures, source=source)


def read_json_file(path: str | os.PathLike) -> Any:
    """Parse a JSON document from disk, raising ``DocumentReadError``."""
    target = Path(path)
    try:
        with target.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise DocumentReadError("no such file: %s" % target) from exc
    except IsADirectoryError as exc:
        raise DocumentReadError("%s is a directory, not a file" % target) from exc
    except OSError as exc:
        raise DocumentReadError("could not read %s: %s" % (target, exc)) from exc
    except json.JSONDecodeError as exc:
        raise DocumentReadError(
            "%s is not valid JSON: %s (line %d, column %d)"
            % (target, exc.msg, exc.lineno, exc.colno)
        ) from exc
