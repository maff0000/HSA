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

PID line 114 lists "large wick" among the phrases that **must not be
guessed** (the list runs from line 114 to line 118; line 117 is
*"confirmation candle"*). PID line 242 then builds acceptance Example B directly on
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
  sentence the term sits in, plus `sentences_after` sentences following it.
  The window **bounds the search**; it does not decide the outcome.
- **`basis_qualifier_policy.attachment`** — which of the qualifiers found
  there actually count. This is the ruling that decides refusals, and it is
  described in full in the next section.

A term whose window contains a declared qualifier **that is attached to the
ruled measurement** does not resolve. It becomes a `BLOCKING` unresolved item
in a `STRATEGY_NOT_SUFFICIENTLY_DEFINED` result, naming the ruled basis, the
constructions that displaced it, and the decision needed to settle which
basis governs. Its `source_language` quotes the **full qualifying context**,
not the matched phrase — quoting only "large wick" would hide the very words
that caused the refusal.

### What attaches a qualifier to a ruled term

Finding a qualifier in the window is **not** enough to refuse. A qualifier
re-bases a ruled term only when it is syntactically attached to the ruled
measurement. Three declared forms attach, and nothing else does:

| Form | What it is | Example |
| --- | --- | --- |
| `SLOT` | The qualifier sits in the term's own modifier slot — the `basis_slot` group every `PARAMETERISE` pattern must declare, being the run of words the pattern tolerates between its ruled adjective and its ruled head noun. Any category attaches here. | *"a large **ATR** wick"*, *"a larger **than average** wick"* |
| `COMPLEMENT` | A `COMPARATIVE` qualifier stands as the term's own complement, separated from it only by declared filler. A comparative is the connective that binds a yardstick to a measurement. | *"a large wick **relative to** the recent average"* |
| `GLOSS` | The source restates one of the term's **own matched words** and then defines it. Naming the ruled word is what attaches the gloss. | *"a large wick, and **by large I mean** twice the 14-period ATR"* |

`SLOT` is why hits **inside** the term's matched span are inspected rather
than discarded. A `PARAMETERISE` pattern contains a wildcard, and the wildcard
is exactly where a re-basing lands: *"a larger than average wick"* matches
`large_wick` **in its entirety**, so the qualifier falls inside the match.
Dropping inside-span hits as "part of the ruled phrase the lexicon already
declares" was false, and it made the guard's behaviour flip on word order —
*"a wick larger than the average"* refused while the more natural *"a larger
than average wick"* resolved.

### What is deliberately **not** a re-basing

The guard is tuned for **precision, not recall**. These are ordinary, correct
trading descriptions, and every one of them resolves:

| Source | Why it is not a re-basing |
| --- | --- |
| *"Enter on a large wick. The setup expires within 3 bars."* | The bar count is an **expiry**, which PID line 137 requires a package to state. |
| *"Enter on a large wick. My stop is 2 ATR below entry."* | The ATR sizes the **stop**, not the wick. |
| *"Enter on a large wick above the 200 period moving average."* | The average is a **trend filter**; the wick is placed against it, not measured by it. |
| *"Enter on a large wick that clears the previous bars' high."* | The prior bar supplies a **price level**, not a yardstick. |

Refusing these is not caution — it is a defect. The refusal advises
*"restate the source without the re-basing language"*, which for *"expires
within 3 bars"* means deleting an expiry the PID **requires**. And because
`"after 4 bars"` matched the declared lookback pattern while `"after four
15m bars"` did not, two sources with **identical meaning** produced opposite
outcomes on a spelling difference; acceptance Example B passed only by that
accident. `tests/test_ambiguity.py` now pins the pair to agree.

**What makes precision safe here** is that the guard is not the only thing
telling the truth. Every resolution it permits still carries
`source_basis_agreement: NOT_VERIFIED`, which declines to certify that the
source agrees with the ruled basis, and now also lists under
`declared_qualifiers_seen_unattached` the qualifiers that were found and
deliberately passed over. A precise guard beside an honest disclaimer is a
coherent design. A recall-maximising guard that refuses required expiries is
not — and its clean-scan stamp is *less* trustworthy, not more, because the
filtering behind it is unprincipled.

One term, one ruling: if any occurrence of a ruled term in a source is
re-based, the term does not resolve anywhere in that source. Its parameter
would be declared once for the whole draft and there is no coherent way to
half-declare it, so it fails in the closed direction.

