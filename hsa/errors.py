"""Typed exceptions for HSA.

Every failure mode a command can hit has a type here, so callers branch on
the exception class rather than on message text. ``hsa.cli`` maps these onto
process exit codes; it is the only place that decides exit codes.
"""

from __future__ import annotations

from typing import Any, Sequence

__all__ = [
    "HSAError",
    "ContractError",
    "UnknownKindError",
    "MissingDiscriminatorError",
    "SchemaLoadError",
    "DocumentReadError",
    "DocumentInvalidError",
]


class HSAError(Exception):
    """Base class for every error HSA raises deliberately."""


class ContractError(HSAError):
    """A problem with the contract set itself, or with selecting from it."""


class UnknownKindError(ContractError):
    """A document kind was requested that is not part of the contract set."""

    def __init__(self, kind: Any, known: Sequence[str]) -> None:
        self.kind = kind
        self.known = tuple(known)
        super().__init__(
            "unknown contract kind %r (known kinds: %s)"
            % (kind, ", ".join(self.known))
        )


class MissingDiscriminatorError(ContractError):
    """A document carries no usable ``$hsa_kind`` discriminator.

    Auto-detection is refused rather than guessed: validating a document
    against the wrong contract would report misleading errors, and HSA does
    not guess (PID line 39).
    """

    def __init__(self, discriminator: str, detail: str) -> None:
        self.discriminator = discriminator
        super().__init__(
            "cannot determine contract kind: %s; supply %s in the document "
            "or pass an explicit kind" % (detail, discriminator)
        )


class SchemaLoadError(ContractError):
    """A contract schema file is missing or is not readable JSON."""


class DocumentReadError(HSAError):
    """The document to validate could not be read or parsed as JSON."""


class DocumentInvalidError(HSAError):
    """A document failed validation against its contract.

    Carries the failing JSON path (or paths) rather than only a message, so
    a caller can point at the exact offending location. ``failures`` is a
    list of plain dicts with keys ``path``, ``message`` and ``schema_path``,
    ordered as reported by the validator.
    """

    def __init__(
        self,
        kind: str,
        failures: Sequence[dict],
        source: str | None = None,
    ) -> None:
        self.kind = kind
        self.failures = list(failures)
        self.source = source
        super().__init__(self._render())

    @property
    def json_path(self) -> str:
        """JSON path of the first (most relevant) failure."""
        return self.failures[0]["path"] if self.failures else "$"

    def _render(self) -> str:
        where = self.source or "document"
        head = "%s is not a valid %s (%d problem%s)" % (
            where,
            self.kind,
            len(self.failures),
            "" if len(self.failures) == 1 else "s",
        )
        lines = [head]
        for failure in self.failures:
            lines.append("  at %s: %s" % (failure["path"], failure["message"]))
        return "\n".join(lines)
