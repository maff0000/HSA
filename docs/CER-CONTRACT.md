# The CER contract

How HSA uses CER (PID lines 160-181). This is one of the documents a fresh
HSA boot must load (PID line 215), and it is the durable answer to a single
question: **what may an HSA session assume about evidence?**

The short answer, before any detail: HSA does not own evidence. CER does.
HSA names evidence, points at it, and states in advance what evidence a
strategy needs. It never stores evidence, never judges it, and — while CER
is not live — has never actually checked any of it against reality.

---

## 1. The authority boundary

| | HSA | CER |
| --- | --- | --- |
| Owns the strategy specification | yes | no |
| Owns evidence and its storage | no | yes |
| Mints `strategy_id` / `strategy_version` | yes | no |
| Mints `experiment_id` / `run_id` / `evidence_id` / `artifact_id` | no | yes |
| States what evidence is required, before it exists | yes | no |
| States whether the evidence was met | no | yes |

HSA must not bypass CER (PID line 37) and must consume evidence from CER
(PID line 29). The four CER-minted identities are **opaque to HSA**: HSA
carries them verbatim and never parses, interprets, derives or invents them.

**Where the PID is silent about CER's internals, that silence is CER's
authority, not an invitation.** The PID gives HSA an identity set and a list
of things to record or target. It says nothing about how CER stores
evidence, how a run is executed, what a run emits, how evidence is queried,
or what makes evidence sufficient. HSA therefore says nothing about those
things either. Anywhere this repository would have had to invent CER
semantics to proceed, it stopped instead — see §6.

---

## 2. The canonical identities (PID lines 166-171)

| Identity | Minted by | What it means to HSA |
| --- | --- | --- |
| `strategy_id` | HSA | The stable canonical identity of a strategy. Shared verbatim with CER. Never reused for a different strategy and **never changed across versions** — it is what makes a lineage a lineage. |
| `strategy_version` | HSA | Strict `MAJOR.MINOR.PATCH`. Identifies one immutable specification. Every evidence reference is anchored to a specific version, because evidence gathered against one version says nothing about another (see `docs/VERSIONING.md`). |
| `experiment_id` | CER | The investigation a reference belongs to. Opaque. |
| `run_id` | CER | One execution within an experiment. Opaque. |
| `evidence_id` | CER | One piece of evidence produced. Opaque. This is the identity `hsa cer show` resolves. |
| `artifact_id` | CER | One stored artefact backing that evidence. Opaque. |

**Identity is always id plus version.** Neither half alone identifies
anything governable, and the frozen `cer_reference` contract requires both
in every reference (acceptance criterion 10, PID line 259).

A reference must also carry **at least one** of the four CER identities. A
document that names a strategy but no evidence is not a reference at all,
and the schema rejects it.

---

## 3. What HSA records and targets through CER contracts

PID lines 173-179 list five things. They map onto the canonical
`reference_type` values in `contracts/common.defs.json`:

| PID line | `reference_type` | What HSA is saying |
| --- | --- | --- |
| 175 source analysis | `SOURCE_ANALYSIS` | What the raw source claimed, which parts were measurable, which were discretionary language that had to be resolved or refused. |
| 176 strategy hypotheses | `STRATEGY_HYPOTHESIS` | The economic claim being tested. A hypothesis structure to be empirically validated, not doctrine that guarantees edge. |
| 177 strategy-version lineage | `VERSION_LINEAGE` | An anchor for one version in a strategy's lineage. The version it supersedes is named in the package's `lifecycle.supersedes`, **not** in the reference — the reference carries CER identities, and CER identities are opaque. |
| 178 research findings | `RESEARCH_FINDING` | Something learned that is not itself a verdict. Findings may come from NEO (PID line 200); they are still evidence HSA governs, never a licence to rewrite anything. |
| 179 evidence supporting promotion / revision / rejection | `PROMOTION_EVIDENCE`, `REVISION_EVIDENCE`, `REJECTION_EVIDENCE` | Evidence offered in support of a governed decision about one specific version. |

The separate `supports` field records which decision a reference is offered
in support of: `PROMOTION`, `REVISION`, `REJECTION`, `INFORMATIONAL`.
`reference_type` says what kind of thing the evidence is; `supports` says
what it is being used to argue.