### What it cannot do, stated plainly

This is a **surface-pattern check over a declared vocabulary inside a
declared window**. It is not comprehension, and general detection of
re-basing in natural language is not achievable this way.

These are the real misses. Some are accidents of a surface vocabulary; the
last group are **deliberate**, and they are listed here rather than implied
away:

- A re-basing phrased in words the vocabulary does not declare passes it.
- A re-basing attached by a connective the `COMPLEMENT` form does not list
  passes it.
- A gloss phrased outside `gloss_constructions` passes it, and so does one
  stated further away than `window.sentences_after`.
- A re-basing that modifies the term from the **left** — *"an ATR-relative
  large wick"* — passes it.
- A yardstick that genuinely governs the term but reads, on the surface,
  exactly like the location and expiry prose in the table above passes it
  **on purpose**. That is the price of not refusing the four legitimate
  sources listed there, and it is paid knowingly.

So a term that survives the check is **not proven** to carry the ruled basis.
It is a term in which no *attached* declared re-basing was found. That is a
narrower claim, and it is the one the output now makes — which is why the
scan result reads `NO_ATTACHED_REBASING_FOUND` and not
`NO_DECLARED_REBASING_FOUND`. The older name asserted that the window held no
declared re-basing at all, which is knowingly false whenever the guard passes
over an ATR stop or a bar-count expiry: a stamp claiming more than the check
established, which is the same class of defect as the `hsa_guessed: false`
field this document already removed.

## A wildcard slot is not ruled text

A term's pattern is part literal and part wildcard. The literal parts are the
phrase this document rules on. The `basis_slot` group is a **wildcard run of
words that merely sits between them**, and nobody has ruled on those words at
all.

The analyser stops scanning inside a ruled term's match — a phrase this
document has settled should not also be reported as an open question. That is
right for the literal parts and **wrong for the slot**, and the consequence was
the worst kind of defect this document exists to prevent: a silent one.

```
"XAUUSD 15m. I enter on a large near resistance wick."
  -> exit 0, resolved "large near resistance wick", nothing unresolved
```

`"near resistance"` is one of the five phrases **PID line 115** says must never
be guessed. On its own it refuses, correctly. Between `"large"` and `"wick"` it
disappeared — no refusal, no advisory, no mention — because it fell inside a
span the analyser had already written off as ruled. The same hole swallowed all
sixteen declared marker families and a second must-not-guess phrase, and no
shipped fixture triggered it, which is why the suite stayed green through two
audits.

That also broke the guarantee the *previous* section leans on. The re-basing
guard is tuned for precision and misses on purpose; what made that safe to ship
was that unknown terms fail closed underneath it. They did not.

Two rules close it, and both are enforced on **every** term rather than on the
patterns that happened to expose the problem:

1. **Only the literal parts of a match suppress further scanning.** Slot
   contents are scanned like the ordinary prose they are. A REFUSE term or a
   discretionary marker sitting in a slot is reported exactly as it would be
   anywhere else in the source. `basis_qualifier_policy.attachment` already
   treated the slot as scannable for re-basings — its `SLOT` form is *only*
   about what is in there — so this extends one existing idea rather than
   adding one.

2. **A term match may not span a sentence boundary.** The same wildcard let a
   match run across a full stop and take the next sentence's opening words with
   it (`"a large trade. some wick setups only"` matched `large_wick`), hiding
   everything it swallowed. So such a match is not accepted as a ruling: it
   resolves nothing and suppresses nothing, and everything on the far side of
   the boundary is still scanned. A terminator with a word character on **both**
   sides is inside a token rather than between two sentences, so `1.5`, `m.a`,
   `h.4` and `a.m` are each one token, while `"trade. some"` still ends a
   sentence. **Declining to read a match is not permission to delete it** — see
   "A recognised term is never deleted, only reported" below, which is where
   this rule spent four audits being wrong.

### Why a PARAMETERISE term whose slot is unresolved does not resolve

Surfacing the hidden refusal is not enough on its own. The words in the slot
**modify the measurement** — that is what a modifier slot is — so undefined
language there is undefined language about the very thing being measured.
Declaring `min_wick_to_range_ratio` over the top of *"large near resistance
wick"* would attach a bounded parameter to a quantity the source has not
finished describing. So the term does not resolve, and the draft says why,
naming the term, the slot text and what was found in it
(`term_match_policy.unruled_slot_content`).

