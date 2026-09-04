# Strategy inventory

Governed HSA strategy packages, one directory per strategy, one directory per
version. This is the *current strategy inventory / version state* a fresh HSA
boot loads (`PID.md:216`).

A package in here is the deliverable FORGE consumes to implement inside
HELIOS. It carries enough precision that FORGE implements the specification
rather than inventing trading logic (`PID.md:148`).

---

## Layout

```
strategies/<strategy_id>/<strategy_version>/package.json    the governed strategy_package
strategies/<strategy_id>/<strategy_version>/source.txt      the raw description it came from
strategies/<strategy_id>/<strategy_version>/evidence.json   its CER references
```

| File | What it is |
| ---- | ---------- |
| `package.json` | A full `strategy_package` document, valid against [`contracts/strategy_package.schema.json`](../contracts/strategy_package.schema.json) **and** clean under `hsa.semantics.check_package`. Self-contained: the atomic strategy definitions and the chain are embedded in full, not referenced by id, so FORGE implements from this one document. |
| `source.txt` | The raw strategy description exactly as it arrived, before HSA touched it. Provenance points at this path (`PID.md:145`). |
| `evidence.json` | The CER references anchored to this version. |

The directory names are not decoration: `<strategy_id>` and
`<strategy_version>` **must** equal the `strategy_id` and `strategy_version`
inside `package.json`. A package filed under a path that contradicts its own
identity is unfindable by the identity CER records evidence against.

`strategy_version` is strict `MAJOR.MINOR.PATCH`. `strategy_id` matches
`^[a-z][a-z0-9_]{2,63}$` and is never reused for a different strategy, nor
changed across versions.

### `evidence.json` is a convention, not a contract

It is an inventory-local index and deliberately carries **no `$hsa_kind`**, so
no tool routes it to a schema it was never meant to satisfy. Its shape:

```json
{
  "document_type": "hsa_strategy_evidence_index",
  "strategy_id": "...",
  "strategy_version": "...",
  "cer_status": "NOT_LIVE",
  "references": [ { "$hsa_kind": "cer_reference", "...": "..." } ]
}
```

Every entry in `references[]` **is** a full `cer_reference` document and
validates against the frozen contract on its own.

This file is an index, not a store. CER owns evidence; HSA points at it
(`PID.md:160-181`). While CER is not live every reference declares
`"source": "CONTRACT_FIXTURE"` and carries `FIXTURE-` prefixed identities, so
a stand-in cannot be mistaken for live evidence. When CER goes live these are
**replaced at the `hsa.cer.open_evidence_reader()` seam and never migrated**;
a growing local record here is exactly the incompatible permanent evidence
store `PID.md:181` forbids.

---

## Promoted versions are immutable

> **`PID.md:185-189`** — *Promoted strategy versions are immutable. Do not
> tweak a live strategy in place. A proposed modification creates a separately
> versioned candidate and must pass governed evidence gates again.*

**A change is a new version directory. Never an edit.**

To revise a strategy, copy the version directory to a new
`<strategy_version>`, change what needs changing there, and set
`lifecycle.supersedes` on the new package to name the version it proposes to
replace and why. The superseded directory stays exactly as it was.

The reason is evidence attribution. CER records evidence against
`strategy_id` **and** `strategy_version` together. Editing a promoted package
in place silently re-points every piece of evidence ever gathered at a
specification that is no longer the one that was tested — and nothing in the
record would show it happened.

`hsa/versioning.py` enforces this: an in-place modification of a `PROMOTED`
version raises `PromotedVersionImmutableError`, and the error names the exact
JSON paths that were going to be edited.

A candidate inherits no verdict from the version it supersedes. It re-earns
promotion through its own evidence gates.

### Lifecycle status

| Status | Meaning |
| ------ | ------- |
| `CANDIDATE` | Proposed. No evidence gate has been passed. |
| `PROMOTED` | Passed its gates. **Immutable from this point.** |
| `DORMANT` | Promoted, and currently outside the market shape it was proven in. A normal resting state, **not a failure** (`PID.md:195`). |
| `RETIRED` | Withdrawn. Kept on the record; rejection is a governed outcome, not a deleted experiment. |

Dormancy is not a reason to tune. Do not tune a strategy merely to restore
trade frequency (`PID.md:197`), and do not force one to trade outside its
preferred market shape (`PID.md:194`). Prefer many independently proven
specialists over one strategy stretched to cover everything.

---

## The inventory

| Strategy | Version | Status | Primitive | Roles | What it is |
| -------- | ------- | ------ | --------- | ----- | ---------- |
| [`gold_context_breakout`](gold_context_breakout/1.0.0/) | `1.0.0` | `CANDIDATE` | `CONTEXT_TRIGGER` | CONTEXT→4H, TRIGGER→5M | **PID acceptance Example A** (`PID.md:234-236`): a 4H moving-average cross context gating a 5M range breakout on XAUUSD. |

**These are product proofs, not claims of profitable strategies**
(`PID.md:244`). No package in this inventory has passed a real evidence gate,
because CER is not live. Every threshold is either an architect-set catalogue
default or a value taken verbatim from the source description, and all of them
are declared, bounded and revisable under evidence.

---

## Checking a package

```bash
python3 -m hsa.cli validate strategies/<id>/<version>/package.json
```

That is the **structural** half only — `hsa validate` checks the document
against its frozen schema and stops there.

The **semantic** half is the cross-field rules JSON Schema cannot express: that
the package and its embedded chain say the same thing, that a `CONTEXT` input
genuinely sits above its `TRIGGER`, that every atomic the chain names resolves
in the catalogue at the exact version pinned, and that package-level HERMES
fields cover what the atomics consume. As of this writing **no CLI command
runs those checks over a `strategy_package`** — `hsa chain` runs them, but it
accepts a `chain` document and rejects any other kind. Until a command covers
it, the semantic half runs from Python:

```python
import json
from hsa.semantics import Catalogue, check_package

package = json.load(open("strategies/<id>/<version>/package.json"))
findings = check_package(package, catalogue=Catalogue.from_directory())
assert findings == []
```

`tests/test_acceptance_example_a.py` runs both halves over Example A on every
test run, so a package that drifts from its catalogue entries fails the suite.

Evidence and lineage:

```bash
python3 -m hsa.cli cer lineage strategies/<id>/<version>/package.json
python3 -m hsa.cli cer list --strategy <id> --strategy-version <version>
```

---

## Related

- [`PID.md`](../PID.md) — the authoritative scope.
- [`contracts/strategy_package.schema.json`](../contracts/strategy_package.schema.json) — the frozen package contract.
- [`docs/COMPOSITION-DOCTRINE.md`](../docs/COMPOSITION-DOCTRINE.md) — how chains compose atomic outputs.
- [`docs/VERSIONING.md`](../docs/VERSIONING.md) — versioning, lineage and promotion in full.
- [`docs/CER-CONTRACT.md`](../docs/CER-CONTRACT.md) — how HSA targets CER.
- [`catalogue/README.md`](../catalogue/README.md) — the atomic strategies a package composes.
