# HSA — HELIOS Strategy Architect

HSA is the persistent, bootable AI strategy-engineering authority for HELIOS.

It exists so that a new AI session does not need Matt to re-explain how to
convert a trading idea into a deterministic, testable, governed HELIOS
strategy (`PID.md:7`). The doctrine that makes that possible is durable in
this repository — in Git, not in chat memory (`PID.md:206`).

HSA owns **strategy engineering**. It does not execute trades, does not know
account or broker state, does not implement HELIOS, and does not guess
ambiguous trading rules (`PID.md:32-39`).

Forge-governed. Authoritative scope: [`PID.md`](PID.md).

---

## Boot it

```bash
python3 -m pip install -r requirements.txt     # jsonschema only
python3 -m hsa.cli boot                        # or: hsa boot
```

`hsa boot` verifies and loads every artifact in
[`docs/boot-manifest.json`](docs/boot-manifest.json) and **exits non-zero if
any required one is missing**. A session that has not booted is not HSA and
must not engineer a strategy.

The full, repeatable boot path is [`docs/BOOT.md`](docs/BOOT.md). To boot as
an AI agent, use the standard agent definition at
[`.claude/agents/hsa.md`](.claude/agents/hsa.md).

## Validate a document

```bash
python3 -m hsa.cli validate tests/fixtures/valid/strategy_package.json
```

Exit codes: `0` valid, `1` invalid (the failing JSON path is printed), `2`
usage error, `3` any other deliberate error such as an unreadable file or an
incomplete boot.

---

## What is in here

| Path | What it is |
| ---- | ---------- |
| [`PID.md`](PID.md) | The authoritative Project Initiation Document. Every rule in this repository traces to a line of it. |
| [`docs/HSA-ROLE.md`](docs/HSA-ROLE.md) | HSA's role and operating doctrine — what it owns, what it must never do, how it works. |
| [`docs/HELIOS-STRATEGY-BLUEPRINT.md`](docs/HELIOS-STRATEGY-BLUEPRINT.md) | The Strategy Blueprint HSA boots with and enforces every time (`PID.md:9`). |
| [`docs/BOOT.md`](docs/BOOT.md) | The documented, repeatable boot path (`PID.md:218`). |
| [`docs/boot-manifest.json`](docs/boot-manifest.json) | The single machine-readable declaration of what a boot must load. |
| [`docs/COMPOSITION-DOCTRINE.md`](docs/COMPOSITION-DOCTRINE.md) | How atomic outputs are combined into chains. |
| [`docs/AMBIGUITY-POLICY.md`](docs/AMBIGUITY-POLICY.md) | How discretionary language is resolved, and how HSA refuses instead of guessing. |
| [`docs/CER-CONTRACT.md`](docs/CER-CONTRACT.md) | CER canonical identities and evidence semantics. |
| [`contracts/`](contracts/) | The frozen JSON Schema contract set, plus [`contracts/README.md`](contracts/README.md). |
| [`catalogue/atomic/`](catalogue/atomic/) | The catalogue of atomic strategies. |
| [`hsa/`](hsa/) | The CLI: `hsa boot`, `hsa validate`. |
| [`tests/`](tests/) | Test suite and reusable fixture documents. |
| `strategies/` | Governed strategy packages and version state, once any exist. |

## Doctrine in one page

- **Atomic strategies** are small, self-contained, independently testable,
  deterministic, execution-blind, unaware of other strategies, and
  mechanically driven by HERMES facts (`PID.md:45-53`).
- **Composition is separate.** Atomic strategies never call or import each
  other; chains combine their normalised outputs using `ALL`, `ANY`,
  `SEQUENCE` and `CONTEXT_TRIGGER` (`PID.md:59-68`).
- **`CONTEXT` / `LOCATION` / `CONFIRMATION` / `TRIGGER` are semantic roles,
  not hard-coded timeframes** (`PID.md:93`).
- **Ambiguity is refused, not guessed.** Material ambiguity produces a
  structured `STRATEGY_NOT_SUFFICIENTLY_DEFINED` result (`PID.md:120`).
- **Promoted versions are immutable.** A change is a separately versioned
  candidate that re-earns promotion through evidence (`PID.md:185-189`).
- **Prefer many proven specialists.** Dormancy is not failure; do not tune
  to restore trade frequency (`PID.md:191-198`).

## Development

Python 3.11+. Runtime dependency: `jsonschema` only (`PID.md:227`).

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install pytest
python3 -m pytest
```

No secrets or configuration in source; configuration is supplied externally
and missing configuration fails loudly. UTC everywhere (`PID.md:224-225`).
