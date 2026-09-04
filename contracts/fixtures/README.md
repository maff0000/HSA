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
| `strategy_hypothesis.json` | `STRATEGY_HYPOTHESIS` | `INFORMATIONAL` | The economic claim being tested. |
| `research_finding_run.json` | `RESEARCH_FINDING` | `INFORMATIONAL` | A run that produced evidence — the one fixture carrying the full identity chain `experiment_id` → `run_id` → `evidence_id` → `artifact_id`. |
| `promotion_evidence.json` | `PROMOTION_EVIDENCE` | `PROMOTION` | Evidence offered in support of promoting `gold_context_breakout` 1.0.0. |
| `version_lineage_promoted.json` | `VERSION_LINEAGE` | `INFORMATIONAL` | Lineage anchor for the original promoted version, 1.0.0. |
| `version_lineage_candidate.json` | `VERSION_LINEAGE` | `INFORMATIONAL` | Lineage anchor for candidate 1.1.0, which supersedes 1.0.0. |
| `revision_evidence_candidate.json` | `REVISION_EVIDENCE` | `REVISION` | Evidence for the 1.1.0 candidate — anchored to 1.1.0, not 1.0.0, because a candidate inherits no verdict from the version it supersedes (PID line 189). |
| `rejection_evidence.json` | `REJECTION_EVIDENCE` | `REJECTION` | Evidence supporting rejection of `wick_rejection_sequence` 0.1.0. Rejection is a governed outcome on the record, not a deleted experiment. |

Two strategies appear, deliberately: `gold_context_breakout` across two
versions (so lineage is actually lineage), and `wick_rejection_sequence`,
which was rejected.

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
