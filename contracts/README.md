# HSA contracts

The frozen interface for HSA v1. Everything else in this repository — and
every work item built after this one — codes against the schemas in this
directory. They are JSON Schema **Draft 2020-12** and are validated offline;
nothing here is ever fetched over the network.

## The contract set

| Kind (`$hsa_kind`)         | File                                    | What it is |
| -------------------------- | --------------------------------------- | ---------- |
| `atomic_strategy`          | `atomic_strategy.schema.json`           | One small, self-contained, deterministic, execution-blind strategy driven by HERMES facts (PID lines 43-55). |
| `chain`                    | `chain.schema.json`                     | A composition of atomic strategies using the canonical primitives `ALL`, `ANY`, `SEQUENCE`, `CONTEXT_TRIGGER` (PID lines 57-82). |
| `strategy_package`         | `strategy_package.schema.json`          | The governed deliverable FORGE implements inside HELIOS (PID lines 122-148). |
| `cer_reference`            | `cer_reference.schema.json`             | CER canonical identities and evidence semantics (PID lines 160-181). |
| `not_sufficiently_defined` | `not_sufficiently_defined.schema.json`  | The structured `STRATEGY_NOT_SUFFICIENTLY_DEFINED` refusal (PID line 120). |

`common.defs.json` is **not** a document kind. It holds the shared building
blocks — identity patterns, UTC timestamps, timeframes, provenance,
parameters, output contracts, criteria — so each shape has exactly one
definition. No document ever validates against it directly.

## The discriminator

Every HSA document declares its own contract in a `$hsa_kind` property whose
value is one of the kinds above, and which each schema pins with a `const`.
That is what lets tooling route a document without out-of-band knowledge:

```json
{ "$hsa_kind": "atomic_strategy", "strategy_id": "golden_cross", "...": "..." }
```

An optional `$hsa_contract_version` records which version of this contract
set a document was authored against.

## Using them

```bash
hsa validate path/to/document.json                     # kind auto-detected
hsa validate path/to/document.json --schema chain      # kind forced
```

Exit codes: `0` valid, `1` invalid (the failing JSON path is printed), `2`
usage error, `3` any other error such as an unreadable file.

From Python, always go through `hsa.contracts` rather than loading these
files yourself — it handles cross-file `$ref` resolution:

```python
from hsa.contracts import KINDS, load_schema, detect_kind, validate_document

kind = validate_document(document)          # raises DocumentInvalidError
```

## Two prohibitions, and where each is really enforced

One of the two is enforced by the shape of the schema. The other is not, and
is enforced by a test instead. The distinction matters: a reader who believes
the schema rejects both will trust `hsa validate` to catch something it does
not catch.

**An atomic strategy cannot reference another strategy — enforced by a test,
not by the schema.** PID lines 52 and 59 say atomic strategies are unaware of
other strategies and never call or import them. `atomic_strategy.schema.json`
provides no property through which a peer could be named — no `depends_on`,
no `components`, no `inputs` — and sets `additionalProperties: false`, so
inventing a top-level property is rejected. That is real, but it is not the
whole prohibition. Each `deterministic_test_cases` item carries three
deliberately open objects — `given_hermes_facts`, `given_parameters` and
`expected_output`, all declared `{"type": "object"}` with no constraint on
their keys — and a peer `strategy_id` planted inside any of the three
validates clean: `validate_document()` returns `atomic_strategy` and
`hsa validate --structural-only` exits 0.

What actually enforces the prohibition is
`tests/test_catalogue.py::test_entry_references_no_other_strategy`, which
walks every node of every catalogue entry and fails on any `strategy_id`
that is not the entry's own. The walk is complete by construction — it does
not care which key the reference hides under — and it is itself checked for
non-vacuity by planting a reference and requiring the walk to find it. The
packages embed catalogue entries verbatim, so that walk covers what ships.
Composition happens exclusively in a chain, from the outside.

**A chain cannot contain another chain.** PID line 82 says prefer atomic
inputs and do not create recursive chain-of-chain complexity in v1. A chain
is flat by construction: one `primitive` and an `inputs` array whose items
are atomic strategy references only. There is no reusable node definition
and no self-`$ref`, so neither a nested composition node nor a reference to
another chain document can be expressed. An expression such as
`ALL(context, ANY(trigger_a, trigger_b))` must be split into separately
governed chains. Relaxing this later is additive and would not invalidate
documents written today.

## Other invariants worth knowing before you write a document

- **Identity is always id plus version.** Chain inputs pin
  `strategy_id` *and* `strategy_version` (PID line 72). Versions are strict
  semver, and promoted versions are immutable (PID lines 185-189).
- **UTC only.** Every timestamp field must end in a literal `Z`
  (PID line 225).
- **Timeframes** are written like `5M`, `15M`, `1H`, `4H`, `1D`, where `M`
  means *minutes* (PID line 95 writes `1H/15M/5M/1M`). There is no month
  suffix, so `M` is never ambiguous. The semantic *roles* — `CONTEXT`,
  `LOCATION`, `CONFIRMATION`, `TRIGGER` — are canonical; the timeframes they
  map to are a per-strategy choice (PID lines 84-97).
- **No discretionary language.** A parameter must carry a default, units and
  either an `allowed_range` or an `allowed_values` list. Phrases like *large
  wick* or *near resistance* cannot be encoded as prose; they either become
  bounded parameters or the intake returns a `not_sufficiently_defined`
  result (PID lines 110-120).
- **Chains must explain themselves.** `explanation_contract` requires a
  reason on match *and* on non-match, attributed per input (PID line 80).
- **A strategy package is self-contained.** It embeds full atomic strategy
  and chain definitions rather than referencing them by id, because FORGE
  must implement from the one document.

## Changing a contract

These schemas are the interface several work items build against
simultaneously. Additive, backward-compatible changes (a new optional
property, a relaxed constraint) are ordinary work. Anything that would
invalidate an existing document — a new required property, a narrowed enum,
a new kind — is a contract change: raise it with the PL rather than editing
in place.

Sample documents for every kind, valid and deliberately invalid, live in
`tests/fixtures/`. Reuse them instead of hand-rolling documents.