### Why this is structural rather than four tightened patterns

Both rules could have been written as regex fixes — forbid `.` in the slot's
character class, enumerate the words a slot accepts. That would have fixed the
four patterns that exist today and nothing else. Instead:

- The sentence-boundary rule is enforced **on the match**, in the analyser, so
  it holds for a term nobody has declared yet. The patterns are tightened as
  well, and `tests/test_ambiguity.py` proves the rule still holds when a
  pattern is *not* tightened, by running a deliberately loose fixture lexicon
  through it.
- The loader **refuses to load** a term whose pattern contains a wildcard
  outside the declared `basis_slot` group. The analyser can only decline to
  treat wildcard text as ruled if it can see where the wildcard is, and the
  named group is the only thing that tells it. An undeclared wildcard is
  therefore not a style problem; it is this defect, re-armed, and the lexicon
  simply does not load.
- The slot check is a **direct scan**, not a filter over what the main passes
  accepted. The main passes resolve overlaps, so a refusal that overlapped the
  ruled term *both* ways — partly in the slot, partly sharing its head noun —
  lost that contest and vanished anyway: `"no wick confirmation candle"`
  resolved at exit 0 while containing PID line 117's *"confirmation candle"*
  verbatim. Asking the narrower question — *is there unresolved language
  touching this match?* — does not care who won the overlap.

## Overlap resolution never deletes a refusal

The section above scoped its fix to the **wildcard slot**, because the slot was
where the defect had been found. A fourth audit found the fifth phrasing, and
it does not use the slot at all:

```
"XAUUSD 15m. I enter on a no-wick close to resistance."
  -> exit 0, resolved "no-wick close", nothing unresolved

  control: "XAUUSD 15m. I enter close to resistance."  -> exit 4, near_resistance
  control: "XAUUSD 15m. I enter near resistance."      -> exit 4, near_resistance
```

`no_wick_candle` lists `closes?` among its **literal head nouns**. It claims
the word *"close"*, which is also where `near_resistance` starts. The analyser
collects every match and then resolves overlaps by a fixed rule — leftmost,
then longest, then lexicon order — and the loser was discarded. So
`near_resistance`, a **PID line 115** must-not-guess phrase, lost a sorting
contest and left no trace: no refusal, no advisory, no mention. The controls
show it fires perfectly well on its own. It was deleted, not missed.

That is the same silent path as the slot bug and as the two before it. Three
repairs each fixed the phrasing in front of them; this one states the rule they
were all instances of:

> **Overlap resolution may decide which term *resolves*. It may never cause a
> recognised REFUSE term or a declared marker to go unreported.**

Two consequences, both enforced on the match in `hsa/intake/analyser.py` and
both declared in `term_match_policy.overlap_resolution`:

1. **Suppression requires coverage, not overlap.** A match is treated as
   "already ruled on", and dropped, only when the accepted rulings cover it
   **end to end**. Partial overlap is not a ruling — it is two readings of one
   stretch of text — so both are kept and reported. This is also why *"a
   no-wick close to the 200 period moving average"* now reports its proximity
   claim: `"close to"` straddles the ruled word `"close"`, and half a ruling is
   no ruling.

2. **A contested ruled term does not resolve.** Where a PARAMETERISE phrase and
   a REFUSE phrase claim the same words, which one the source means is exactly
   what is undefined, so **REFUSE wins outright**: the refusal is reported on
   its own terms, and the ruled term is itemised as a contested match that
   resolves nothing. The same holds when *both* rulings are PARAMETERISE — *"a
   large no-wick candle"* is `large_wick` and `no_wick_candle` over the top of
   one another, and they contradict each other; declaring the threshold that
   happened to sort first would put a number on a contradiction the source has
   not settled.

The scan that finds these collisions asks about the **whole matched span**, its
literal head nouns included, rather than the wildcard slot alone. Scoping it to
the slot is what left this open, and scoping is what a sixth phrasing walks
around.

### How this is proved rather than asserted

`tests/test_ambiguity.py` does not hand-write the sources it checks. It
**generates** them from the declared patterns: a bounded sample of the phrases
each pattern can spell, crossed with every REFUSE term and every marker family,
with each probe placed at every position relative to the ruled phrase — before
it, after it, in every gap between its words, and *sharing* one of its literal
head nouns. Several thousand sources, generated from the lexicon, and for every
one of them: every term and every marker the lexicon can find is either
resolved, or covered end to end by an accepted ruling, or named in the emitted
refusal. There is no fourth outcome and no silent one.

