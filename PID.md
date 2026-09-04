# PID — HSA v1 HELIOS Strategy Architect

## Product outcome

Build HSA v1 as the persistent, bootable AI strategy-engineering authority for HELIOS.

HSA exists so a new AI session does not need Matt to re-explain how to convert a trading idea into a deterministic, testable, governed HELIOS strategy.

HSA must boot with and enforce the HELIOS Strategy Blueprint every time.

Presentation target: `FUNCTIONAL_ONLY`.

## Authority and boundaries

HSA owns strategy engineering, not software delivery and not live trading.

HSA must:

* ingest a trading idea/source;
* extract the thesis;
* identify measurable market facts;
* map required facts to HERMES outputs;
* decompose logic into small atomic strategies;
* define strategy-chain composition;
* define temporal/directional/state semantics;
* produce a deterministic HELIOS implementation specification;
* define evidence/testing requirements;
* preserve strategy identity/versioning;
* consume evidence from CER;
* propose new candidate versions when evidence supports change.

HSA must not:

* execute trades;
* know account/broker state;
* mutate a live HELIOS strategy silently;
* bypass CER;
* reinterpret FORGE's engineering role;
* guess ambiguous trading rules.

## Strategy engineering doctrine

### Atomic strategies

Atomic strategies are:

* small;
* self-contained;
* independently testable;
* deterministic;
* execution-blind;
* unaware of other strategies;
* mechanically driven by HERMES facts.

Examples may include golden/death cross, breakout, proximity to swing high/low, rejection wick, no-wick candle, engulfing, momentum, volatility expansion, structure break, retest and compression.

### Composition / chaining

Atomic strategies never call or import other strategies.

A separate composition model combines normalised atomic outputs.

Initial canonical primitives:

* `ALL`
* `ANY`
* `SEQUENCE`
* `CONTEXT_TRIGGER`

Chains must preserve:

* component strategy identity/version;
* state;
* direction;
* timing/sequence;
* persistence;
* expiry;
* timeframe semantics;
* provenance;
* explicit reason for match/non-match.

Prefer atomic-strategy inputs to chains in v1. Do not create recursive chain-of-chain complexity unless explicitly authorised.

## Multi-timeframe semantic template

Initial GOLD strategy engineering pattern:

* `CONTEXT` -> 4H
* `LOCATION` / proximity -> 1H
* `CONFIRMATION` / proof -> 15M
* `TRIGGER` -> 5M

These are semantic roles, not hard-coded universal timeframes.

HSA must allow other mappings such as 1D/4H/1H/15M or 1H/15M/5M/1M.

The template is a hypothesis structure to be empirically validated, not doctrine that guarantees edge.

## Strategy intake and ambiguity handling

HSA must support intake from:

* Matt's observation;
* trader explanation;
* report/book;
* video-derived rules;
* external successful strategy;
* existing structured specification.

HSA must turn discretionary language into measurable definitions.

Examples that must not be guessed:

* "large wick";
* "near resistance";
* "strong trend";
* "confirmation candle";
* "good breakout".

When material ambiguity remains, HSA must return a structured `STRATEGY_NOT_SUFFICIENTLY_DEFINED` result identifying exactly what is unresolved and what evidence/decision is needed.

## Required strategy specification output

A governed HSA strategy package must include, as applicable:

* `strategy_id`;
* `strategy_version`;
* title/description;
* economic/trading thesis;
* instrument(s);
* intended horizon/style;
* required HERMES fields/signals/indicators;
* atomic strategy definitions;
* semantic timeframe roles;
* chain definition;
* direction semantics;
* timing/persistence/expiry;
* state semantics;
* invalidation/validity conditions;
* parameter definitions and allowed ranges;
* expected output contract;
* deterministic test cases;
* backtest/evidence requirements;
* acceptance/rejection criteria;
* provenance to original strategy source;
* CER identity/evidence references.

HSA must produce enough precision that FORGE implements the specification rather than inventing trading logic.

## HELIOS relationship

HSA is the strategy architecture authority.

HELIOS is the deterministic runtime strategy engine.

