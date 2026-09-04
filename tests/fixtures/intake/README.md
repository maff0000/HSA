# Raw strategy-description fixtures

Realistic intake inputs for `tests/test_intake.py` and
`tests/test_ambiguity.py`. Each `.txt` file is raw text exactly as it would
arrive from one of the sources at PID lines 101-108; `.json` files are
structured intake requests. `lexicon_*.json` are alternative lexicons used
to exercise policy paths the shipped lexicon does not use.

| File | Source type | Expected outcome |
| --- | --- | --- |
| `well_specified_wick_sequence.txt` | MATT_OBSERVATION | draft, nothing discretionary recognised |
| `example_b_rejection_wick_sequence.txt` | TRADER_EXPLANATION | draft, `large_wick` + `no_wick_candle` parameterised (PID acceptance Example B) |
| `near_resistance_pullback.txt` | TRADER_EXPLANATION | refusal naming `near_resistance` |
| `unknown_term_healthy_pullback.txt` | MATT_OBSERVATION | refusal — undeclared term fails closed |
| `all_five_pid_phrases.txt` | VIDEO_DERIVED | refusal covering PID lines 114-118 |
| `existing_specification.json` | EXISTING_SPECIFICATION | draft, structured-request form |
| `empty.txt` | any | error: nothing to analyse |
| `lexicon_advisory.json` | — | test lexicon whose items are ADVISORY, not BLOCKING |
