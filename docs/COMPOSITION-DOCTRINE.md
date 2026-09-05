# Composition doctrine

How HSA combines atomic strategies into chains, and why it combines them the
way it does. This is durable authority: a fresh HSA boot loads this document
and does not need the reasoning re-explained (PID lines 202-218).

Its subject is PID lines 57-97. The machine-enforced half lives in
`contracts/chain.schema.json` and `hsa/semantics.py`; this document is the
half that explains *why*, and states the rules that are doctrine rather than
code.

---

## 1. Atomic strategies never call or import each other

PID line 59. This is the load-bearing rule of the whole model, and everything
below is downstream of it.

An atomic strategy is small, self-contained, independently testable,
deterministic, execution-blind, unaware of other strategies, and mechanically
driven by HERMES facts (PID lines 45-53). Every one of those properties is
lost the moment one strategy may consult another:

- **Independently testable** stops being true. A strategy that consults a peer
  can only be tested against that peer's behaviour, so its
  `deterministic_test_cases` no longer pin its own logic.
- **Evidence stops being attributable.** CER records evidence against
  `strategy_id` plus `strategy_version` (PID lines 162-171). If `retest`
  internally consults `structure_break`, then evidence recorded against
  `retest` is really evidence about a pair, and promoting one version silently
  re-promotes a hidden dependency that no gate examined.
- **Versioning stops being safe.** Promoted versions are immutable (PID lines
  185-189). A hidden edge from A to B means a new version of B changes the
  behaviour of the frozen A, which is precisely the in-place mutation the PID
  forbids.
- **Reuse stops being free.** An atomic that carries a dependency can only be
  composed where its dependency is also wanted.

So composition is a **separate model applied from the outside** (PID line 61).
A chain reads normalised atomic outputs and combines them. The atomics never
learn that a chain exists.

The prohibition is structural, not advisory: `atomic_strategy.schema.json`
provides no property through which another strategy could be named and sets
`additionalProperties: false`, so a document that invents one fails
validation. See `contracts/README.md`.

**The line this puts on catalogue authoring.** An atomic strategy may consume
any market fact HERMES publishes, including structural ones. It may not
consume the *output of another HSA strategy*. `level_retest` in the catalogue
is the worked example: it needs to know a level was broken, and it takes
`level.recent_break_price` from HERMES rather than reading
`structure_break`'s output. A chain that wants those two to agree composes
them; it does not wire them together.

---

## 2. What normalisation buys

Every atomic declares an `output_contract` with a `signal_type` of `BOOLEAN`,
`STATE` or `SCORE`, a field list, and a mandatory `reason_field`
(`common.defs.json`). That shared shape is what lets a chain treat a
rejection wick and a moving-average cross as the same kind of thing without
knowing anything about either.

The mandatory `reason_field` is what makes the chain's own explanation
possible. A chain does not invent an explanation; it assembles one out of the
reasons its components already emit.

---

## 3. The canonical primitives

Exactly four, per PID lines 63-68. The enum in `chain.schema.json` is closed:
adding a fifth is a PID change, not a document change.

Throughout, *required input* means an input without `optional: true`.

### `ALL`

Every required input must match **on the same evaluation**, in the chain's
resolved direction.

- Order is not significant. An input that matched three bars ago has not
  matched now, unless the chain's own `persistence` says a match stays
  asserted for a number of bars — in which case that persistence, not the
  input, is what is still holding.
- Direction: every required input must agree once `INHERIT` and `EITHER` are
  resolved. Disagreement is a non-match, and the reason must say which input
  disagreed.
- Optional inputs are evaluated and reported, and their result never blocks a
  match.

### `ANY`

At least one required input must match on the evaluation. The matching input
carries the chain's direction; where more than one matches, the chain's
`direction_rule` must say how direction is resolved.

- `ANY` is the one primitive where a single input causes a match on its own.
  That is why an `optional` input under `ANY` is rejected: see §6.
