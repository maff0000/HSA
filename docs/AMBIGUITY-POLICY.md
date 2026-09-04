# HSA ambiguity policy

**Status: ratified. This document is the authority.** Other work items,
schemas and code cross-reference it by this exact path
(`docs/AMBIGUITY-POLICY.md`). A fresh HSA boot reads it and applies the same
boundary without Matt present. Changing the boundary is a governance
decision, not an implementation detail.

It answers one question: when HSA meets discretionary trading language,
does it **parameterise** the term, or does it **refuse** with a
`STRATEGY_NOT_SUFFICIENTLY_DEFINED` result?

## The tension this resolves

The PID says two things that look contradictory.

PID line 117 lists phrases that **must not be guessed**, and "large wick" is
one of them. PID line 242 then builds acceptance Example B directly on
*"large 15m rejection wick"*, and PID line 288 requires that example to pass
acceptance.

Read naively, only one can hold:

- If every discretionary phrase triggers refusal, Example B can never pass.
- If ambiguity is always parameterised away, acceptance criterion 3 —
  "identify ambiguity rather than guessing" (PID line 252) — becomes
  untestable, because nothing would ever be identified.

The PID resolves this itself. Line 110: *HSA must turn discretionary
language into measurable definitions.* Line 120: HSA returns
`STRATEGY_NOT_SUFFICIENTLY_DEFINED` **when material ambiguity remains**.

Conversion is the default obligation. Refusal is for what survives
conversion. The word doing the work is **material**.

## The boundary

> **Parameterise** a term whose **measurement basis is known** but whose
> **threshold is unset**.
>
> **Refuse** a term whose **measurement basis is itself undefined**.

That is the whole rule. It turns on *measurement basis*, not on how vague
the wording sounds.

**Measurement basis** means: the quantity to compute, and the HERMES facts
to compute it from. If HSA can name the quantity without inventing trading
semantics, the basis is known, and what is missing is only a number — a
number that belongs in a bounded parameter, subject to evidence, exactly as
PID line 140 requires. If naming the quantity would itself require HSA to
decide something about markets that the source never said, the basis is
undefined, and no parameter can be declared without HSA guessing. PID line
39 forbids that. So HSA refuses, and says precisely what it needs.

Two consequences worth stating plainly:

- **Vagueness of wording is not the test.** "Large wick" sounds vague and is
  parameterisable. "Confirmation candle" sounds technical and is not.
- **A parameter is not a guess made quietly.** The difference between a
  parameter and a guess is not the value — it is whether the value is
  *declared, bounded, attributed and revisable*. See "Attribution" below.

## The PID's own examples, classified

These are the five phrases named at PID lines 114-118, plus the one Example
B additionally depends on. Each is a live entry in the declared lexicon at
`hsa/intake/lexicon.json`; this table and that file must agree, and a test
enforces that they do.

| Phrase | Ruling | Measurement basis | Why |
| --- | --- | --- | --- |
| **"large wick"** (PID 114) | **PARAMETERISE** | Wick length as a fraction of the candle's total range. | Both quantities are unambiguous HERMES facts on a single bar: the wick length and the bar's high-minus-low. Nothing outside the bar is needed, no level must be constructed, no lookback chosen. Only the cut-off is missing, and a cut-off is a parameter. |
| **"no-wick candle"** (PID 55, needed by Example B) | **PARAMETERISE** | The larger wick as a fraction of the candle's total range, capped near zero. | Same single-bar basis as above, read in the opposite direction. "No wick" cannot mean *exactly* zero on real data, so the tolerance is a bounded parameter. |
| **"near resistance"** (PID 115) | **REFUSE** | *Undefined.* | Two separate things are missing, and neither is a threshold. First, **resistance is not constructed**: which swing, over what lookback, on which timeframe, a single price or a zone. Second, **"near" has no reference to be near to** until the first is settled. HSA cannot pick a swing-detection method without inventing trading semantics the source never stated. There is no parameter to declare, because there is no quantity yet. |
| **"strong trend"** (PID 116) | **REFUSE** | *Undefined.* | "Trend strength" names no quantity. ADX, moving-average separation, slope of a regression, count of consecutive higher highs and net displacement over a lookback are all defensible readings, and they disagree on real data — they can rank the same two charts in opposite orders. Choosing among them is a trading decision, not a threshold. Once the construction *is* chosen, its cut-off becomes an ordinary parameter. |
| **"confirmation candle"** (PID 117) | **REFUSE** | *Undefined.* | Nothing here says what confirms, or what is confirmed. Engulfing, close beyond a prior extreme, close in the top third of the range, a second bar in the same direction — all are "confirmation candles" to some trader. The pattern itself is the missing definition. Contrast Example B's *"no-wick directional confirmation"*, which does name the pattern: there, "confirmation" is a **role label** on a defined pattern, and the pattern resolves. |
| **"good breakout"** (PID 118) | **REFUSE** | *Undefined.* | "Breakout" alone is definable, but "good" does not attach to a stated quantity. It could mean closing beyond the level rather than wicking through, expanded volume, follow-through on the next bar, or absence of an immediate return inside. These are different mechanical tests, not different settings of one test. |

