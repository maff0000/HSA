# Atomic strategy catalogue

The registry of atomic strategies HSA can compose. One JSON file per strategy
in `catalogue/atomic/`, each a valid `atomic_strategy` document against
`contracts/atomic_strategy.schema.json`.

This is durable authority: a fresh HSA boot loads this catalogue and knows
what building blocks exist without Matt re-explaining them (PID lines
202-218). It is also the resolution target for chains — `hsa chain` fails a
chain that references a strategy this directory does not hold, at the exact
version pinned.

**These are product proofs, not a claim of profitable strategies** (PID line
244). Every threshold in here was set by the architect and none of it has
passed an evidence gate. Defaults are starting points that CER evidence is
expected to move.

---

## The entries

The third column is **not** one relationship. Only a PARAMETERISE term has a
declared `realised_by` link in `hsa/intake/lexicon.json`, checked end to end by
`tests/test_lexicon_catalogue_agreement.py`; a REFUSE term has no realisation
at all, because its measurement basis is undefined and there is nothing to
realise. What an entry offers a REFUSE term is a measurable construction the
author could *choose*, and HSA never chooses it for them
(`docs/AMBIGUITY-POLICY.md`). The column used to run both together under "the
discretionary term it replaces", which reads as though a refusal had been
answered when it has not been.

| `strategy_id` | Measures | Discretionary term | Relationship |
| --- | --- | --- | --- |
| `golden_cross` | Fast moving average crossing the slow moving average; up is the golden cross, down the death cross. | — | — |
| `range_breakout` | Close beyond a consolidation boundary by a fraction of the range height. | *good breakout* (PID line 118) | one measurable option a refusal could be resolved to; still refused |
| `swing_level_proximity` | Distance from close to the most recent confirmed swing high or low, in ATR multiples. | *near resistance* (PID line 115) | one measurable option a refusal could be resolved to; still refused |
| `rejection_wick` | Wick length, body length and opposing wick length, each as a fraction of the bar range, over an ATR floor. | *large wick* (PID line 114) | **declared `realised_by`** — this is what the ruled parameter is implemented as |
| `no_wick_candle` | Body as a fraction of bar range with both wicks bounded, over an ATR floor. | *no wick* — a proportion, not an absolute | **declared `realised_by`** |
| `engulfing_candle` | Current body length against the prior opposite body length. | — | — |
| `momentum_thrust` | Net close-to-close displacement in ATR multiples, with adverse excursion bounded. | *strong trend* (PID line 116) | one measurable option a refusal could be resolved to; still refused |
| `volatility_expansion` | Short-window ATR over long-window ATR, above a threshold, held for a bar count. | — | — |
| `range_compression` | The same ratio below a threshold, held for a bar count. | — | — |
| `structure_break` | Close beyond the most recent confirmed swing level by an ATR multiple. | — | — |
| `level_retest` | Return to a HERMES-reported broken level within an ATR tolerance and a bar budget. | — | — |

Together they cover every example named at PID line 55.

Two entries deserve a note:

- **`volatility_expansion` and `range_compression`** emit `NEUTRAL` only.
  Volatility says the market is moving further or less per bar; it does not say
  which way. A chain composing either must take direction from another input.
  They are stated on the same two HERMES facts with the comparator reversed,
  so a `SEQUENCE` chain can require compression followed by expansion without
  either strategy knowing the other exists.
- **`level_retest`** takes the broken level from HERMES
  (`level.recent_break_price` and companions), *not* from `structure_break`'s
  output. Reading another strategy's output would make it aware of a peer and
  breach PID line 59. See `docs/COMPOSITION-DOCTRINE.md` §1.

---

## What every entry must satisfy

Beyond the schema, which `tests/test_catalogue.py` enforces mechanically:

1. **File name equals `strategy_id`.** `catalogue/atomic/<strategy_id>.json`.
2. **Identity is unique.** No two entries share a `strategy_id` *and*
   `strategy_version`. Two versions of one strategy are two files.
3. **Every `required_hermes_fields` entry declares a timeframe.** The schema
   makes `timeframe` optional because a package-level declaration may span
   several; a catalogue entry is one strategy on one timeframe and must say
   which (PID line 22).
4. **Every numeric parameter's default lies inside its own `allowed_range`.**
   The schema requires a default and a range but cannot compare them.
5. **Every `enum` and `boolean` parameter's default is one of its
   `allowed_values`.**
6. **At least one matching and one non-matching test case.** A strategy with
   only matching cases has not been shown to discriminate (PID line 49).
7. **No unquantified discretionary language.** See below.
8. **Provenance records that thresholds were architect-set.** `provenance.notes`
   says so explicitly, so nobody later mistakes a default for a result.

---

## The discretionary-language rule

PID line 110: HSA must turn discretionary language into measurable
definitions. PID lines 112-118 name *large wick*, *near resistance*, *strong
trend*, *confirmation candle* and *good breakout* as things that must not be
guessed.

