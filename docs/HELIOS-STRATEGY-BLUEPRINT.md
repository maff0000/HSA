# HELIOS Strategy Blueprint

**Status:** durable authority. HSA boots with this document and enforces it
every time (`PID.md:9`).

This is the doctrine a strategy must satisfy before HSA will call it a
governed HELIOS strategy. It exists so that a new AI session does not need
Matt to re-explain how to convert a trading idea into a deterministic,
testable, governed HELIOS strategy (`PID.md:7`).

Every rule below is traceable to a line of `PID.md`. Where the PID is silent,
this document says so rather than filling the gap — see
[What this Blueprint does not decide](#8-what-this-blueprint-does-not-decide).
Inventing trading doctrine that the PID does not carry is out of bounds for
HSA and for anyone editing this file.

**Companion doctrine, owned elsewhere.** Do not restate these here;
duplicated doctrine drifts.

| Topic | Authority |
| ----- | --------- |
| Composition, chaining, the canonical primitives in detail | [`docs/COMPOSITION-DOCTRINE.md`](COMPOSITION-DOCTRINE.md) |
| Intake, discretionary language, `STRATEGY_NOT_SUFFICIENTLY_DEFINED` | [`docs/AMBIGUITY-POLICY.md`](AMBIGUITY-POLICY.md) |
| CER identities, evidence semantics, fixtures | [`docs/CER-CONTRACT.md`](CER-CONTRACT.md) |
| HSA's own role, what it owns and must never do | [`docs/HSA-ROLE.md`](HSA-ROLE.md) |
| The machine-checkable shapes of every artifact | [`contracts/README.md`](../contracts/README.md) |

---

## 1. Atomic strategies

An **atomic strategy** is the unit of strategy engineering. HSA decomposes
every idea into atomic strategies before anything else is specified
(`PID.md:23`).

### 1.1 The seven properties

An atomic strategy is (`PID.md:45-53`):

1. **small** — it answers one market question, not several;
2. **self-contained** — everything it needs is in its own definition;
3. **independently testable** — it can be proven true or false on its own,
   without any other strategy present;
4. **deterministic** — the same inputs always produce the same output. No
   randomness, no wall-clock dependence, no hidden state;
5. **execution-blind** — it knows nothing about orders, fills, position size,
   risk or money. It reports what the market did, not what to do about it;
6. **unaware of other strategies** — it cannot name, call, import or read
   another strategy;
7. **mechanically driven by HERMES facts** — its inputs are measurable market
   facts sourced from HERMES, never opinion or narrative.

A candidate that fails any one of these is not atomic. Split it, or push the
part that fails back into composition, intake or the runtime where it
belongs.

### 1.2 Named examples

The PID names these as examples of the right size and shape (`PID.md:55`):
golden/death cross, breakout, proximity to swing high/low, rejection wick,
no-wick candle, engulfing, momentum, volatility expansion, structure break,
retest, compression.

They are examples, not a closed list, and not a claim that any of them is
profitable. The catalogue of atomic strategies HSA actually holds lives in
`catalogue/atomic/`; boot loads it (`PID.md:213`).

### 1.3 Failure modes this rules out

- *"It's atomic, it just checks the trend filter first."* — a strategy that
  consults another strategy is composition, and belongs in a chain
  (`PID.md:59`).
- *"It's atomic, it only skips the signal when we're already long."* —
  position awareness is execution state. Atomic strategies are
  execution-blind (`PID.md:51`) and HSA does not know account or broker state
  at all (`PID.md:35`).
- *"It's atomic, it just needs the last three sessions of its own output."* —
  persistence and state are chain-level semantics (`PID.md:70-79`), declared
  explicitly, not hidden inside an atom.

### 1.4 Composition, in one paragraph

Atomic strategies never call or import other strategies; a separate
composition model combines their normalised outputs using the canonical
primitives `ALL`, `ANY`, `SEQUENCE` and `CONTEXT_TRIGGER` (`PID.md:59-68`).
Chains preserve component identity and version, state, direction, timing and
sequence, persistence, expiry, timeframe semantics, provenance, and an
explicit reason for match and non-match (`PID.md:70-80`). v1 prefers atomic
inputs to chains and does not build recursive chain-of-chain complexity
without explicit authorisation (`PID.md:82`).

Everything beyond that paragraph — how each primitive resolves, how sequence
windows and expiry are expressed, how a chain explains itself — is in
[`docs/COMPOSITION-DOCTRINE.md`](COMPOSITION-DOCTRINE.md).

### 1.5 Ambiguity, in one paragraph

HSA turns discretionary language into measurable definitions and does not
guess ambiguous trading rules (`PID.md:39`, `PID.md:110`). Phrases such as
"large wick", "near resistance", "strong trend", "confirmation candle" and
"good breakout" must not be guessed (`PID.md:112-118`). Where material
ambiguity remains, HSA returns a structured
`STRATEGY_NOT_SUFFICIENTLY_DEFINED` result naming exactly what is unresolved
and what evidence or decision is needed (`PID.md:120`).

The full policy — how ambiguity is detected, graded and reported — is in
[`docs/AMBIGUITY-POLICY.md`](AMBIGUITY-POLICY.md).

---

## 2. The multi-timeframe semantic template

### 2.1 The four roles

HSA's initial strategy-engineering pattern uses four semantic roles
(`PID.md:84-91`):

| Role | Question it answers | Initial GOLD mapping |
| ---- | ------------------- | -------------------- |
| `CONTEXT` | What regime or structure are we in? | 4H |
| `LOCATION` | Are we at a place that matters? (proximity) | 1H |
| `CONFIRMATION` | Has the market proved something? | 15M |
| `TRIGGER` | Is the precise moment now? | 5M |

### 2.2 The roles are semantic, the timeframes are not fixed

**This is the rule most easily broken and the one that matters most.** The
timeframes above are the *initial GOLD* mapping, not universal constants
(`PID.md:86`, `PID.md:93`). The roles are canonical; the timeframe each role
maps to is a per-strategy choice that the strategy must declare.

HSA must allow other mappings, for example `1D/4H/1H/15M` or `1H/15M/5M/1M`
(`PID.md:95`).

Practical consequences:

- Never hard-code `4H` as "the context timeframe" in a specification, a
  catalogue entry, or a HELIOS implementation instruction.
- An atomic strategy is written against a *role*, or against no role at all,
  and is bound to a concrete timeframe by the strategy that uses it.
- A specification that omits its role-to-timeframe mapping is incomplete.
- Not every strategy needs all four roles. Use the roles the thesis actually
  requires and say which are unused.

### 2.3 The template is a hypothesis

The template is a hypothesis structure to be empirically validated, not
doctrine that guarantees edge (`PID.md:97`). HSA may not present a strategy
as sound merely because it fills all four roles. Evidence decides that, via
CER (§4.4), and dormancy is an acceptable outcome (§6).

---

## 3. The required strategy specification output

A governed HSA strategy package must include, **as applicable**
(`PID.md:124-146`):

| # | Element | Notes |
| - | ------- | ----- |
| 1 | `strategy_id` | Identity, stable across versions (§7.1). |
| 2 | `strategy_version` | Identity is always id **plus** version. |
| 3 | title / description | What a human calls it. |
| 4 | economic / trading thesis | *Why* this should work. A package without a thesis is a pattern, not a strategy. |
| 5 | instrument(s) | What it is specified against. |
| 6 | intended horizon / style | Scalp, intraday, swing — declared, not implied. |
| 7 | required HERMES fields / signals / indicators | Every input mapped to a HERMES output (`PID.md:22`). Nothing is assumed available. |
| 8 | atomic strategy definitions | The decomposition, each satisfying §1.1. |
| 9 | semantic timeframe roles | The role-to-timeframe mapping of §2. |
| 10 | chain definition | The composition, per `COMPOSITION-DOCTRINE.md`. |
| 11 | direction semantics | Long / short / both, and how direction is derived. |
| 12 | timing / persistence / expiry | How long a component's truth survives. |
| 13 | state semantics | What state exists and where it lives. |
| 14 | invalidation / validity conditions | What makes a live signal void. |
| 15 | parameter definitions and allowed ranges | Every parameter bounded, with units and a default. Unbounded parameters are how overfitting enters. |
| 16 | expected output contract | Exactly what the strategy emits. |
| 17 | deterministic test cases | Fixed inputs, fixed expected outputs. |
| 18 | backtest / evidence requirements | What must be proven before promotion. |
| 19 | acceptance / rejection criteria | Stated **before** the evidence arrives. |
| 20 | provenance to original strategy source | Back to Matt's observation, the video, the book, the report. |
| 21 | CER identity / evidence references | Per [`docs/CER-CONTRACT.md`](CER-CONTRACT.md). |
| 22 | `lifecycle` | Status, immutability and what this version supersedes. Not from the `PID.md:124-146` list — it comes from acceptance criterion 13 (`PID.md:262`) and the versioning doctrine (`PID.md:183-189`), and it is required on every package (§5). A package built from the twenty-one elements above alone does **not** validate. |

"As applicable" is the PID's own qualifier (`PID.md:124`), and the contract
reads it narrowly: **every** element above is `required` in
`contracts/strategy_package.schema.json`, and "as applicable" is honoured by
allowing structurally empty content where a section genuinely does not apply —
an empty `parameters` array for a fully fixed strategy — **never** by allowing
the field itself to be absent. A missing section cannot be told apart from an
overlooked one, and FORGE cannot tell the difference; an explicitly empty one
is a decision on the record. (This paragraph used to read "as applicable" as
licensing omission, which contradicted the schema it describes.)

An element that applies but is unknown is neither absent nor empty: it is
ambiguity, and takes the `STRATEGY_NOT_SUFFICIENTLY_DEFINED` route (§1.5).

### 3.1 The precision bar

> HSA must produce enough precision that FORGE implements the specification
> rather than inventing trading logic. (`PID.md:148`)

That sentence is the acceptance test for every package HSA emits. The
question is never "is this a good description of the idea?" but "could a
competent engineer who knows no trading implement exactly this, with no
decision left to them?"

If the answer is no, the package is not finished — regardless of how
confident anyone is about the idea.

The machine-checkable half of this bar is `contracts/strategy_package.schema.json`;
`hsa validate <file>` enforces it. Schema validity is necessary and not
sufficient: a schema cannot tell you that a thesis is vacuous or that a test
case proves nothing.

---

## 4. Where HSA sits: authority boundaries

```
   source idea ─▶ HSA ──── governed specification ────▶ FORGE ──▶ HELIOS
   (Matt, book,   │                                      (builds)  (runs it)
    video, trader)│                                                    │
                  │◀──── evidence / identities ──── CER ◀── runs ──────┘
                  │                                  ▲
                  └──◀── hypotheses ── NEO ──────────┘
```

### 4.1 HSA — the strategy architecture authority

HSA owns strategy engineering; it does not own software delivery and does not
own live trading (`PID.md:15`, `PID.md:152`). Its full duties and
prohibitions are in [`docs/HSA-ROLE.md`](HSA-ROLE.md).

### 4.2 HELIOS — the deterministic runtime strategy engine

HELIOS runs strategies (`PID.md:154`). HSA must not embed runtime trading
state or broker/account knowledge into HELIOS specifications (`PID.md:156`).

A specification that says "if we are already in a position, skip" has put
runtime state into the strategy layer and is wrong at the architecture level,
not merely awkward.

### 4.3 FORGE — the implementer

FORGE implements HSA-approved specifications inside HELIOS (`PID.md:158`).

**The return path is doctrine:** if implementation exposes ambiguity, the
strategy returns to HSA rather than FORGE guessing (`PID.md:158`). A question
from FORGE about what a rule means is not a delay to be worked around with a
plausible answer — it is the system behaving correctly. HSA answers it, or
returns `STRATEGY_NOT_SUFFICIENTLY_DEFINED`.

HSA must not reinterpret FORGE's engineering role (`PID.md:38`).

### 4.4 CER — the evidence and identity authority

HSA must use CER canonical identities and evidence semantics (`PID.md:162`),
at minimum `strategy_id`, `strategy_version`, `experiment_id`, `run_id`,
`evidence_id` and `artifact_id` (`PID.md:164-171`).

Through CER contracts, HSA records or targets source analysis, strategy
hypotheses, strategy-version lineage, research findings, and the evidence
references supporting promotion, revision or rejection (`PID.md:173-179`).

HSA must not bypass CER (`PID.md:37`). If CER is not yet live, HSA may use
contract fixtures or mocks, but must not create an incompatible permanent
evidence store (`PID.md:181`) — a convenient local results file that CER
would later have to reconcile is exactly the prohibited thing.

Detail: [`docs/CER-CONTRACT.md`](CER-CONTRACT.md).

### 4.5 NEO — a source of evidence and hypotheses

NEO may provide evidence and hypotheses. HSA governs any resulting candidate
strategy redesign. **NEO may never silently rewrite HELIOS** (`PID.md:200`).

A NEO finding is an input to strategy engineering, never a change to a live
strategy. It enters through the same governed route as any other idea and
produces a separately versioned candidate (§7.1).

---

## 5. Strategy versioning

### 5.1 Promoted versions are immutable

- Promoted strategy versions are immutable (`PID.md:185`).
- Do not tweak a live strategy in place (`PID.md:187`).
- A proposed modification creates a **separately versioned candidate** and
  must pass governed evidence gates again (`PID.md:189`).

There is no such thing as a small safe edit to a promoted strategy. Changing
a parameter default, widening a range, relaxing a filter — each is a new
candidate version that re-earns its promotion through evidence. This is what
makes evidence attributable: without it, evidence gathered under version 1.2
silently describes behaviour that no longer exists.

Identity is `strategy_id` **plus** `strategy_version` everywhere it appears —
in chains, in CER references, in the inventory.

### 5.2 The silent-mutation prohibition

HSA must not mutate a live HELIOS strategy silently (`PID.md:36`). "Silently"
is the operative word: the governed route (new candidate, evidence, gate)
exists and is always available. What is forbidden is the change that leaves
no versioned trace.

---

## 6. Portfolio philosophy

Long-term doctrine (`PID.md:191-198`):

- **Prefer many independently proven specialist strategies** over one
  general strategy asked to work everywhere.
- **Do not force a strategy to trade outside its preferred market shape.** A
  strategy built for volatility expansion is not repaired by making it also
  trade compression; that is a different strategy.
- **Dormancy is not failure.** A strategy producing no signals because its
  conditions are absent is behaving correctly.
- **Do not tune merely to restore trade frequency.** Trade count is not the
  objective, and tuning toward it is how a proven strategy is destroyed.
- **Allow old proven strategies to remain available and reactivate when
  conditions return.** Retirement is not the default response to a quiet
  period.
- **Avoid overfitting.** Every additional free parameter and every
  post-hoc rule fitted to observed history is a step toward describing the
  past instead of predicting the future.

These interlock. Specialisation is only safe if dormancy is acceptable;
dormancy is only acceptable if nobody tunes to restore frequency; not tuning
is only possible if old strategies may sit idle and return.

---

## 7. Applying this Blueprint to a strategy

The order HSA works in, from `PID.md:19-30`:

1. ingest the idea or source, preserving provenance;
2. extract the thesis — *why* this should work;
3. identify the measurable market facts it depends on;
4. map every required fact to a HERMES output;
5. decompose the logic into small atomic strategies (§1);
6. define the chain composition (`COMPOSITION-DOCTRINE.md`);
7. define temporal, directional and state semantics (§2, §3);
8. produce the deterministic HELIOS implementation specification (§3);
9. define the evidence and testing requirements;
10. preserve strategy identity and versioning (§5);
11. consume CER evidence (§4.4);
12. propose a new candidate version when evidence supports change (§5.1).

At any step, unresolved discretionary language stops the process and produces
`STRATEGY_NOT_SUFFICIENTLY_DEFINED` (§1.5). Proceeding with a plausible
guess is the one failure this Blueprint exists to prevent.

### 7.1 Before declaring a package finished

- [ ] Every atomic strategy satisfies all seven properties of §1.1.
- [ ] No atomic strategy names another strategy.
- [ ] Semantic roles are assigned and mapped to declared timeframes (§2.2).
- [ ] Every input maps to a named HERMES output.
- [ ] Every parameter has units, a default, and a bounded range.
- [ ] Direction, timing, persistence, expiry and invalidation are all stated.
- [ ] Deterministic test cases exist, with fixed inputs and expected outputs.
- [ ] Acceptance and rejection criteria were written before the evidence.
- [ ] Provenance reaches the original source.
- [ ] CER identities are present and follow CER semantics.
- [ ] `lifecycle` is stated: status, `immutable_once_promoted`, and what
      this version supersedes (`null` for an original, stated rather than
      omitted).
- [ ] `hsa validate <package>` exits 0.
- [ ] Nothing in the package requires FORGE to decide a trading question.

---

## 8. What this Blueprint does not decide

The PID is silent on the following. They are open questions to raise, not
gaps to fill with invention. Anyone extending this document must keep that
distinction.

- **Numeric evidence thresholds.** The PID requires acceptance and rejection
  criteria per strategy (`PID.md:143-144`) but sets no portfolio-wide
  minimum sample size, significance level or drawdown limit. Each package
  states its own; there is no default to inherit.
- **Who approves a promotion.** The PID requires governed evidence gates
  (`PID.md:189`) without naming the approver or the ceremony.
- **The HERMES field vocabulary.** The PID requires facts to be mapped to
  HERMES outputs (`PID.md:22`) but does not enumerate them. Field names come
  from HERMES, not from HSA's imagination.
- **Instruments beyond the GOLD example.** The multi-timeframe mapping in §2
  is given as the *initial GOLD* pattern (`PID.md:86`). The PID neither
  restricts HSA to GOLD nor specifies mappings for anything else.
- **Layout of the strategy inventory.** `PID.md:216` requires the current
  inventory to be loadable "where available" without specifying its shape.
  The boot manifest records where it lives; its internal structure is
  decided by the work item that creates it.
- **Anything about position sizing, risk, portfolio allocation or execution.**
  Not silence but exclusion: these are outside HSA's authority entirely
  (`PID.md:15`, `PID.md:34`, `PID.md:51`).
