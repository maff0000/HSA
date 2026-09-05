# Raw strategy-description fixtures

Realistic intake inputs for `tests/test_intake.py`,
`tests/test_ambiguity.py` and the two acceptance suites
(`tests/test_acceptance_example_a.py`, `tests/test_acceptance_example_b.py`).
Each `.txt` file is raw text exactly as it would arrive from one of the
sources at PID lines 101-108; `.json` files are structured intake requests.
`lexicon_*.json` are alternative lexicons used to exercise policy paths the
shipped lexicon does not use.

**The table below must list every file in this directory.**
`tests/test_ambiguity.py::test_the_fixture_readme_lists_every_fixture`
fails on a file with no row and on a row with no file, so a fixture added by
a later work item cannot land here undocumented — which is how the three
acceptance fixtures went missing from this table the first time.

| File | Source type | Expected outcome |
| --- | --- | --- |
| `well_specified_wick_sequence.txt` | MATT_OBSERVATION | draft, nothing discretionary recognised |
| `example_b_rejection_wick_sequence.txt` | TRADER_EXPLANATION | draft, `large_wick` + `no_wick_candle` parameterised |
| `example_b_wick_rejection_sequence.txt` | TRADER_EXPLANATION | draft, same two terms parameterised — the packaged source of `strategies/wick_rejection_sequence/0.1.0` (PID acceptance Example B) |
| `example_a_first_pass.txt` | TRADER_EXPLANATION | refusal naming `strong_trend` + `good_breakout` — Example A's first call, before the trader named the constructions |
| `example_a_gold_context_breakout.txt` | TRADER_EXPLANATION | draft with **zero** parameterised terms — the second call, where the trader supplied the constructions himself (PID acceptance Example A) |
| `near_resistance_pullback.txt` | TRADER_EXPLANATION | refusal naming `near_resistance` |
| `unknown_term_healthy_pullback.txt` | MATT_OBSERVATION | refusal — undeclared term fails closed |
| `all_five_pid_phrases.txt` | VIDEO_DERIVED | refusal covering PID lines 114-118 |
| `rebased_wick_recent_average.txt` | MATT_OBSERVATION | refusal — `docs/AMBIGUITY-POLICY.md`'s own worked example: a ruled term whose context re-bases it |
| `rebased_wick_atr_multiple.txt` | TRADER_EXPLANATION | refusal — the source states an ATR basis and says the bar range is irrelevant, so the ruled bar-range basis does not apply |
| `existing_specification.json` | EXISTING_SPECIFICATION | draft, structured-request form |
| `empty.txt` | any | error: nothing to analyse |
| `lexicon_advisory.json` | — | test lexicon whose items are ADVISORY, not BLOCKING |
| `lexicon_collision.json` | — | test lexicon whose patterns collide on purpose: a PARAMETERISE head noun a REFUSE term also claims. Proves the overlap invariant is enforced on the match, not by patterns being written carefully |

## Two files whose names read alike

`example_b_rejection_wick_sequence.txt` and
`example_b_wick_rejection_sequence.txt` are different fixtures and are not
interchangeable.

- `example_b_rejection_wick_sequence.txt` is the unit-test fixture. It
  exercises the parameterise path in `tests/test_intake.py` and
  `tests/test_ambiguity.py`.
- `example_b_wick_rejection_sequence.txt` is the **acceptance** fixture. It
  is the source text of the governed package at
  `strategies/wick_rejection_sequence/0.1.0`, and
  `tests/test_acceptance_example_b.py` asserts the packaged `source.txt` is
  this file byte for byte. Editing it changes the provenance of a governed
  package, so treat it as fixed.

`tests/test_acceptance_example_a.py` makes the same byte-for-byte claim about
`example_a_gold_context_breakout.txt`.