Four refusals, two parameterisations. That distribution is the point:
acceptance criterion 3 stays testable because most of the PID's named
phrases genuinely refuse, and Example B still passes because the two it
depends on genuinely resolve.

## Why "large wick" resolving is not a loophole

The obvious objection: could this reasoning be stretched to resolve
anything? No, and the reason is checkable rather than rhetorical.

Ask what HSA must supply to make the term measurable:

- **Only a number, from a basis the source already implies** →
  parameterise. For "large wick", the source said *wick*, and a wick has
  exactly one natural relative measure on its own bar.
- **A choice between materially different constructions** → refuse. For
  "strong trend", the source said *trend*, and HSA would have to pick which
  of several disagreeing constructions "trend" means before any number could
  exist.

The test is therefore mechanical: *can the quantity be named without
choosing between constructions that disagree on real data?* If yes, the
basis is known. If no, it is undefined, and that is material ambiguity.

## A ruled term can be re-based by its context

A parameterisable term still becomes a refusal when its context removes the
basis. "Large wick relative to the recent average" is not the same claim as
"large wick" — it introduces a lookback that the lexicon's single-bar basis
does not cover. The lexicon rules on the phrase it declares; anything that
changes the basis is a different term, and an undeclared term refuses (see
"Unknown terms fail closed").

**This paragraph used to stand alone, and nothing implemented it.** The
worked example above resolved at exit 0, and so did a source that said in as
many words that the wick had to be *twice the 14-period ATR* and that *the
bar range is irrelevant*: HSA applied its own bar-range basis over the top,
emitted `candle.range` as a required HERMES input, raised nothing, and
stamped the resolution `hsa_guessed: false`. Under PID line 148 FORGE would
have implemented `wick / bar_range >= 0.6` for a trader who specified
`wick >= 2 x ATR`. A document that is itself the authority (PID line 206)
cannot assert a guard that does not exist, so the guard now exists. What
follows is what it does, and — the more important half — what it does not.

### What runs

Before a `PARAMETERISE` term is allowed to resolve, the text around it is
scanned for constructions that name a **different measurement basis**. Both
halves of that scan are declared as data in `hsa/intake/lexicon.json`, for
the same reason the rulings themselves are:

- **`basis_qualifiers`** — the vocabulary. Each entry has a
  `qualifier_id`, a `category` (`COMPARATIVE`, `LOOKBACK`,
  `ALTERNATIVE_BASIS`, `NEIGHBOUR`), a human `reason` and a `pattern`. It
  covers comparative constructions (*relative to*, *compared to*, *versus*,
  *against the average*), lookbacks (*recent*, *the average*, *a rolling
  mean*, *over the last N bars*, *N-period*) and alternative bases (*ATR*,
  *true range*, *standard deviation*, *twice the …*, *in pips*, *the other
  candles*, *its neighbours*).
- **`basis_qualifier_policy.window`** — how much text is inspected: the
  sentence the term sits in, plus the sentence after it. The window size is
  the reviewable half of the guard, so it is declared rather than chosen in
  code: widen it and more innocent prose refuses, narrow it and more
  re-basing is missed.