**A catalogue entry containing an unquantified adjective is a defect**, and
this is checked mechanically, not by review. `tests/test_catalogue.py` scans
the human-readable prose of every entry — titles, descriptions, theses, field
purposes, parameter descriptions, direction rules, output field descriptions
and test-case descriptions — against a list of discretionary magnitude,
quality, proximity and hedging terms, and fails on any hit. There are no
per-entry exemptions. The catalogue is written to pass the scan.

So an entry says `wick_to_range_ratio_min`, default `0.6`, units `ratio`,
allowed range `0.3` to `0.95` — never "a large wick".

### The boundary: parameter or escalation

Ratified policy, stated at length in `docs/AMBIGUITY-POLICY.md` and summarised
here because it decides whether something is catalogue material at all:

- A term whose **measurement basis is known but whose threshold is unset**
  becomes a **declared parameter** — with a default, an allowed range, units,
  and provenance recording that the value was architect-set. *Large wick* is
  this case: wick length over bar range is a defined measurement; only "how
  much" was missing.
- A term whose **measurement basis is itself undefined** is **not catalogue
  material**. It must be escalated as a
  `STRATEGY_NOT_SUFFICIENTLY_DEFINED` result naming what is unresolved (PID
  line 120), never guessed into a parameter.

Two limits of the mechanical scan, stated so nobody over-trusts it:

- It catches the *adjective* class of ambiguity. *Confirmation candle* (PID
  line 117) is ambiguous because the word "confirmation" has no agreed
  measurement, not because it contains a vague adjective, and no word list
  will catch it. That class is caught at intake, by the ambiguity policy.
- It scans `catalogue/atomic/*.json` only. This README and the doctrine
  documents legitimately quote the banned terms in order to prohibit them.

---

### The link back to intake

A catalogue entry is not only a building block; for the two terms the
ambiguity policy parameterises, it is the **realisation** of a ruling made at
intake. `hsa/intake/lexicon.json` resolves *large wick* onto
`min_wick_to_range_ratio` and *no wick* onto `max_wick_to_range_ratio`;
`rejection_wick` and `no_wick_candle` implement those as
`wick_to_range_ratio_min` and `wick_to_range_ratio_max`.

The names differ on purpose — intake names the phrase it resolved, the
catalogue names the quantity and the comparator — so the correspondence is
**declared** rather than inferred from matching names. It is declared in the
lexicon, as `realised_by`, naming this directory's `strategy_id`,
`strategy_version` and parameter. The link points one way only: a lexicon
entry may be revised, but a promoted catalogue entry may not be edited in
place, so the mutable side is the side that carries the pointer.

`tests/test_lexicon_catalogue_agreement.py` fails if a link names an entry,
version or parameter this directory does not hold, or if the two sides
disagree on type, units, default or allowed range. That test is the only
thing that reads both files; nothing at runtime does. **Consequences for
anyone editing an entry here:**

- Changing a linked parameter's default, units, type or `allowed_range`
  breaks the agreement test until the lexicon is changed to match. That is
  the intended friction — the number intake hands over must be the number
  this directory implements.
- Renaming a linked parameter breaks the link outright. Under the
  immutability rule below it is a new version anyway, and the lexicon link
  must then be repointed at that version.
- Adding or removing a `required_hermes_fields` entry on a linked strategy
  breaks the declared basis/derivation relationship until the lexicon
  accounts for the change. See `docs/AMBIGUITY-POLICY.md`, "Basis fields and
  derivation fields": intake declares the quantities the ruling is stated
  in, this directory declares the raw facts they are computed from, and
  every fact consumed here is either used by a derivation or declared
  catalogue-only with a reason.

---

## Versioning

Identity is `strategy_id` plus `strategy_version` together, everywhere
(PID line 72). Versions are strict semver and a promoted version is immutable
(PID lines 185-189).

**Never edit a promoted entry in place.** Changing a default, widening a range
or altering a rule produces a *new version* — a new file — that must pass the
evidence gates on its own. A chain pins the exact version it was proven
against, so an in-place edit would silently change the meaning of every chain
already evidenced against it.

`strategy_id` is never reused for a different strategy and never changes
across versions.

---

## Adding an entry

1. Write `catalogue/atomic/<strategy_id>.json`.
2. Express every threshold as a bounded parameter with default, units and an
   allowed range or value list. If you cannot, the term is not catalogue
   material — escalate it per `docs/AMBIGUITY-POLICY.md`.
3. Declare each `required_hermes_fields` entry with its timeframe (PID line 22).
4. Give it at least one matching and one non-matching deterministic test case.
5. Record provenance, including that the defaults were architect-set.
6. Run `python3 -m pytest tests/test_catalogue.py` and
   `hsa validate catalogue/atomic/<strategy_id>.json`.

An atomic strategy may **not** reference another strategy. There is no
property in the schema through which it could, and it must not acquire one by
consuming another strategy's output through a HERMES field. See
`docs/COMPOSITION-DOCTRINE.md` §1.

---

## Related doctrine

- `contracts/README.md` — the frozen contract set.
- `docs/COMPOSITION-DOCTRINE.md` — how these entries are combined into chains.
- `docs/AMBIGUITY-POLICY.md` — declared parameter versus escalation, in full.
