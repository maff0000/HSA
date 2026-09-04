"""``hsa chain`` — validate a strategy chain and explain what it composes.

Two kinds of validation run, in this order, and both must pass:

  1. STRUCTURAL, via ``hsa.contracts`` — the document is a valid ``chain``
     against the frozen schema.
  2. SEMANTIC, via ``hsa.semantics`` — the cross-field rules JSON Schema
     cannot express: unique input handles, contiguous SEQUENCE ordering, an
     optional input that is never the sole cause of a match, a CONTEXT that
     genuinely sits above its TRIGGER, and every referenced atomic strategy
     resolving to a real catalogue entry at the exact version pinned.

Then it explains the composition in plain terms: what each primitive means as
applied here, what each input contributes, and what the chain preserves —
identity, state, direction, timing, persistence, expiry, timeframe semantics
and provenance (PID lines 70-80).

Reference resolution needs the atomic strategy catalogue. It is found
automatically in a checkout, overridden with ``--catalogue``, or switched off
with ``--no-catalogue`` when checking a chain in isolation.

This module raises the typed errors from ``hsa.errors``; ``hsa.cli`` owns the
mapping from exception type to process exit code.
"""

from __future__ import annotations

import argparse
from typing import Any, Mapping

from hsa.contracts import detect_kind, read_json_file, validate_document
from hsa.errors import ContractError
from hsa.semantics import Catalogue, check_chain, raise_if_invalid

NAME = "chain"
HELP = "validate a strategy chain and explain its composition"

#: What each canonical primitive means (PID lines 63-68). Kept in step with
#: docs/COMPOSITION-DOCTRINE.md, which is the authority; this is the one-line
#: form printed at the terminal.
PRIMITIVE_SEMANTICS: dict[str, str] = {
    "ALL": (
        "every required input must match on the same evaluation, in the "
        "chain's resolved direction"
    ),
    "ANY": (
        "at least one required input must match; the first match carries the "
        "chain's direction"
    ),
    "SEQUENCE": (
        "required inputs must match in ascending sequence_index order, each "
        "at or after the previous, all within the declared sequence window"
    ),
    "CONTEXT_TRIGGER": (
        "the higher-timeframe CONTEXT input must be holding at the moment the "
        "lower-timeframe TRIGGER input fires"
    ),
}


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "path",
        metavar="<file>",
        help="path to the chain document to validate and explain",
    )
    parser.add_argument(
        "--catalogue",
        dest="catalogue",
        metavar="<dir>",
        default=None,
        help=(
            "atomic strategy catalogue directory used to resolve the chain's "
            "inputs. Defaults to catalogue/atomic in the checkout, or the "
            "HSA_CATALOGUE_DIR environment variable when it is set."
        ),
    )
    parser.add_argument(
        "--no-catalogue",
        dest="no_catalogue",
        action="store_true",
        help=(
            "skip resolution of atomic references; checks the chain's internal "
            "coherence only"
        ),
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="validate only; suppress the composition explanation",
    )


# --- rendering ---------------------------------------------------------------


def _line(label: str, text: str) -> str:
    return "  %-13s %s" % (label, text)


def _describe_direction(semantics: Any) -> str:
    if not isinstance(semantics, Mapping):
        return "not declared"
    emits = semantics.get("emits")
    emitted = ", ".join(emits) if isinstance(emits, list) else "not declared"
    rule = semantics.get("direction_rule", "")
    inversion = semantics.get("inversion_allowed")
    suffix = ""
    if inversion is True:
        suffix = " Inversion is permitted."
    elif inversion is False:
        suffix = " Inversion is not permitted."
    return "emits %s. %s%s" % (emitted, rule, suffix)


def _describe_timing(timing: Any) -> str:
    if not isinstance(timing, Mapping):
        return "not declared"
    text = "evaluated on %s of the %s timeframe" % (
        timing.get("evaluation_trigger", "an undeclared trigger"),
        timing.get("evaluation_timeframe", "undeclared"),
    )
    window = timing.get("sequence_window")
    if isinstance(window, Mapping):
        text += "; the ordered steps must complete within %s bars of %s" % (
            window.get("max_bars"),
            window.get("timeframe"),
        )
    return text


def _describe_persistence(persistence: Any) -> str:
    if not isinstance(persistence, Mapping):
        return "not declared"
    if persistence.get("signal_persists") is not True:
        return "a match is asserted on its own evaluation only and does not persist"
    text = "a match stays asserted for %s bars of %s" % (
        persistence.get("persist_for_bars"),
        persistence.get("persist_timeframe"),
    )
    re_arm = persistence.get("re_arm_rule")
    if re_arm:
        text += ". Re-arm: %s" % re_arm
    return text


def _describe_expiry(expiry: Any) -> str:
    if not isinstance(expiry, Mapping):
        return "not declared"
    if expiry.get("expires") is not True:
        return "does not expire. %s" % expiry.get("expiry_rule", "")
    return "expires %s bars of %s after it is produced. %s" % (
        expiry.get("expires_after_bars"),
        expiry.get("expiry_timeframe"),
        expiry.get("expiry_rule", ""),
    )


def _describe_state(state: Any) -> str:
    if not isinstance(state, Mapping):
        return "not declared"
    if state.get("stateful") is not True:
        return "stateless; each evaluation stands alone"
    states = state.get("states")
    text = "stateful over %s, starting at %s" % (
        ", ".join(states) if isinstance(states, list) else "undeclared states",
        state.get("initial_state"),
    )
    rule = state.get("state_transition_rule")
    if rule:
        text += ". %s" % rule
    resets = state.get("reset_conditions")
    if isinstance(resets, list) and resets:
        text += " Resets on: %s" % "; ".join(resets)
    return text