A term whose window contains a declared qualifier does not resolve. It
becomes a `BLOCKING` unresolved item in a `STRATEGY_NOT_SUFFICIENTLY_DEFINED`
result, naming the ruled basis, the constructions that displaced it, and the
decision needed to settle which basis governs. Its `source_language` quotes
the **full qualifying context**, not the matched phrase — quoting only "large
wick" would hide the very words that caused the refusal.

One term, one ruling: if any occurrence of a ruled term in a source is
re-based, the term does not resolve anywhere in that source. Its parameter
would be declared once for the whole draft and there is no coherent way to
half-declare it, so it fails in the closed direction.

### What it cannot do, stated plainly

This is a **surface-pattern check over a declared vocabulary inside a
declared window**. It is not comprehension, and general detection of
re-basing in natural language is not achievable this way.

- A re-basing phrased in words the vocabulary does not declare passes it.
- A re-basing stated further away than the declared window passes it.
- A construction it does recognise in innocent prose refuses a term that
  should have resolved. That direction costs one round trip; the other costs
  the audit trail, which is why the design leans this way.

So a term that survives the check is **not proven** to carry the ruled basis.
It is a term in which no *declared* re-basing was found. That is a narrower
claim, and it is the one the output now makes.

## Attribution: a parameterisation is never silent

A parameterised term must be **visible and attributable in the output**.
Every parameterised resolution in an intake draft carries:

- `disposition: "PARAMETERISED"` — stated, not implied by absence;
- the `source_language` quoted verbatim, and where it appeared;
- the `measurement_basis` it was resolved onto, in words;
- the `declared_parameters` it produced, each with default, allowed range
  and units per PID line 140;
- `authority: "HUMAN_ARCHITECT_RULING"` with `ruling_document` pointing at
  this file, and the `lexicon_term` and `lexicon_version` that supplied it;
- `basis_authority: "RATIFIED_LEXICON_RULING"` and
  `hsa_invented_basis: false` — the claim that is genuinely verified: the
  measurement basis came from a ruling in the lexicon, not from HSA;
- `source_basis_agreement: "NOT_VERIFIED"` — the claim that is not, and
  cannot be, verified in general: whether the source agreed with that basis;
- `basis_conflict_scan` — what was actually run against the source: the
  declared vocabulary, the number of qualifiers in it, the lexicon version,
  the window rule, the verbatim text inspected, the `result`
  (`NO_DECLARED_REBASING_FOUND`), and the scan's own declared `limits`;
- `default_status: "PROVISIONAL_PENDING_EVIDENCE"`.

**There is no `hsa_guessed` field, and its absence is deliberate.** It was
emitted as `false` on every resolution. That was an overclaim: what had been
checked was that the basis came from a ratified ruling; what had not been
checked, at all, was whether the source said something different. The two
claims are now separated and each is emitted at the strength it actually
holds. The old key was **removed rather than redefined**, so a consumer still
reading it fails loudly instead of reading a changed meaning out of a
familiar name. A resolution recorded under an earlier lexicon version — such
as the provenance note in `strategies/wick_rejection_sequence/0.1.0` — keeps
the words it was written with; it is a record of what was emitted then, not a
claim about what is emitted now.

That last field is the honest part, and it deserves stating outright. **What
this policy ratifies is the measurement basis, not the default value.** The
basis is a governance decision recorded here and reviewable in the lexicon.
The default is a bounded starting point, and it must be settled by CER
evidence before a strategy version is promoted (PID lines 143, 189, 198). A
default that shipped unchanged and unevidenced into a promoted strategy
would be a guess wearing a parameter's clothes; flagging it provisional,
bounding its range and requiring evidence is what stops that.

Downstream consumers can therefore always answer "who decided this, and is
it settled?" from the document alone.

## From ruling to realisation

A ruling that nothing implements is paperwork. This section states how a
parameterised term reaches the atomic strategy that runs it, and what must
stay true between them.

Intake and the catalogue are two halves of one ruling, written in two files:

- `hsa/intake/lexicon.json` declares the ruled term, its measurement basis
  and its bounded parameters. It is what a raw source is scanned against.
- `catalogue/atomic/<strategy_id>.json` declares the atomic strategy that
  computes the basis and applies the threshold. It is what FORGE implements.