**Rejection is a governed outcome on the record, not a deleted experiment.**
A `REJECTION_EVIDENCE` reference is as much a deliverable as a promotion.

### Evidence requirements are stated before evidence exists

A strategy package's `evidence_requirements` block declares
`required_cer_evidence_types`, `backtest_requirements` and a
`minimum_sample_size` **before** any run happens. That ordering is the point:
thresholds that are written after seeing a result are not thresholds. The
`minimum_sample_size` guard exists so edge is never declared from a handful
of occurrences (PID line 198, avoid overfitting).

---

## 4. The reference document

The frozen contract is `contracts/cer_reference.schema.json`. A reference
looks like this:

```json
{
  "$hsa_kind": "cer_reference",
  "$hsa_contract_version": "1.0.0",
  "strategy_id": "gold_context_breakout",
  "strategy_version": "1.0.0",
  "experiment_id": "FIXTURE-EXP-GOLD-0001",
  "run_id": "FIXTURE-RUN-GOLD-0001-A",
  "evidence_id": "FIXTURE-EVID-GOLD-0001-PROMO",
  "artifact_id": "FIXTURE-ART-GOLD-0001-PROMO-report",
  "reference_type": "PROMOTION_EVIDENCE",
  "source": "CONTRACT_FIXTURE",
  "summary": "Evidence offered in support of promoting gold_context_breakout 1.0.0.",
  "recorded_at_utc": "2026-09-02T16:20:00Z",
  "supports": "PROMOTION"
}
```

`summary` is a convenience for human review only. **CER remains the
authority**; a summary in an HSA document is never evidence and is never
grounds for a decision.

`recorded_at_utc` is when CER recorded the evidence, in UTC with a literal
trailing `Z` (PID line 225). HSA does not get to invent it, which is why
`hsa.cer.build_reference()` requires it rather than defaulting to "now".

Strategy packages embed their references in a `cer_references` array, which
always has at least one entry: a package has at least a source-analysis or
hypothesis reference even before any run exists.

---

## 5. The fixture stand-in

> **PID line 181** — *If CER is not yet live, HSA may use contract
> fixtures/mocks, but must not create an incompatible permanent evidence
> store.*

**CER is not live. Everything in `contracts/fixtures/cer/` is a fixture.**

### What is fixture today

* Every document in `contracts/fixtures/cer/`. All eight declare
  `"source": "CONTRACT_FIXTURE"`, and every CER-minted identity in them is
  prefixed `FIXTURE-` so it cannot pass for a real identity even when read
  out of context.
* The CER references embedded in `tests/fixtures/valid/strategy_package.json`
  and in any example package in this repository.
* Therefore: **no evidence claim anywhere in this repository has been
  checked against reality.** The fixtures prove the contract shapes are
  right. They prove nothing about any strategy.

### Why the `source` field exists

W1's `cer_reference` schema requires `source`, valued `CER_LIVE` or
`CONTRACT_FIXTURE`, precisely so this distinction is **declared in the
document rather than inferred from context**. There is no third state and no
default. A reference that does not say which it is fails validation.

That is what makes fixture-backed references mechanically findable when CER
goes live:

```bash
grep -rl CONTRACT_FIXTURE contracts/ strategies/ tests/
hsa cer list                     # prints the source on every listing
```

### What must change when CER goes live

The seam is one function: **`hsa.cer.open_evidence_reader()`**. It returns
an `EvidenceReader` — three read methods, `references()`,
`references_for()`, `reference()`. Today it always returns a
`FixtureEvidenceReader` backed by `contracts/fixtures/cer/`.

The whole migration is:

1. Add a `LiveCerEvidenceReader` implementing those same three methods.
2. Have `open_evidence_reader()` return it when CER connection details are
   supplied externally, as environment or runtime configuration — **never in
   source** (PID line 224).
3. References it returns declare `source: CER_LIVE`.
4. Re-anchor real references: every existing `CONTRACT_FIXTURE` reference is
   **replaced** with a real one, or **deleted**. A fixture identity is never
   rewritten into a live one, because the fixture never pointed at anything.
