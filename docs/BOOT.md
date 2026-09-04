# Booting HSA

`PID.md:204` requires HSA to be explicitly bootable as a dedicated AI role or
agent, `PID.md:206` requires its durable authority to live in Git rather than
chat memory, and `PID.md:218` requires the boot path to be **documented and
repeatable**. This is that path.

Boot is a gate, not a greeting. A session that has not loaded its doctrine is
not HSA and must not engineer a strategy.

---

## 1. The boot path

### Step 0 — get the repository and install HSA

```bash
git clone https://github.com/maff0000/HSA.git
cd HSA

python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install .
```

Python 3.11 or newer. The only runtime dependency is `jsonschema`
(`PID.md:227`, keep the implementation lightweight); `pip install .` pulls it
in and puts the `hsa` command on `PATH`.

**Install the package — do not stop at the dependency.** This document and
every other file in the repository writes commands as `hsa …`, and `hsa` does
not exist until the package is installed. A Step 0 that installed only
`requirements.txt` left `hsa validate` in Step 3 failing at exit `127` from a
clean clone, which is a boot path that is documented but not repeatable
(`PID.md:218`).

**Use a virtual environment.** On the development host (`dell-debian`,
`PID.md:222`) and on any current Debian or Ubuntu, the system Python is
marked externally managed (PEP 668) and `pip install` outside a virtual
environment refuses to run at all. `.venv/` is already in `.gitignore`.

If you would rather not install the package, install just the dependency into
the same virtual environment and use the module form of every command in this
document:

```bash
python3 -m pip install -r requirements.txt     # jsonschema only
python3 -m hsa.cli boot                        # instead of: hsa boot
```

### Step 1 — verify and load the doctrine

```bash
hsa boot
```

`hsa boot` reads [`docs/boot-manifest.json`](boot-manifest.json) — the single
machine-readable declaration of what a boot must load — verifies every
artifact it declares, loads it, and reports what was loaded.

**Exit code 0 means the doctrine is present and readable. It does not mean
you have read it.**

### Step 2 — read what boot listed

Read the artifacts in the order `hsa boot` printed. That order is deliberate:
who HSA is, then the doctrine it enforces, then the contracts it emits
against, then the catalogue and policies it applies, then evidence semantics,
then the current inventory.

At minimum, before doing any strategy work, you must have read:

1. [`docs/HSA-ROLE.md`](HSA-ROLE.md) — who you are, and what you must never do
2. [`docs/HELIOS-STRATEGY-BLUEPRINT.md`](HELIOS-STRATEGY-BLUEPRINT.md) — the doctrine you enforce
3. [`contracts/README.md`](../contracts/README.md) — the shapes you must emit
4. [`docs/COMPOSITION-DOCTRINE.md`](COMPOSITION-DOCTRINE.md) — how atomic outputs combine
5. [`docs/AMBIGUITY-POLICY.md`](AMBIGUITY-POLICY.md) — how to refuse rather than guess
6. [`docs/CER-CONTRACT.md`](CER-CONTRACT.md) — identity and evidence semantics

### Step 3 — confirm the toolchain works

```bash
hsa validate tests/fixtures/valid/strategy_package.json
```

Expect `valid strategy_package` and exit code 0. This proves the contract
set resolves offline before you rely on it.

### Step 4 — work

Follow [`docs/HSA-ROLE.md`](HSA-ROLE.md) §4. Commit outcomes to Git: durable
authority lives in the repository, not in the conversation (`PID.md:206`).

---

## 2. Booting as an AI agent

The bootable role definition is [`.claude/agents/hsa.md`](../.claude/agents/hsa.md),
a standard agent definition. There is no bespoke loader, daemon or
orchestration platform, and adding one would violate `PID.md:228`.

From Claude Code in a checkout of this repository:

```
> Use the hsa agent to engineer a strategy from this description: ...
```

The agent definition instructs the session to run the boot path above and
read the manifest artifacts **before** any strategy work. A session that
skips it is not HSA.

---

## 3. What `hsa boot` reports

Every block in this section is the output of a real `hsa boot` run against
this repository. The only edit is the checkout path, shortened to `~/HSA`.
`tests/test_boot.py::test_boot_md_shows_what_a_real_boot_actually_reports`
compares the statuses, the directory entry counts and the summary line below
against a live run, because this section went stale once — it claimed a
one-entry catalogue and an absent `strategies/` while the repository held
eleven atomic strategies and both acceptance packages.

