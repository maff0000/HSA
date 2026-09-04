# Contract fixtures

> **PID line 181** — *If CER is not yet live, HSA may use contract
> fixtures/mocks, but must not create an incompatible permanent evidence
> store.*

**CER is not live. Everything under `cer/` is a fixture. None of it is
evidence.**

These documents exist to prove the *shape* of the CER contract while the
system that would supply the real thing does not yet exist. They prove that
HSA can produce and consume every evidence shape the PID requires. They prove
nothing whatsoever about any trading strategy.

## What this directory is not

It is not an evidence store, and it must never become one. A CER datastore is
an explicit non-goal (PID line 269), and the realistic way that non-goal gets
violated is not by someone deciding to build a database — it is by "just a
little local evidence storage" accreting here until HSA has a second source
of evidence truth that CER can never absorb.

So:

* **Nothing writes here.** `hsa/cer.py` has no write path; `hsa cer` is a
  read-only command. `tests/test_cer.py::test_reading_evidence_writes_nothing`
  asserts the directory is byte-identical across a full read/validate/build
  cycle.
* **This is not a growing record.** One document per evidence shape, chosen
  to cover the contract. Runs, results and findings do not accumulate here.
* **Fixtures are replaced, never migrated.** There is no "import the fixtures
  into CER" step and there must never be one. That step is exactly what
  *incompatible permanent evidence store* means.

## How a fixture is labelled

Two independent signals, so a fixture cannot be mistaken for live evidence
even when read out of context:

1. **`"source": "CONTRACT_FIXTURE"`.** Required by
   `contracts/cer_reference.schema.json`, whose only other legal value is
   `CER_LIVE`. There is no default and no third state — a reference that does
   not declare which it is fails validation. The `FixtureEvidenceReader`
   additionally refuses to load any document in this directory that claims to
   be `CER_LIVE`.
2. **`FIXTURE-` prefixed identities.** Every CER-minted identity —
   `experiment_id`, `run_id`, `evidence_id`, `artifact_id` — is prefixed
   `FIXTURE-`. Real CER identities are minted by CER and will not look like
   this.

```bash
grep -rl CONTRACT_FIXTURE contracts/ strategies/ tests/   # find every stand-in
hsa cer validate                                          # contract + label check
```

## The fixture set (`cer/`)

Covering all seven canonical `reference_type` values (PID lines 175-179) and
all four `supports` values.

| File | `reference_type` | `supports` | What it represents |
| --- | --- | --- | --- |
| `source_analysis.json` | `SOURCE_ANALYSIS` | `INFORMATIONAL` | Analysis of the raw source behind a strategy: which claims were measurable, which were discretionary language. |
| `strategy_hypothesis.json` | `STRATEGY_HYPOTHESIS` | `INFORMATIONAL` | The economic claim a strategy stakes. Stated, not shown. |
| `research_finding_run.json` | `RESEARCH_FINDING` | `INFORMATIONAL` | The shape of a finding from a run — the one fixture carrying the full identity chain `experiment_id` → `run_id` → `evidence_id` → `artifact_id`. No run has been executed. |
| `promotion_evidence.json` | `PROMOTION_EVIDENCE` | `PROMOTION` | The shape of evidence offered in support of promoting `gold_context_breakout` 1.0.0. No gate has been evaluated; 1.0.0 is a `CANDIDATE`. |
| `version_lineage_original.json` | `VERSION_LINEAGE` | `INFORMATIONAL` | Lineage anchor for the original version, 1.0.0, which supersedes nothing. A lineage anchor says nothing about lifecycle status. |
| `version_lineage_candidate.json` | `VERSION_LINEAGE` | `INFORMATIONAL` | The shape of a lineage anchor for a candidate 1.1.0 superseding 1.0.0. No 1.1.0 exists in `strategies/`. |
| `revision_evidence_candidate.json` | `REVISION_EVIDENCE` | `REVISION` | The shape of evidence for a 1.1.0 candidate — anchored to 1.1.0, not 1.0.0, because a candidate inherits no verdict from the version it supersedes (PID line 189). |
| `rejection_evidence.json` | `REJECTION_EVIDENCE` | `REJECTION` | The shape of evidence supporting rejection of `wick_rejection_sequence` 0.1.0. Rejection is a governed outcome on the record, not a deleted experiment. No criterion has been evaluated; 0.1.0 is a `CANDIDATE`. |

Two strategies appear, deliberately: `gold_context_breakout` across two
versions (so a lineage fixture is actually a lineage), and
`wick_rejection_sequence`, so that a rejection shape is covered as well as a
promotion shape.

## What these fixtures do NOT assert

Every fixture describes a **shape**. None of them is a verdict, and none of
them is a claim about the strategy it names.

* **No promotion has occurred.** `promotion_evidence.json` shows what
  promotion evidence would look like. `gold_context_breakout` 1.0.0 is
  `CANDIDATE`, and `docs/VERSIONING.md` makes promotion an evidence-gated
  act that has never been performed.
* **No rejection has occurred.** `rejection_evidence.json` is the same kind
  of shape. `wick_rejection_sequence` 0.1.0 is `CANDIDATE` too.
* **No run has been executed.** The identity chain in
  `research_finding_run.json` is a chain of `FIXTURE-` identities that
  resolve nowhere.
* **The 1.1.0 candidate does not exist.** The two fixtures anchored to
  `gold_context_breakout` 1.1.0 exist so the lineage and revision shapes are
  covered. There is no `strategies/gold_context_breakout/1.1.0/`, and
  `hsa.versioning.derive_candidate` will not produce one while 1.0.0 is a
  `CANDIDATE` — a version that was never promoted is not frozen, so it is
  edited directly rather than superseded (`docs/VERSIONING.md` §3).

These fixtures were reworded to say so. An earlier wording asserted that
1.0.0's "acceptance criteria were met" and called it "the original promoted
version"; both stated a promotion that never happened, and neither is
something this repository can stand behind.

## When CER goes live

The seam is `hsa.cer.open_evidence_reader()`. Replace the reader, replace or
delete every `CONTRACT_FIXTURE` reference, and delete this directory or keep
it as test data. Nothing here is carried forward as data.

The full procedure is in `docs/CER-CONTRACT.md` §5.

## Overriding the location

`HSA_CER_FIXTURES_DIR` points the reader at a different directory. Supplied
externally; no location is baked into source beyond the repository-relative
default (PID line 224). Fails loudly when the directory is missing.

## Related

* `docs/CER-CONTRACT.md` — how HSA uses CER, and what a session may assume.
* `contracts/cer_reference.schema.json` — the frozen contract.
* `tests/fixtures/` — W1's per-kind valid/invalid contract samples. Different
  purpose: those exercise the validator, these stand in for a live system.