They do not share a naming convention and are not meant to. Intake names a
parameter after the phrase it resolves — `min_wick_to_range_ratio`. The
catalogue names it after the quantity and the comparator —
`wick_to_range_ratio_min`. Both conventions are internally consistent, and
renaming either side would change a promoted catalogue identity, which
`docs/VERSIONING.md` forbids in place.

So the correspondence is **declared, not inferred**. Every parameterised
lexicon term carries a `realised_by` entry naming the catalogue
`strategy_id`, `strategy_version` and parameter that implements it.
`tests/test_lexicon_catalogue_agreement.py` fails if that link points at
something that does not exist, or if the two sides disagree on **type,
units, default or allowed range**.

The allowed range matters as much as the default, and it is the half that
had silently diverged. Intake declared `min_wick_to_range_ratio` as 0.3-0.9
on a 0.05 grid while the realisation accepted 0.3-0.95 with no grid, and
declared `max_wick_to_range_ratio` as 0.0-0.25 while the realisation
accepted 0.0-0.3. Neither side's bound carries evidence — what this document
ratifies is the basis, never the value — so the narrower bound was not a
safeguard, it was an unratified extra restriction on a ratified basis, and
the grid was a claim about permitted values that the thing actually running
did not enforce. A CER sweep of the realisation could therefore have
produced evidence for a value intake called impermissible. **The realisation
is the reconciled side**: its bounds are the ones reasoned about alongside
the other parameters of the same bar, and they are now declared identically
in both files.

### The lexicon is versioned, and citations are pinned to a version

Reconciling those bounds changed a declared ruling, so
`hsa/intake/lexicon.json` moved from `lexicon_version` **1.0.0** to
**1.1.0**. That is not bookkeeping. An intake draft records the
`lexicon_version` that produced it, and a governed package records the draft
it came from, so a citation of a lexicon version is a claim about what the
ruling said *at that time*.

Adding the `basis_qualifiers` vocabulary and its policy changed which
sources resolve, so the lexicon moved again, from **1.1.0** to **1.2.0**.
Same reasoning: a citation of a lexicon version is a claim about what the
ruling said at that time.

`strategies/wick_rejection_sequence/0.1.0` was ingested under lexicon 1.0.0
and its provenance records the bounds that version declared — 0.3 to 0.9 and
0.0 to 0.25. **That record is history and stays correct as written**: it says
what the intake draft declared, under a named lexicon version, on a named
date. It is not a statement about the current ruling, and it must not be
edited to look like one — the package is a promoted-candidate artefact under
`docs/VERSIONING.md` and rewriting its provenance would destroy the audit
trail this whole document exists to protect. A reader reconciling that
package against today's lexicon should read the version numbers, not assume
they match.

What is *not* history, and is enforced now, is that the package's embedded
`rejection_wick 1.0.0` and `no_wick_candle 1.0.0` carry the same defaults and
the same bounds as the catalogue entries of those identities, and that those
entries agree with the lexicon. Those two chains of equality are what make
the package's claim to a ratified basis checkable.

### Basis fields and derivation fields

The two files also declare different HERMES facts, and this too is
deliberate rather than a defect.

- Intake declares the **basis fields** — the quantities the ruling is
  *stated in*: `candle.wick_upper`, `candle.wick_lower`, `candle.range`.
  Reading the ruling should not require reconstructing a wick from four
  numbers.
- The catalogue declares the **derivation fields** — the raw facts the
  realisation *computes from*: `candle.open`, `candle.high`, `candle.low`,
  `candle.close`, plus `atr`.

The relationship between them is declared in the lexicon as
`hermes_basis_relationship` and is exactly this:

| Basis field (intake) | Derived from (catalogue) |
| --- | --- |
| `candle.wick_upper` | `candle.high - max(candle.open, candle.close)` |
| `candle.wick_lower` | `min(candle.open, candle.close) - candle.low` |
| `candle.range` | `candle.high - candle.low` |

`atr` appears only on the catalogue side. It is not part of the basis: the
atomic entries add a minimum bar range as an ATR multiple so the ratio is
not read off a bar too compressed to carry it. **A realisation may add
guards on top of the ruled basis; it may not change the basis.** The lexicon
declares `atr` as a catalogue-only field with that reason, so the addition
is visible rather than assumed.

