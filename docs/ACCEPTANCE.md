# HSA v1 — acceptance evidence and PL adjudication record

Presentation target: **`FUNCTIONAL_ONLY`** (`PID.md:11`). The PID's explicit
non-goals include dashboards/UI (`PID.md:275`), so there is no browser surface
and no browser-verification gate applies. Evidence here is mechanical.

Full suite: **869 passed** — pinned by
`tests/test_boot.py::test_the_acceptance_record_reports_the_suite_it_actually_has`,
so a stale number here fails rather than waiting for an audit. `hsa boot` reports
`17 artifacts declared: 17 loaded, 0 required missing, 0 optional absent`.

## Acceptance criteria (`PID.md:246-262`)

| # | Criterion | Where it is proven |
|---|---|---|
| 1 | load durable doctrine without Matt re-explaining it | `hsa boot` (exit 0, 17/17); `docs/boot-manifest.json`; `tests/test_boot.py` (53), which now also asserts `docs/BOOT.md`'s sample output against a live run |
| 2 | ingest a realistic raw strategy description | `strategies/*/*/source.txt` driven through `hsa intake`; `tests/test_intake.py` (31) |
| 3 | identify ambiguity rather than guessing | `docs/AMBIGUITY-POLICY.md`; `tests/test_ambiguity.py` (113). Five directions proven — Example A's first-pass source was **refused** (exit 4) for "strong trend"/"clean breakout"; Example B's terms were **parameterised** with attribution; and a ruled term whose context re-bases it (*"large wick relative to the recent average"*, *"twice the 14-period ATR"*) is **refused** rather than resolved onto a basis the source displaced; and a ruled term whose own wildcard slot holds unresolved language (*"a large **near resistance** wick"*) is **refused** rather than resolving over the top of it, which is the direction a third audit found open; and a ruled term whose own **literal** phrase collides with a refusal (*"a no-wick **close to resistance**"*, where `no_wick_candle` and `near_resistance` both claim the word *close*) is **refused**, with the refusal reported on its own terms — overlap resolution decides which term parameterises and is not allowed to decide that the loser was never said (`term_match_policy.overlap_resolution`). and a ruled term whose match runs across a **sentence boundary** (*"a valid **m.a** breakout"*, where a dotted abbreviation was read as a full stop) is **refused and reported** rather than discarded, which is the direction a fifth audit found open and the last of the three rules in `term_match_policy` that could stop a recognised match resolving. Those are asserted over corpora generated from the declared patterns rather than a written list of sources, and each is checked for vacuity by re-arming the defect. The general statement is enforced structurally as well as asserted: every recognised match leaves the scan carrying one declared reason it was accounted for, checked against the findings actually emitted, and there is no reason meaning "dropped" — a sixth deletion path raises `UnreportedMatchError` instead of drafting at exit 0. A resolution reports `hsa_invented_basis: false` and `source_basis_agreement: "NOT_VERIFIED"` beside the scan that was actually run; it does not emit `hsa_guessed`, which claimed more than was checked |
| 4 | decompose into independent atomic strategies | `catalogue/atomic/` (11 entries); `tests/test_catalogue.py` (149). Atomics cannot reference peers — structurally impossible in `contracts/atomic_strategy.schema.json` |
| 5 | construct an explicit chain using canonical primitives | Example A `CONTEXT_TRIGGER`, Example B `SEQUENCE`; `tests/test_semantics.py` (94). Per-input reason attribution (`PID.md:80`) is now bound mechanically: every `reason_fields` entry must name a chain `input_id` and a field that input's atomic emits, or a field the package's `output_contract` declares |
| 6 | assign semantic timeframe roles | both packages' `timeframe_roles`; roles are assignments, not universal timeframes (`PID.md:93`) |
| 7 | define timing/direction/persistence/expiry | both packages; `package.chain_agreement` enforces package and embedded chain agree |
| 8 | map required inputs to HERMES | `required_hermes_fields` per atomic; `package.hermes_coverage` |
| 9 | produce a coherent deterministic HELIOS package | `hsa validate` runs structural **and** semantic by default; `tests/test_semantic_cli.py` (27) |
| 10 | preserve strategy/version identity | id+version pinned everywhere including directory paths; embedded atomics byte-identical to catalogue entries |
| 11 | define tests and evidence requirements | `deterministic_test_cases` and evidence requirements in both packages |
| 12 | use/target CER semantics | `docs/CER-CONTRACT.md`; 8 fixtures; `tests/test_cer.py` (58), `tests/test_cer_evidence_container.py` (21) |
| 13 | separately versioned candidate, never mutate a promoted strategy | `docs/VERSIONING.md`, now a **required boot artifact** so a fresh boot is shown the `derive_candidate` mechanism it must use; `tests/test_versioning.py` (63), `tests/test_criterion_13_inventory.py` (13). **See the adjudication below** |

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

`PID.md:114` lists "large wick" among phrases that must not be guessed;
`PID.md:242` builds Example B on one and `PID.md:288` requires the examples to
pass. Resolved by `PID.md:110` + `PID.md:120`: **parameterise** where the
measurement basis is known and only the threshold is unset; **refuse** where
the basis is itself undefined. Of the five phrases at `PID.md:114-118`, **one
parameterises and four refuse**. Example B additionally depends on "no-wick
candle" (`PID.md:55`), which parameterises as well — so the lexicon rules on
**six** terms, two `PARAMETERISE` and four `REFUSE`. Criterion 3 stays testable
and Example B stays reachable. (This previously read "of the PID's five
examples, two parameterise and four refuse", which is six outcomes from five
phrases; the sixth term is real, it is just not one of the five.) Durable
statement: `docs/AMBIGUITY-POLICY.md`, which scopes the same set.

A later audit found the document promising more than the code delivered: it
stated that a ruled term is re-based by its context and therefore refuses,
and nothing implemented that. It does now, through a declared
`basis_qualifiers` vocabulary inside a declared window, and the document
states what that guard does not cover instead of implying completeness.

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

Two forward invariants keep this from decaying into an excuse, and they are in
different states, which this record now says rather than presenting both as
live:

- **promotion is evidenced.** The predicate — a package claiming a
  promotion-proving status carries `CER_LIVE` promotion evidence, and any
  promotion evidence at all is `CER_LIVE` — is exercised directly against
  constructed in-memory packages, and then swept over the real inventory. Over
  the inventory alone it executed no assertion at all (1.0.0 is a `CANDIDATE`
  with no promotion evidence, so both branches are skipped), and it was
  presented here as an active guard while nothing it asserts had ever run.
- **any superseding version is a governed derivation.** Still **dormant by
  design**: the inventory holds no superseding version, so the loop body does
  not execute. The test declares that in its own docstring and is written now
  so the rules a derived version must meet are on the record before anyone
  derives one. It gains teeth the day a real 1.1.0 lands, without a rewrite.

This is a **product-authority** matter, not an engineering one. If a second
inventory directory is wanted before CER is live, someone holding product
authority must state on the record what evidence justifies promoting 1.0.0.
The PL's position is that no such evidence exists today.