5. Delete `contracts/fixtures/cer/`, or keep it as test data only.

No caller changes, because callers only ever see `EvidenceReader`.

### Why none of this is a permanent evidence store

This is the failure mode the PID names as an explicit non-goal (line 269, do
not build a CER datastore), and it is an easy one to walk into: "just a
little local evidence storage" quietly becomes a second source of evidence
truth that CER can never absorb.

The guarantees that stop it:

* **`hsa/cer.py` has no write path.** No database, no append-only log, no
  index file, no cache written to disk. It reads fixture files and validates
  documents against the frozen contract. That is the whole job.
  `tests/test_cer.py::test_reading_evidence_writes_nothing` hashes the
  fixture directory across a full read/validate/build cycle and asserts it is
  unchanged, and asserts the adapter created no files of its own.
* **`hsa cer` never writes.** It is a read-only window.
* **The fixtures are contract proof, not data.** They are one document per
  evidence shape, chosen to cover the contract, not a growing record of
  results. Nothing appends to them at runtime.
* **Fixtures are replaced, never migrated.** There is no "import fixtures
  into CER" step and there must never be one — that step is exactly what
  "incompatible permanent evidence store" means.

The durable statement of intent: if a future change adds a write to
`hsa/cer.py`, that change is building the thing the PID forbids.

---

## 6. What a fresh HSA session may and may not assume

**May assume:**

* The canonical identity set is `strategy_id`, `strategy_version`,
  `experiment_id`, `run_id`, `evidence_id`, `artifact_id`, and HSA mints only
  the first two.
* Every evidence reference in this repository is contract-valid and anchored
  to a specific strategy version.
* Every reference declares its `source` explicitly, so what is fixture and
  what is live is always knowable without asking anyone.
* The canonical `reference_type` and `supports` vocabularies are fixed by
  `contracts/common.defs.json`.

**Must NOT assume:**

* That any evidence claim is true. CER is not live; nothing has been checked.
* That a `PROMOTION_EVIDENCE` fixture means a strategy was promoted on
  evidence. It means the reference shape is correct.
* That evidence anchored to one version says anything about another version.
  It does not, ever — that is the whole basis of `docs/VERSIONING.md`.
* That HSA can query CER, run an experiment, or produce evidence. It cannot.
  HSA states requirements and reads references.
* Anything about CER's internal storage, query model, run execution or
  sufficiency rules. The PID is silent, so HSA is silent.

**Must NOT do:**

* Write evidence anywhere in this repository.
* Add a local store, cache or index of evidence "for convenience".
* Relabel a `CONTRACT_FIXTURE` reference as `CER_LIVE` without a real CER
  behind it.
* Invent a CER identity. If a needed identity does not exist yet, the
  reference does not exist yet either.

---

## 7. Using it

```bash
hsa cer list                                    # every reference, with its source
hsa cer list --strategy gold_context_breakout   # one strategy's evidence
hsa cer list --supports PROMOTION               # by the decision it argues for
hsa cer list --type VERSION_LINEAGE             # by reference type
hsa cer show FIXTURE-EVID-GOLD-0001-PROMO       # one reference in full
hsa cer validate                                # every fixture, contract + label
hsa cer validate path/to/reference.json         # named documents
hsa cer lineage pkg-1.0.0.json pkg-1.1.0.json   # lineage plus per-version evidence
```

Exit codes come from `hsa/cli.py`: `0` valid, `1` a document failed contract
validation, `2` usage, `3` any other deliberate HSA error.

From Python:

```python
from hsa.cer import open_evidence_reader, build_reference

reader = open_evidence_reader()            # THE SEAM
reader.source                              # "CONTRACT_FIXTURE" today
references = reader.references_for("gold_context_breakout", "1.0.0")
```

`hsa.cer` also exposes `validate_reference()`, `is_fixture()`,
`reference_types()` (read from the frozen contract, never restated) and
`group_by_reference_type()`.

---

## Related

* `contracts/cer_reference.schema.json` — the frozen contract.
* `contracts/fixtures/README.md` — what the fixture set is and is not.
* `docs/VERSIONING.md` — why every reference is anchored to one immutable
  version, and what a candidate may and may not inherit.