- Non-match must still report every input, since "none of these fired" is only
  auditable if the reader can see what was tried.

### `SEQUENCE`

Required inputs must match in ascending `sequence_index` order, each at or
after the one before, and the whole ordered set must complete inside
`timing.sequence_window`.

- `sequence_index` is 1-based and must be contiguous with no duplicates —
  enforced by `hsa/semantics.py`, because a gap or a repeat leaves the order
  undetermined and JSON Schema cannot see it.
- The window is mandatory for `SEQUENCE` (enforced by the schema). A sequence
  with no window is not a sequence, it is a claim that two things happened at
  some point, which is not testable.
- Partial progress is state. A `SEQUENCE` chain that has seen step 1 and is
  waiting for step 2 is in a named state, and `state_semantics` must name it
  and say what resets it.
- An optional step is skipped without breaking the ordering: if steps are
  1, 2 (optional), 3, then 1 followed by 3 inside the window is a match.

#### The limit on ordering, stated rather than glossed

Contiguity and uniqueness are the **only** ordering rules a check can
enforce. Whether the order is the *right* order is not visible in the
document at all.

Swap `sequence_index` 1 and 2 on the Example B package and the strategy
inverts — it now waits for a no-wick bar and then a rejection wick, the
opposite setup — and it still validates, structurally and semantically,
because 1 and 2 are still contiguous and still unique. Nothing is wrong with
the document. Something is wrong with the strategy.

That gap is not closable by a check, and trying would be worse than leaving
it open. The correct order comes from the source, and HSA recovering it from
the chain alone would mean deciding which of two orderings a trader meant —
a trading decision it was never given, which `PID.md:39` forbids. There is no
mechanical difference between "wick then confirmation" and "confirmation then
wick" that does not come from outside the document.

What does pin the order is `deterministic_test_cases` (`PID.md:142`): fixed
HERMES facts with the exact expected output, which an inverted chain fails.
So for a `SEQUENCE` chain the test cases are not a nice-to-have alongside the
specification — **they are the only place the intended order is recoverable**,
and a reviewer checking a sequence must read them against the source rather
than trusting that a valid document is a correct one.

### `CONTEXT_TRIGGER`

A `CONTEXT_TRIGGER` chain carries exactly two inputs' worth of roles: one
CONTEXT and one TRIGGER. A third role, or a second of either, is rejected —
the primitive defines no rule for how it would combine.

A higher-timeframe `CONTEXT` input must be **holding** at the moment a
lower-timeframe `TRIGGER` input **fires**.

This is the only primitive that distinguishes a *condition that persists* from
an *event that occurs*, and it is the reason the primitive exists separately
from `ALL`.

- The schema requires both roles to be present. `hsa/semantics.py` additionally
  requires the CONTEXT input's timeframe to be **strictly higher** than the
  TRIGGER's — a 5M context over a 4H trigger validates structurally while
  inverting the entire model of PID lines 84-97.
- "Holding" means the context's most recent evaluation on its own timeframe is
  still a match. A 4H context is evaluated eight times fewer than a 5M trigger;
  the chain reads the context's latched result, which is why a
  `CONTEXT_TRIGGER` chain is nearly always stateful.
- Neither the CONTEXT nor the TRIGGER input may be `optional`. The primitive is
  *defined* as the conjunction of those two roles.
- Direction is normally taken from the context, with the trigger required to
  agree; whichever way a chain resolves it, `direction_rule` must say so.

---

## 4. What a chain must preserve

PID lines 70-80, in order. Each is a required property of `chain.schema.json`,
so a chain that omits one does not validate.

