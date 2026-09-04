# HSA v1 — acceptance evidence and PL adjudication record

Presentation target: **`FUNCTIONAL_ONLY`** (`PID.md:11`). The PID's explicit
non-goals include dashboards/UI (`PID.md:275`), so there is no browser surface
and no browser-verification gate applies. Evidence here is mechanical.

Full suite at the time of writing: **753 passed**. `hsa boot` reports
`16 artifacts declared: 16 loaded, 0 required missing, 0 optional absent`.

## Acceptance criteria (`PID.md:246-262`)

| # | Criterion | Where it is proven |
|---|---|---|
| 1 | load durable doctrine without Matt re-explaining it | `hsa boot` (exit 0, 16/16); `docs/boot-manifest.json`; `tests/test_boot.py` (49) |
| 2 | ingest a realistic raw strategy description | `strategies/*/*/source.txt` driven through `hsa intake`; `tests/test_intake.py` (30) |
| 3 | identify ambiguity rather than guessing | `docs/AMBIGUITY-POLICY.md`; `tests/test_ambiguity.py` (28). Both directions proven — Example A's first-pass source was **refused** (exit 4) for "strong trend"/"clean breakout"; Example B's terms were **parameterised** with `hsa_guessed: false` |
| 4 | decompose into independent atomic strategies | `catalogue/atomic/` (11 entries); `tests/test_catalogue.py` (149). Atomics cannot reference peers — structurally impossible in `contracts/atomic_strategy.schema.json` |
| 5 | construct an explicit chain using canonical primitives | Example A `CONTEXT_TRIGGER`, Example B `SEQUENCE`; `tests/test_semantics.py` (85) |
| 6 | assign semantic timeframe roles | both packages' `timeframe_roles`; roles are assignments, not universal timeframes (`PID.md:93`) |
| 7 | define timing/direction/persistence/expiry | both packages; `package.chain_agreement` enforces package and embedded chain agree |
| 8 | map required inputs to HERMES | `required_hermes_fields` per atomic; `package.hermes_coverage` |
| 9 | produce a coherent deterministic HELIOS package | `hsa validate` runs structural **and** semantic by default; `tests/test_semantic_cli.py` (27) |
| 10 | preserve strategy/version identity | id+version pinned everywhere including directory paths; embedded atomics byte-identical to catalogue entries |
| 11 | define tests and evidence requirements | `deterministic_test_cases` and evidence requirements in both packages |
| 12 | use/target CER semantics | `docs/CER-CONTRACT.md`; 8 fixtures; `tests/test_cer.py` (58), `tests/test_cer_evidence_container.py` (20) |
| 13 | separately versioned candidate, never mutate a promoted strategy | `tests/test_versioning.py` (57), `tests/test_criterion_13_inventory.py` (12). **See the adjudication below** |

## Acceptance examples (`PID.md:230-244`)

- **Example A** — `strategies/gold_context_breakout/1.0.0/`, `CONTEXT_TRIGGER`
  (4H golden cross context gating a 5M range breakout).
- **Example B** — `strategies/wick_rejection_sequence/0.1.0/`, `SEQUENCE`
  (rejection wick → no-wick confirmation → optional trigger).

Both are product proofs, not claims of profitable strategies (`PID.md:244`).

## PL adjudication record

Three genuine contradictions inside the PID surfaced during delivery. Each was
resolved without changing the PID, and each is recorded here so an Auditor can
challenge the reasoning rather than reverse-engineer it.

### 1. "large wick" — must never be guessed, yet Example B is built on it

`PID.md:117` lists "large wick" among phrases that must not be guessed;
`PID.md:242` builds Example B on one and `PID.md:288` requires the examples to
pass. Resolved by `PID.md:110` + `PID.md:120`: **parameterise** where the
measurement basis is known and only the threshold is unset; **refuse** where
the basis is itself undefined. Of the PID's five examples, two parameterise and
four refuse, so criterion 3 stays testable and Example B stays reachable.
Durable statement: `docs/AMBIGUITY-POLICY.md`.

### 2. Immutability vs dormancy

`PID.md:185` freezes promoted versions; `PID.md:195-197` requires strategies to
go dormant and reactivate — and `status` lives inside the package. Resolved by
separating **specification** (frozen) from **activation state** (a fixed
transition table, never returning to `CANDIDATE`). A status change accompanied
by any content edit is still refused. Durable statement: `docs/VERSIONING.md`.

### 3. Criterion 13 and the absent promotion — PL ruling on a blocked finding

A repair Engineer was asked to land a real `1.1.0` candidate in the inventory
and returned **`blocked`**, correctly. `derive_candidate` refuses a
non-promoted parent, and `gold_context_breakout` 1.0.0 is honestly `CANDIDATE`:
its own acceptance criteria require ≥100 qualifying matches and a measured
expectancy uplift, which need a backtester, market data and a live CER — two
explicit PID non-goals and one system the PID itself says may not exist yet
(`PID.md:181`).

**Ruling: criterion 13 is proven by capability, and the inventory stays at one
version.** Manufacturing a promotion to produce a second directory would
fabricate exactly the verdict this delivery removed from the CER fixtures, and
would contradict the PID's own evidence-gated promotion model. The criterion
requires HSA to *produce a separately versioned candidate rather than mutate a
promoted strategy* — a capability, proven against the real on-disk package by
`tests/test_criterion_13_inventory.py`: the governed refusal fires, the
derivation produces a valid 1.1.0 with `supersedes` and correctly dropped gate
evidence, in-place mutation is refused, and `1.0.0/` is asserted
**byte-identical** afterwards by SHA-256.

Two forward invariants keep this from decaying into an excuse: the suite fails
the moment any package is marked promoted without `CER_LIVE` promotion
evidence, and any superseding version the inventory ever holds must be a
governed derivation.

This is a **product-authority** matter, not an engineering one. If a second
inventory directory is wanted before CER is live, someone holding product
authority must state on the record what evidence justifies promoting 1.0.0.
The PL's position is that no such evidence exists today.