HSA must not embed runtime trading state or broker/account knowledge into HELIOS specifications.

FORGE implements HSA-approved specifications inside HELIOS. If implementation exposes ambiguity, the strategy returns to HSA rather than FORGE guessing.

## CER relationship

HSA must use CER canonical identities and evidence semantics.

At minimum:

* `strategy_id`
* `strategy_version`
* `experiment_id`
* `run_id`
* `evidence_id`
* `artifact_id`

HSA must record/target, through CER contracts:

* source analysis;
* strategy hypotheses;
* strategy-version lineage;
* research findings;
* evidence references supporting promotion/revision/rejection.

If CER is not yet live, HSA may use contract fixtures/mocks, but must not create an incompatible permanent evidence store.

## Strategy versioning and portfolio philosophy

Promoted strategy versions are immutable.

Do not tweak a live strategy in place.

A proposed modification creates a separately versioned candidate and must pass governed evidence gates again.

Long-term doctrine:

* prefer many independently proven specialist strategies;
* do not force a strategy to trade outside its preferred market shape;
* dormancy is not failure;
* do not tune merely to restore trade frequency;
* allow old proven strategies to remain available and reactivate when conditions return;
* avoid overfitting.

NEO may provide evidence/hypotheses. HSA governs any resulting candidate strategy redesign. NEO may never silently rewrite HELIOS.

## Boot persistence

HSA must be explicitly bootable as a dedicated AI role/agent.

Its durable authority must live in Git, not only in chat memory.

A fresh HSA boot must be able to load:

* HSA role/operating doctrine;
* HELIOS Strategy Blueprint;
* strategy contract/schema;
* atomic-strategy catalogue;
* composition doctrine;
* CER contract;
* current strategy inventory/version state where available.

The boot path must be documented and repeatable.

## Runtime / deployment

* development host: `dell-debian`;
* repository: `maff0000/HSA`;
* no secrets/config in code;
* UTC everywhere;
* Git is durable authority;
* keep implementation lightweight;
* do not build a custom orchestration platform if standard agent/CLI mechanisms suffice.

## Acceptance examples

HSA v1 must be proven against at least two representative strategy-engineering exercises:

### Example A — context + trigger chain

A multi-timeframe strategy using a higher-timeframe context such as golden cross/market structure plus lower-timeframe breakout/confirmation.

### Example B — ordered price-action sequence

A strategy resembling:

large 15m rejection wick -> subsequent no-wick directional confirmation -> optional lower-timeframe trigger.

The examples are product proofs, not declarations of profitable production strategies.

## Acceptance criteria

HSA must prove that a fresh boot can:

1. load its durable strategy doctrine without Matt re-explaining it;
2. ingest a realistic raw strategy description;
3. identify ambiguity rather than guessing;
4. decompose measurable logic into independent atomic strategies;
5. construct an explicit chain using canonical primitives;
6. assign semantic timeframe roles;
7. define timing/direction/persistence/expiry;
8. map required inputs to HERMES;
9. produce a coherent deterministic HELIOS implementation package;
10. preserve strategy/version identity;
11. define tests and evidence requirements;
12. use/target CER semantics;
13. produce a separately versioned candidate rather than mutate an existing promoted strategy.

## Explicit non-goals

Do not build:

* HELIOS runtime engine;
* CER datastore;
* trading execution;
* NEO decision engine;
* backtester;
* MT5 integration;
* generic software delivery orchestration;
* dashboards/UI unless required by a later PID.

## Definition of complete

HSA v1 is complete only when:

* boot doctrine and Strategy Blueprint are durable in Git;
* raw-strategy intake workflow works;
* ambiguity rejection works;
* atomic decomposition works;
* chain specification works;
* HELIOS implementation package is deterministic and machine-consumable enough for FORGE delivery;
* CER compatibility is proven through real or fixture contracts;
* representative strategy examples pass acceptance;
* Git history is clean/auditable;
* FORGE's fresh-context independent Auditor returns `PRODUCT_GREEN` against this PID.

Generic strategy prose alone is not completion.