| Preserved | Where it lives | Why it cannot be dropped |
| --- | --- | --- |
| **Component identity and version** | `inputs[].strategy_id` + `strategy_version`, both required | Evidence in CER is recorded against id *and* version. A chain that pinned only an id would silently change meaning when a new version was promoted. |
| **State** | `state_semantics` | A latched context or a half-complete sequence is state. Undeclared state is state HELIOS invents for itself. |
| **Direction** | `direction_semantics` on the chain and per input | Composing a LONG context with a SHORT trigger is a non-match, not a match. That is only decidable if both express direction. |
| **Timing / sequence** | `timing`, `inputs[].sequence_index` | "Both happened" and "one happened then the other" are different strategies. |
| **Persistence** | `persistence` | How long a match stays asserted is part of the strategy, not an implementation choice for FORGE. |
| **Expiry** | `expiry` | An unconsumed match or a latched context that never goes stale is a leak. If `expires` is true the schema forces a bar count and a timeframe: an expiry with no horizon is exactly the discretionary language HSA refuses. |
| **Timeframe semantics** | `timeframe_roles`, `inputs[].timeframe_role` + `timeframe` | See §5. |
| **Provenance** | `provenance` | An artefact whose origin cannot be named is not governed (PID line 145). |
| **Explicit reason for match AND non-match** | `explanation_contract` | See below. |

### The reason requirement is the strictest of them

PID line 80 asks for an explicit reason for match **and** non-match.
`explanation_contract` sets `emit_reason_on_match`,
`emit_reason_on_non_match` and `per_input_evaluation_reported` all to
`const: true`, so no chain can be authored that reports a bare boolean.

A non-match with no reason is unauditable, and unauditable output cannot be
governed by evidence. In practice the non-match reason is the more valuable
of the two: it is what tells a researcher whether a strategy is dormant
because its conditions are absent (PID line 195: dormancy is not failure) or
because it is broken.

Attribution must be **per input**, using each atomic's own `reason_field`. "The
chain did not match" is not a reason; "context held, trigger did not fire —
break_distance_ratio 0.05 against a required 0.1" is.

---

## 5. The multi-timeframe semantic role model

PID lines 84-97. The initial GOLD pattern is:

| Role | Question it answers | Initial GOLD mapping |
| --- | --- | --- |
| `CONTEXT` | What regime are we in? | 4H |
| `LOCATION` | Are we somewhere that matters? | 1H |
| `CONFIRMATION` | Has the idea proved itself? | 15M |
| `TRIGGER` | Is it happening now? | 5M |

**The roles are canonical. The timeframes are not.** PID line 93 states this
directly, and line 95 requires 1D/4H/1H/15M and 1H/15M/5M/1M to be equally
expressible. So:

- The **role** enum is closed in `common.defs.json`. `CONTEXT`, `LOCATION`,
  `CONFIRMATION` and `TRIGGER` are the vocabulary.
- The **mapping** is per chain, declared in `timeframe_roles`. Nothing in HSA
  hard-codes 4H to `CONTEXT`.
- A chain need not use all four roles. Acceptance example A uses two.
- `hsa/semantics.py` requires each input's declared `timeframe` to equal the
  timeframe its role maps to, and requires every role an input uses to appear
  in the role model. A document that says `CONTEXT` is 4H in one place and 15M
  in another states two different things about one role.

PID line 97 is worth restating because it constrains how this template may be
used: it is **a hypothesis structure to be empirically validated, not doctrine
that guarantees edge.** A chain that assigns roles correctly has been
specified correctly. It has not been shown to work. That is what CER evidence
gates are for.

---

## 6. `optional` inputs

`optional: true` on a chain input exists for one named requirement: the
*optional lower-timeframe trigger* of PID line 242, acceptance example B.

**What it means.** An optional input is evaluated, and its result is reported
in the explanation, but its non-match does not prevent the chain matching. It
adds information; it does not gate.

**What it can never be.** *An optional input can never be the sole cause of a
match.* If the only reason a chain matched is that an optional input matched,
then that input was not optional — it was the strategy. `hsa/semantics.py`
enforces this in four forms:

