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

Note that a parameterisable term can still become a refusal when its
context removes the basis. "Large wick relative to the recent average" is
not the same claim as "large wick" — it introduces a lookback that the
lexicon's single-bar basis does not cover. The lexicon rules on the phrase
it declares; anything that changes the basis is a different term, and an
undeclared term refuses (see "Unknown terms fail closed").

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
- `hsa_guessed: false` — the claim made explicit so it can be audited;
- `default_status: "PROVISIONAL_PENDING_EVIDENCE"`.

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
   file that a human can read and correct rather than in code.

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