`tests/test_lexicon_catalogue_agreement.py` enforces the table above in both
directions: every basis field must be derivable from facts the linked
catalogue entry actually consumes, and every fact that entry consumes must be
either used by a derivation or declared catalogue-only. A field appearing or
disappearing on either side fails the test, so this section cannot quietly
stop being true.

One limit, stated rather than glossed. Whether two prose descriptions name
the *same* measurement cannot be compared mechanically. Each link declares
`basis_phrases` — the words that must survive in both the lexicon's own
statement of the basis and the catalogue's description of the parameter
("wick", "total bar range", and the comparator). That is a canary on the
quantity, the denominator and the direction, not a proof of semantic
identity. It fires on the drift that matters — a re-based ratio, a flipped
comparator — and it does not pretend to more.

## Unknown terms fail closed

The lexicon is finite. Traders are not. So the single most important
property of intake is what happens to a discretionary term the lexicon has
never seen.

**An unrecognised discretionary term is an unresolved item, not a pass.**
It produces a `BLOCKING` entry in a `STRATEGY_NOT_SUFFICIENTLY_DEFINED`
result, exactly as a ruled refusal does. It is never silently carried
through into a draft.

The reason is PID line 39. A term that slips through unflagged does not stay
harmless — it becomes an assumption baked into a governed strategy, and by
the time FORGE implements it, nobody can tell which parts of the
specification were decided and which were absorbed. Refusing an unknown term
costs one round trip. Passing one through costs the audit trail.

## What the analyser actually is, and what it is not

This must be stated plainly, because overstating it would undermine every
guarantee above.

Intake is a **deterministic, rules-based analyser over a declared lexicon**.
It is:

- a set of declared surface patterns in `hsa/intake/lexicon.json`, each
  carrying an explicit ruling under this policy;
- a second declared vocabulary of **discretionary markers** — words and
  constructions that signal qualitative language ("large", "strong", "good",
  "near", "clean", "roughly", …);
- a scan that matches lexicon terms first, then reports every marker
  occurrence **not** already consumed by a ruled term as an unknown
  discretionary term.

It is **not** an LLM call, and it does not understand English. Two limits
follow, and both are real:

1. **It cannot prove a description is unambiguous.** Absence of markers is
   not evidence of precision. A discretionary claim phrased without any
   declared marker will pass unflagged — the analyser has no way to see it.
   A clean intake draft means "nothing HSA recognises as discretionary
   survived unruled", never "this description is fully specified".
2. **It matches surface patterns, so context can fool it.** The lexicon
   pattern is the unit of review; that is precisely why it lives in a data
   file that a human can read and correct rather than in code. One family of
   context error is checked rather than merely admitted: text that re-bases a
   ruled term is caught by the declared `basis_qualifiers` vocabulary and
   refuses (see "A ruled term can be re-based by its context"). That check is
   itself surface patterns inside a declared window, so it narrows this limit
   and does not remove it — which is why a resolution reports
   `source_basis_agreement: "NOT_VERIFIED"` rather than claiming the source
   and the ruling agree.

What it *does* guarantee is narrower and worth having: **nothing the
analyser recognises as discretionary ever passes through without a ruling.**
Every recognised term is either parameterised with visible attribution, or
itemised as unresolved with an owner and a stated resolution. There is no
third path, and no silent one.

Closing that first gap — catching discretionary claims that use no declared
marker — is a matter of extending the declared vocabulary as real sources
expose gaps. It is not a matter of making the analyser cleverer, and it must
not be closed by having HSA infer meaning. Inference is the failure mode
this whole document exists to prevent.

## Applying this to a new term

1. Ask: **can the quantity be named without choosing between constructions
   that disagree on real data?**
2. If yes — add a `PARAMETERISE` entry to `hsa/intake/lexicon.json` with the
   measurement basis, the bounded parameters, the HERMES facts they need,
   and a `basis_rationale`. Add a row to the table above.
3. If no — add a `REFUSE` entry stating why the basis is undefined, what
   `blocks`, and what `resolution_needed` (kind, description, responsible).
   Candidate definitions may be offered; the contract deliberately provides
   no way to mark one as chosen, because choosing is the resolution and it
   happens outside the document.
4. If unsure — **leave it out**. An absent term refuses. That is the safe
   direction, and it is the direction the design deliberately falls in.