**A bounded sample, not an exhaustive enumeration.** This document called it
exhaustive and it never was, which matters because the gap is where a defect
sat. Three declared bounds, all deterministic and all in `_phrases`:

- a character **range** contributes its first character only, so `[a-z]` spells
  `a`;
- a **repetition** is spelled zero times and once, never more;
- the enumeration **stops at 400 phrases** per pattern.

`near_resistance` alone can spell more than 25,000 phrases and 400 are taken,
so this is not a rounding difference. A fourth bound was worse than a bound: an
`IN` node spelled only its **first** alternative, so every term pattern joins
its words with `[ -]` and the corpus contained **zero hyphens** — while the
phrasing the fourth audit reported was hyphenated. That one is now fixed rather
than declared: an `IN` node spells all its literal alternatives.

The corpus also generated no sentence terminator and no dotted token anywhere
near a ruled phrase, which is exactly why several thousand sources could not
see the boundary defect below. A second generated corpus now covers that
region specifically: every ruled phrase with a dotted token (`m.a`, `h.4`,
`a.m`, `1.5`) and with each declared terminator placed **inside** it, at every
gap between its words. Both corpora assert the same property.

The previous class-level test hand-wrote its carriers and passed while this
defect was live, because every carrier it contained injected into the slot —
the bug that had just been fixed. That is the difference between a corpus and a
list of the sentences somebody remembered.

The test is checked for vacuity by putting the defect back: restore the
slot-scoped scan and the overlap-based suppression, and the generated corpus
fails on the shipped phrasing. `tests/fixtures/intake/lexicon_collision.json`
goes further — a lexicon whose patterns collide **on purpose**, with `closes?`
declared as a head noun of a PARAMETERISE term whose REFUSE neighbour begins
`"close to"`. Nothing in it has been written carefully, and the guarantee holds
anyway, because it is not the patterns that hold it.

## A recognised term is never deleted, only reported

Four repairs, each closing one path and leaving another, and five independent
audits reporting what is in the end a single root cause: **a recognised term
was deleted without being reported.** Exactly three rules can stop a recognised
match resolving, and after the first two repairs they looked like this:

| rule | declares a disposition? | emits a finding? |
|---|---|---|
| `unruled_slot_content` | yes — `REFUSE`, `BLOCKING` | yes |
| `overlap_resolution` | yes — `REFUSE`, `BLOCKING` | yes |
| `sentence_boundary` | **no** | **no — the match was discarded** |

The third one had a rule, a terminator set and a rationale, and no consequence
at all. What it did instead of reporting was `continue`, and the effect was the
same silent exit 0 as the four phrasings before it:

```
"XAUUSD 15m breakout rules.

I only take a valid m.a breakout of the range."
  -> exit 0, STRATEGY_INTAKE_DRAFT, nothing unresolved

  control, identical minus the dotted token:
  "... I only take a valid breakout of the range."
  -> exit 4, [BLOCKING] good_breakout
```

`good_breakout` is a **PID line 118** must-not-guess phrase, and the pattern
matched in both cases — this was deletion, not non-recognition. The entry was
the decimal exception being too narrow: only digit-`.`-digit was exempt, so
`m.a`, `h.4`, `4.hour`, `vwap.session` and `a.m` each read as a sentence ending
mid-word and any match spanning one was judged to cross a boundary. Those are
the abbreviations **PID lines 104-105** intake actually receives. The
`PARAMETERISE` side leaked the same way with no adjective anywhere in the term:
`no_wick_candle` contains no marker word at all, so *every* boundary-crossing
match of it vanished without even a marker left behind to notice.

Two things are wrong there and only one of them is the tokenisation. The rule
itself was stated as a single decision when it is two:

> **Declining to read a match as a ruled term is not permission to delete it.**
> The two decisions are separate and only the first was ever justified.

So a boundary-crossing match is now **refused and reported**, exactly like the
other two rules: it is not accepted (nothing is suppressed, and everything on
the far side of the boundary is still scanned freely, which is the concern that
originally justified discarding it), and it is itemised, with the straddling
span quoted so a reader can see what happened. `sentence_boundary` declares its
`disposition`, `severity`, `blocks`, `why_unresolved_template` and
`resolution_needed` like the other two, and the loader **requires** them: a
lexicon declaring a rule with no consequence no longer loads.