def _describe_explanation(contract: Any) -> str:
    if not isinstance(contract, Mapping):
        return "not declared"
    fields = contract.get("reason_fields")
    return (
        "a reason is emitted on match and on non-match, attributed per input. "
        "Reason fields: %s" % (", ".join(fields) if isinstance(fields, list) else "none")
    )


def _describe_provenance(provenance: Any) -> str:
    if not isinstance(provenance, Mapping):
        return "not declared"
    return "%s — %s (ingested %s)" % (
        provenance.get("source_type"),
        provenance.get("source_reference"),
        provenance.get("ingested_at_utc"),
    )


def _expression(chain: Mapping) -> str:
    """One-line rendering of the composition, e.g. ``ALL(a@4H, b@5M)``."""
    inputs = chain.get("inputs")
    parts: list[str] = []
    if isinstance(inputs, list):
        ordered = [item for item in inputs if isinstance(item, Mapping)]
        if chain.get("primitive") == "SEQUENCE":
            ordered = sorted(
                ordered,
                key=lambda item: item.get("sequence_index")
                if isinstance(item.get("sequence_index"), int)
                else 0,
            )
        for item in ordered:
            rendered = "%s@%s" % (item.get("input_id"), item.get("timeframe"))
            if item.get("optional") is True:
                rendered += "?"
            parts.append(rendered)
    return "%s(%s)" % (chain.get("primitive"), ", ".join(parts))


def _explain(chain: Mapping, catalogue: Catalogue | None) -> str:
    lines: list[str] = []
    lines.append(
        "chain %s %s — %s"
        % (chain.get("chain_id"), chain.get("chain_version"), chain.get("title"))
    )
    lines.append("  %s" % chain.get("description", ""))
    lines.append("")

    primitive = chain.get("primitive")
    lines.append(_line("composition", _expression(chain)))
    lines.append(
        _line("", PRIMITIVE_SEMANTICS.get(primitive, "primitive semantics undeclared"))
    )
    lines.append("")

    lines.append("  inputs")
    inputs = [item for item in (chain.get("inputs") or []) if isinstance(item, Mapping)]
    for index, item in enumerate(inputs, start=1):
        marker = item.get("sequence_index") if primitive == "SEQUENCE" else index
        lines.append(
            "    [%s] %-18s %-12s %-5s direction %-8s %s"
            % (
                marker,
                item.get("input_id"),
                item.get("timeframe_role"),
                item.get("timeframe"),
                item.get("direction"),
                "optional" if item.get("optional") is True else "required",
            )
        )
        strategy_id = item.get("strategy_id")
        version = item.get("strategy_version")
        entry = (
            catalogue.get(strategy_id, version)
            if catalogue is not None
            and isinstance(strategy_id, str)
            and isinstance(version, str)
            else None
        )
        if entry is not None:
            lines.append(
                "         %s %s — %s" % (strategy_id, version, entry.get("title"))
            )
            emits = (entry.get("direction_semantics") or {}).get("emits")
            reason_field = (entry.get("output_contract") or {}).get("reason_field")
            lines.append(
                "         atomic emits %s; reason carried in %r"
                % (", ".join(emits) if isinstance(emits, list) else "?", reason_field)
            )
        else:
            lines.append(
                "         %s %s — not resolved (catalogue lookup was skipped)"
                % (strategy_id, version)
            )
    lines.append("")

    roles = chain.get("timeframe_roles")
    if isinstance(roles, Mapping):
        lines.append(
            _line(
                "role model",
                ", ".join("%s -> %s" % pair for pair in sorted(roles.items()))
                + " (roles are canonical; the timeframes are this chain's choice)",
            )
        )
    lines.append(_line("direction", _describe_direction(chain.get("direction_semantics"))))
    lines.append(_line("timing", _describe_timing(chain.get("timing"))))
    lines.append(_line("state", _describe_state(chain.get("state_semantics"))))
    lines.append(_line("persistence", _describe_persistence(chain.get("persistence"))))
    lines.append(_line("expiry", _describe_expiry(chain.get("expiry"))))
    lines.append(
        _line("explanation", _describe_explanation(chain.get("explanation_contract")))
    )
    lines.append(_line("instruments", ", ".join(chain.get("instruments") or [])))
    lines.append(_line("provenance", _describe_provenance(chain.get("provenance"))))
    return "\n".join(lines)


# --- entry point -------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    document = read_json_file(args.path)

    kind = detect_kind(document)
    if kind != "chain":
        raise ContractError(
            "hsa chain expects a chain document but %s declares kind %r; use "
            "hsa validate for other contract kinds" % (args.path, kind)
        )

    validate_document(document, kind="chain", source=args.path)

    catalogue = None
    if not args.no_catalogue:
        catalogue = Catalogue.from_directory(args.catalogue)

    findings = check_chain(document, catalogue=catalogue)
    raise_if_invalid(findings, "chain", source=args.path)

    if args.quiet:
        return 0

    resolution = (
        "catalogue resolution skipped"
        if catalogue is None
        else "%d inputs resolved against %s" % (len(document.get("inputs") or []), catalogue.source)
    )
    print("%s: valid chain, structurally and semantically (%s)" % (args.path, resolution))
    print()
    print(_explain(document, catalogue))
    return 0