1. A chain whose single input is optional is rejected: nothing is required to
   cause a match.
2. A chain whose inputs are *all* optional is rejected, for the same reason.
3. Any optional input under `ANY` is rejected. `ANY` matches when one input
   matches, so an optional input there is by construction able to be the sole
   cause.
4. The `CONTEXT` or `TRIGGER` input of a `CONTEXT_TRIGGER` chain may not be
   optional, since the primitive is defined as those two roles together.

Under `ALL` and `SEQUENCE`, an optional input alongside at least one required
input is legitimate and is the intended use.

---

## 7. Chains are flat in v1

PID line 82: *prefer atomic-strategy inputs to chains in v1; do not create
recursive chain-of-chain complexity unless explicitly authorised.*

HSA reads that strictly, and the PL has ratified the strict reading. A chain
is **exactly one top-level primitive whose inputs are atomic references
only**. There is no operator nesting. `ALL(context, ANY(trigger_a,
trigger_b))` cannot be expressed and must be split into separately governed
chains.

This is enforced by the shape of `chain.schema.json`, not by convention: there
is no reusable node definition, no self-`$ref`, and no `chain_id` inside an
input, so a nested node is unrepresentable rather than discouraged.

### Why the strict reading

- **It is what the PID says.** The permissive reading — "allow nesting, just
  prefer not to" — needs the words *unless explicitly authorised* to mean
  something other than what they say.
- **Both acceptance examples are flat.** PID lines 234-242 describe a
  context-plus-trigger chain and an ordered three-step sequence. Neither needs
  nesting. A restriction that costs nothing on the actual requirements is
  cheap.
- **Evidence stays attributable.** A flat chain has one primitive and a list
  of versioned atomics, so a CER record against `chain_id` + `chain_version`
  describes something a human can hold in their head. A nested tree does not
  decompose that way.
- **Relaxing later is additive; withdrawing later is not.** Permitting a
  nested node as an *alternative* kind of input in some future version would
  not invalidate a single document written today. Allowing recursion now and
  withdrawing it later would break every document that used it. When a
  restriction is cheap to lift and expensive to impose retroactively, impose
  it first.

### Working within it

Where an expression genuinely needs nesting, split it:

- `ALL(context, ANY(trigger_a, trigger_b))` becomes a chain `ANY(trigger_a,
  trigger_b)` and — since a chain cannot consume a chain in v1 — either a
  separately governed strategy whose triggers are folded into one atomic, or
  two chains `ALL(context, trigger_a)` and `ALL(context, trigger_b)` governed
  and evidenced separately.

The second form is usually the better answer anyway: it produces two
independently evidenced specialist strategies rather than one compound whose
performance is an average of two different behaviours. That is the portfolio
doctrine of PID lines 191-198 arriving by a different road.

If a case appears where the restriction genuinely blocks a required strategy,
that is a PID escalation — *explicitly authorised* is the PID's own escape
hatch — and not something to route around in a document.

---

## 8. Where the rules are enforced

The **Scope** column says what document the rule actually runs against, because
that is not something a reader should have to infer from a row's position. It
was inferable and it was wrong: *"Every `reason_fields` entry names a real
emitted field"* sat among the chain rows and reads as a chain rule, but the
check is `_check_reason_fields_bound` and it runs only from `check_package`. A
standalone chain declaring `reason_fields: ["htf_context.totally_bogus"]`
validated at exit 0. The scope is stated on every row now rather than fixed on
the one row that was caught, and `tests/test_semantics.py` pins the two
`reason_fields` rows against what the code does.