```
HSA boot — 2026-09-04T23:25:58Z
manifest: ~/HSA/docs/boot-manifest.json (version 1)
root:     ~/HSA

  [   ok  ] docs/HSA-ROLE.md                                9.1 KB, 211 lines
  [   ok  ] docs/HELIOS-STRATEGY-BLUEPRINT.md               18.1 KB, 390 lines
  [   ok  ] docs/BOOT.md                                    10.5 KB, 272 lines
  [   ok  ] contracts/README.md                             5.8 KB, 111 lines
  [   ok  ] contracts/common.defs.json                      8.3 KB, 202 lines
  [   ok  ] contracts/atomic_strategy.schema.json           6.1 KB, 115 lines
  [   ok  ] contracts/chain.schema.json                     12.1 KB, 256 lines
  [   ok  ] contracts/strategy_package.schema.json          13.0 KB, 277 lines
  [   ok  ] contracts/cer_reference.schema.json             3.4 KB, 62 lines
  [   ok  ] contracts/not_sufficiently_defined.schema.json  6.4 KB, 132 lines
  [   ok  ] docs/COMPOSITION-DOCTRINE.md                    19.4 KB, 397 lines
  [   ok  ] catalogue/atomic/                               11 entries
  [   ok  ] docs/AMBIGUITY-POLICY.md                        23.3 KB, 414 lines
  [   ok  ] docs/VERSIONING.md                              13.0 KB, 326 lines
  [   ok  ] docs/CER-CONTRACT.md                            14.0 KB, 311 lines
  [   ok  ] contracts/fixtures/cer/                         8 entries
  [   ok  ] strategies/                                     3 entries

17 artifacts declared: 17 loaded, 0 required missing, 0 optional absent

HSA booted. Read the loaded artifacts in the order above before engineering
a strategy; see docs/BOOT.md.
```

The byte and line figures are whatever those files were at the time of the
run and are not asserted by the test; the statuses, the entry counts and the
summary line are.

Options:

| Option | Effect |
| ------ | ------ |
| `--json` | emit the report as JSON, including a `sha256` per loaded file |
| `-q`, `--quiet` | report only problems and the summary line |
| `--manifest <file>` | use a different manifest |
| `--root <dir>` | resolve manifest paths against a different directory |
| `HSA_BOOT_MANIFEST` | environment override for the manifest location |

The manifest, not the code, is the single declaration of what boot means.
Adding an artifact to the boot set is a manifest edit.

---

## 4. Exit codes and failure modes

Exit codes are the CLI's, shared by every command (see `hsa/cli.py`):

| Code | Meaning |
| ---- | ------- |
| `0` | boot complete — every required artifact loaded |
| `2` | usage error |
| `3` | boot failed, or the manifest itself is unusable |

### 4.1 A required artifact is missing

A real run of the tree above with `docs/CER-CONTRACT.md` and `strategies/`
removed:

```
  [   ok  ] docs/VERSIONING.md                              13.0 KB, 326 lines
  [MISSING] docs/CER-CONTRACT.md                            REQUIRED — no such file
  [   ok  ] contracts/fixtures/cer/                         8 entries
  [  warn ] strategies/                                     optional — no such directory

17 artifacts declared: 15 loaded, 1 required missing, 1 optional absent
hsa: boot incomplete: 1 required artifact could not be loaded
  docs/CER-CONTRACT.md: missing (no such file)
HSA has not booted. Its doctrine is incomplete, so it must not engineer a
strategy in this state.
```

Exit code `3`. **Every** missing path is named, not just the first, so one
run tells you everything that is absent. **Do not proceed.** A session that
starts work here believes it holds doctrine it has never read — the exact
failure `PID.md:7` exists to prevent.

An artifact that exists but is empty, is not valid UTF-8, or is a directory
holding fewer entries than the manifest requires fails the same way, marked
`FAILED` rather than `MISSING`:

```
  [ FAILED] catalogue/atomic/                               REQUIRED — holds 0 entries matching '*', expected at least 1
  [ FAILED] docs/CER-CONTRACT.md                            REQUIRED — file is empty; doctrine that is not written is not loaded
  [  warn ] strategies/                                     optional — no such directory

17 artifacts declared: 14 loaded, 2 required missing, 1 optional absent
```

An empty file is not loaded doctrine.

### 4.2 An optional artifact is absent

```
  [  warn ] strategies/                                     optional — no such directory
```

Exit code `0`, with a warning. Only two entries are optional, and each is
optional because the PID says so:

- `strategies/` — the current strategy inventory, required "**where
  available**" (`PID.md:216`). Before any strategy is governed there is
  nothing to load.
- `contracts/fixtures/cer/` — CER fixtures stand in only while CER is not
  live (`PID.md:181`).

Everything else is required. If a boot warns about an optional artifact you
expected to be there, treat the warning as real: an inventory that has
vanished is a problem even though it does not fail the boot.

### 4.3 The manifest itself is broken

```
hsa: boot manifest ~/HSA/docs/boot-manifest.json: ~/HSA/docs/boot-manifest.json is not valid JSON: Expecting property name enclosed in double quotes (line 1, column 3)
```

Exit code `3`, and **nothing is checked**. A manifest that cannot be trusted
must not be allowed to silently verify nothing. Fix the manifest; do not
work around it.

---

## 5. Verifying a boot after the fact

```bash
hsa boot --json > boot-report.json
```

The JSON report carries the UTC boot timestamp, the manifest version, the
resolved root, and a `sha256` for every loaded file — enough to prove later
exactly which doctrine a session booted with.

---

## 6. Adding to the boot set

1. Add the artifact to the repository.
2. Add an entry to [`docs/boot-manifest.json`](boot-manifest.json) with an
   `id`, `title`, `path`, `type`, `required`, the `pid` line that puts it in
   the boot set, and `why` boot fails or warns without it.
3. Run `hsa boot`.

Mark an entry `required: false` only where the PID genuinely allows absence,
and record that reason in `pid` and `why`. Optionality that is not traceable
to the PID is how a boot gate quietly stops being a gate.