### The general statement, and a choke point that enforces it

R7 stated its rule as *"overlap resolution may never cause a recognised term to
go unreported"*. That is one word too narrow, and the missing word is why a
fourth repair was needed:

> **Nothing may cause a recognised term to go unreported.**

Stating it is what the previous four repairs also did. What is different is
that it is now **enforced structurally rather than promised**. Every recognised
match is written into a ledger the moment it is recognised, carrying exactly
one reason it is accounted for, from a closed set:

`REPORTED_AS_TERM`, `REPORTED_AS_REBASED`, `REPORTED_AS_UNRULED_SLOT`,
`REPORTED_AS_CONTESTED`, `REPORTED_AS_STRADDLING_A_SENTENCE_BOUNDARY`, and
`COVERED_END_TO_END_BY_AN_ACCEPTED_RULING`.

Before `analyse` returns, every entry in that ledger is checked against the
findings **actually emitted**: a reason naming a finding kind must find its
term in that collection, and the coverage case must still be covered when
re-tested. There is deliberately **no reason meaning "dropped"**. A sixth
deletion path added by a future edit either declares a reason and emits a
finding for it, or every source that exercises it raises
`UnreportedMatchError` — loudly, in the caller's face, instead of drafting at
exit 0 with `analyser_limits` claiming nothing recognised survived unruled.

That is the difference between this repair and the four before it. Each of
those closed the door it could see. This one makes opening a new door fail.

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
  (`NO_ATTACHED_REBASING_FOUND`), and the scan's own declared `limits`;
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

Replacing that vocabulary's fire-on-any-co-occurrence rule with the
`attachment` ruling above changed which sources resolve again — in **both**
directions, since it both stopped refusing legitimate expiries, stops and
trend filters and started catching re-basings inside a term's own matched
span. So the lexicon moved from **1.2.0** to **1.3.0**, and every
`PARAMETERISE` pattern now declares a `basis_slot` group, which the loader
requires rather than assumes.

Ruling that a term's wildcard slot is not ruled text changed which sources
resolve again — `"a large near resistance wick"` refuses now and did not
before — and added a fourth ruling block, `term_match_policy`. So the lexicon
moved from **1.3.0** to **1.4.0**, and every term pattern's wildcard is now
declared as a `basis_slot` group, including the two `REFUSE` patterns that
carried an undeclared one.

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

That defence is deliberate and it holds, but it rests on a reader noticing a
version number. So this paragraph is the **in-document superseded marker**:
lexicon 1.0.0 is superseded four times over (1.1.0, 1.2.0, 1.3.0, 1.4.0), and any
draft or package citing it — `wick_rejection_sequence/0.1.0` is the only one
in the inventory — records a ruling that has since moved. The marker is
placed **here**, in the governing document, rather than written into the
package: editing the package's own provenance to say it is stale would
change a historical record, which is exactly what the paragraph above
forbids.

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

That sentence was **false for three audits**, and the way it was false is
instructive: nothing failed, nothing was reported, and the guarantee read
exactly as it does now. A term's wildcard slot swallowed recognised
discretionary language and the scan never looked inside — see "A wildcard slot
is not ruled text". So the claim is no longer left as prose to be trusted.
`tests/test_ambiguity.py` asserts it directly, over generated corpora that drop
every declared marker family and every `REFUSE` term into every position
relative to every ruled phrase, and that place a terminator or a dotted token
inside the ruled phrase itself: for each one, every recognised term of **either
disposition** either resolves, or is genuinely inside a term's LITERAL span, or
is reported. The `PARAMETERISE` half of that was missing until R8, and it is
the half `no_wick_candle` fell through. A guarantee that only a human can check is a
guarantee that stays broken quietly.

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
4. Either way, if the pattern accepts words the lexicon does not enumerate,
   **wrap that run in the `(?P<basis_slot>...)` group**. It is not optional and
   it is not style: it is the only thing that tells the analyser which part of
   a match is ruled text and which part is wildcard, and the loader refuses a
   term pattern whose wildcard sits outside it. See "A wildcard slot is not
   ruled text" for what an undeclared one costs.
5. If unsure — **leave it out**. An absent term refuses. That is the safe
   direction, and it is the direction the design deliberately falls in.