| Rule | Scope | Enforced by |
| --- | --- | --- |
| Only the four canonical primitives | chain | `chain.schema.json` (closed enum) |
| Inputs are atomic references only; no nesting | chain | `chain.schema.json` (no node `$def`, no self-`$ref`) |
| Identity is id + version, both required | chain | `chain.schema.json` |
| Reason on match and non-match, per input | chain | `chain.schema.json` (`const: true`) |
| `SEQUENCE` has a window and per-input indices | chain | `chain.schema.json` (conditional) |
| `CONTEXT_TRIGGER` has *at least* one CONTEXT and one TRIGGER | chain | `chain.schema.json` (conditional) |
| `CONTEXT_TRIGGER` has *at most* one of each, and no other role | chain | `hsa/semantics.py` |
| `input_id` unique within a chain | chain | `hsa/semantics.py` |
| `sequence_index` contiguous from 1, no duplicates | chain | `hsa/semantics.py` |
| Whether that order is the *correct* order | — | **nothing** — see section 3, "The limit on ordering" |
| `sequence_index` absent on a non-`SEQUENCE` chain | chain | `hsa/semantics.py` |
| Every `input_id` attributed in `reason_fields` | chain | `hsa/semantics.py` |
| Every `reason_fields` entry names a real emitted field | **package** | `hsa/semantics.py` |
| An optional input is never the sole cause of a match | chain | `hsa/semantics.py` |
| CONTEXT timeframe strictly above TRIGGER | chain | `hsa/semantics.py` |
| Input timeframe agrees with the role model | chain | `hsa/semantics.py` |
| Every referenced atomic resolves in the catalogue | chain, with a catalogue | `hsa/semantics.py` |
| Package and embedded chain agree | package | `hsa/semantics.py` |
| Package embeds every atomic its chain names | package | `hsa/semantics.py` |
| Atomic HERMES needs carried up to package level | package | `hsa/semantics.py` |

### Why that one rule is package-scoped and stays that way

It could not be moved without weakening it. An entry binds either as
`<input_id>.<field>`, which needs the field list of the atomic behind that
input, or as a bare name declared in the **package's** `output_contract.fields`
— and a standalone chain document has neither. It references its atomics rather
than embedding them, and it has no package output contract at all. Running the
check at chain scope would mean checking the half that a catalogue can resolve
and silently skipping the other half, which is a row that overstates itself
again in a new way.

What a standalone chain does get is the row above it: every `input_id` must be
attributed in `reason_fields`. That is the part decidable from the chain alone,
and it runs there.

Note the first two `CONTEXT_TRIGGER` rows. "Exactly one CONTEXT and exactly one
TRIGGER" is enforced by the two layers jointly: the schema's `contains` requires
each role to be present, and `hsa/semantics.py` rejects a second one and rejects
any third role. Neither layer states the rule alone.

### Running both halves

```bash
hsa validate path/to/document.json
```

Structural validation runs first, semantic second, and **both run by default**
— for a `chain` and for a `strategy_package` alike. There is no mode of
`hsa validate` that silently checks half a document.

`--structural-only` asks the narrower question of schema conformance and says
on its success line that the semantic half did not run. `--no-catalogue` runs
the checks that do not need the atomic catalogue and names, on stderr, the
check that therefore did not run. If the catalogue is required but cannot be
loaded, the command fails (exit 3) rather than passing a document it did not
finish checking. **A check that could not run is never reported as a check
that passed.**

`hsa chain` remains the command that *explains* a composition, and it accepts
either a `chain` document or a `strategy_package` — real chains live embedded
inside packages, so refusing a package meant the only chains that actually
exist could not be inspected without cutting them out to a temporary file by
hand. On a package it runs the chain checks and says on stderr which
package-level checks it left to `hsa validate`.

Semantic failure exits 1 — the same "read but failed validation" code as a
schema failure — and reports in the same `path: message` form.

---

## Related doctrine

- `contracts/README.md` — the frozen contract set and its structural
  prohibitions.
- `catalogue/README.md` — the atomic strategy catalogue and its authoring
  rules.
- `docs/AMBIGUITY-POLICY.md` — when a discretionary term becomes a declared
  parameter and when it must be escalated instead.
