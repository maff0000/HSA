# Strategy versioning and portfolio doctrine

PID lines 183-200, implemented in `hsa/versioning.py`. This is durable
authority, not commentary: the constraints below bind any future revision
proposal, and the ones that can be mechanically enforced are enforced.

---

## 1. The rule

> **PID line 185** — *Promoted strategy versions are immutable.*
> **PID line 187** — *Do not tweak a live strategy in place.*
> **PID line 189** — *A proposed modification creates a separately versioned
> candidate and must pass governed evidence gates again.*

This is acceptance criterion 13 (PID line 262): *produce a separately
versioned candidate rather than mutate an existing promoted strategy.*

Why it is absolute: evidence is anchored to a specific version. Editing a
promoted version in place silently detaches it from the evidence that
promoted it, and there is then no version in existence that the evidence
actually describes. The strategy still looks governed. It is not.

It also connects to a hard boundary: HSA must not mutate a live HELIOS
strategy silently (PID line 36). A version that can be edited in place is
exactly the mechanism by which that happens.

**Identity survives, versions do not change.** `strategy_id` is constant
across every version of a strategy; `strategy_version` identifies one frozen
specification. Identity is always the pair (acceptance criterion 10, PID
line 259).

---

## 2. Lifecycle

`lifecycle.status` in `contracts/strategy_package.schema.json`:

| Status | Meaning | Mutable? |
| --- | --- | --- |
| `CANDIDATE` | Proposed, not yet through the evidence gates. Still being written. | Yes — a candidate is edited directly. |
| `PROMOTED` | Passed its gates. Live. | **No.** |
| `DORMANT` | Promoted, resting. Conditions for it are not present. **Not a failure** (PID line 195). | **No.** |
| `RETIRED` | Withdrawn. Kept on the record. | **No.** |

### The one thing that moves

A promoted version's *specification* is frozen. Its *activation state* is
not, because doctrine requires it to move: dormancy is a normal resting state
(PID line 195) and an old proven strategy must remain available and
reactivate when conditions return (PID line 197). A version that could never
leave `PROMOTED` could never go dormant, and a version that could never leave
`DORMANT` could never reactivate.

So exactly these transitions are allowed, and nothing else:

| From | To |
| --- | --- |
| `CANDIDATE` | `PROMOTED`, `RETIRED` |
| `PROMOTED` | `DORMANT`, `RETIRED` |
| `DORMANT` | `PROMOTED`, `RETIRED` |
| `RETIRED` | *nothing* |

**Nothing ever returns to `CANDIDATE`.** A revision is a new version, never a
demotion of an existing one. Hand-editing `lifecycle.status` back to
`CANDIDATE` is treated as an in-place mutation and refused.

```python
from hsa.versioning import apply_status_transition

dormant = apply_status_transition(promoted, "DORMANT")   # returns a new document
live_again = apply_status_transition(dormant, "PROMOTED")
```

`apply_status_transition` never mutates its input, and a permitted status
change never carries a specification edit through with it — that combination
is still refused.

---

## 3. Proposing a modification

```python
from hsa.versioning import derive_candidate

candidate = derive_candidate(
    promoted,
    rationale="Evidence shows the 5M trigger fires late in fast markets; "
              "widen the confirmation window.",
    bump="MINOR",
    changes={"parameters": [...]},
    lineage_reference=version_lineage_reference,
)
```

The candidate:

* keeps the same `strategy_id` — identity is preserved across the lineage;
* takes the next `strategy_version`;
* has `lifecycle.status: CANDIDATE`;
* records `lifecycle.supersedes` — the superseded `strategy_id`,
  `strategy_version` **and a rationale**. The rationale is mandatory: a
  redesign always says why.

`changes` may not set `strategy_id`, `strategy_version` or `lifecycle`.
Those are derived, and setting them by hand is how an in-place edit disguises
itself as a candidate.

`derive_candidate` refuses a parent that was never promoted. A candidate that
has not been through the gates is not frozen, so it is edited directly rather
than superseded — and the frozen schema describes `supersedes` as *the
promoted version this candidate proposes to replace*.

The returned document is **not** written anywhere. Validate it with
`hsa.contracts.validate_document` and commit it; Git is the durable authority
(PID line 226).

### What a candidate inherits, and what it must earn again

> *…and must pass governed evidence gates again.* (PID line 189)

| Inherited | Not inherited |
| --- | --- |
| `SOURCE_ANALYSIS` | `PROMOTION_EVIDENCE` |
| `STRATEGY_HYPOTHESIS` | `REVISION_EVIDENCE` |
| `RESEARCH_FINDING` | `REJECTION_EVIDENCE` |
| `VERSION_LINEAGE` | |

The left column describes where the strategy came from and what was learned;
those remain true statements about the version they are anchored to. The
right column is **verdicts reached on the superseded version**. Carrying a
parent's promotion evidence onto a candidate would let a modification keep an
approval it never earned — which is precisely what acceptance criterion 13
exists to prevent.

A candidate therefore starts with no verdict of its own. It has to go and get
one.

---

## 4. Refusing an in-place mutation

`refuse_in_place_mutation(promoted, proposed)` raises
`PromotedVersionImmutableError` when `proposed` would edit a promoted version
rather than supersede it. This is real, tested behaviour — see
`tests/test_versioning.py`. Actual captured output:

```
refusing in-place modification of gold_context_breakout 1.0.0 (strategies/gold_context_breakout/1.0.0.json): that version is PROMOTED and promoted versions are immutable (PID lines 185-187). 2 changes refused:
  $.parameters[0].default: 1 -> 999
  $.thesis: 'Breakouts taken in the direction of an established higher-timeframe trend re... -> 'Reworded thesis.'
a modification must be a separately versioned candidate that passes the governed evidence gates again (PID line 189, acceptance criterion 13 at PID line 262): derive one with hsa.versioning.derive_candidate().
```

The refusal names every change it refuses, by JSON path, with before and
after values. It does not merely say "no": it says what was going to change
and what to do instead.

It returns cleanly — no refusal — when:

* the versions differ (that is the correct path, not a mutation);
* the shared version has never been promoted (a candidate is still mutable);
* the only difference is a permitted status transition.

It raises `VersioningError` if asked to compare two *different* strategies,
because answering "no mutation" to that would be a misleading pass.

`describe_in_place_mutation()` returns the same change list without raising,
for callers that want to inspect rather than enforce.

---

## 5. Lineage

`lineage(packages)` orders one strategy's packages by semver, oldest first,
and reports each version's status, what it supersedes and why.

> **Illustrative shape, not the inventory.** The sample below shows what a
> two-version lineage looks like once one exists. It is NOT a statement about
> `strategies/`: no package in this repository is `PROMOTED`, no 1.1.0 exists,
> and no promotion gate has been evaluated because CER is not live. See
> `strategies/README.md` for why the inventory holds a single version.

```bash
hsa cer lineage strategies/gold-1.0.0.json strategies/gold-1.1.0.json
```

```
strategy_id gold_context_breakout — 2 versions

1.0.0  [PROMOTED]
  original version, supersedes nothing
  evidence: PROMOTION_EVIDENCE     PROMOTION      ...

1.1.0  [CANDIDATE]
  supersedes 1.0.0 — Widen the confirmation window.
  evidence: REVISION_EVIDENCE      REVISION       ...
```

It refuses a mixed `strategy_id` (a lineage crosses versions, never
strategies) and a duplicate version (a version is immutable, so it appears
exactly once).

Lineage lives in two places on purpose, and they say different things:
`lifecycle.supersedes` in the package is HSA's statement of which version
replaced which; a `VERSION_LINEAGE` CER reference is the anchor recorded
through CER contracts (PID line 177). The superseded version is named only in
the package, because CER identities are opaque to HSA.

---

## 6. Portfolio doctrine — binding constraints on any revision proposal

PID lines 191-198. These are not decoration. Each one forbids a specific
move, and a revision proposal that makes that move is not governed, however
good the numbers look.

### Prefer many independently proven specialist strategies (PID line 193)

The portfolio is built from small strategies that each earned their own
evidence, not from one strategy generalised until it covers everything.

**Forbidden:** broadening an existing strategy's `validity_conditions` or
`instruments` to absorb a case that should be a separate strategy. If the new
case has its own thesis, it gets its own `strategy_id` and its own evidence.

### Do not force a strategy to trade outside its preferred market shape (PID line 194)

Every package declares `intended_horizon`, `intended_style` and
`validity_conditions`. Those are the shape the strategy was proven in.

**Forbidden:** a revision whose purpose is to make a strategy fire in
conditions it was never proven in. Declaring the horizon is what makes this
checkable, which is why the field is mandatory.

### Dormancy is not failure (PID line 195)

A strategy that is not firing because its conditions are absent is working
correctly. `DORMANT` is a normal resting state, and every package must state
non-empty `validity_conditions` — outside them, dormancy is the right
behaviour.

**Forbidden:** treating a dormancy period as evidence of a defect, or opening
a revision proposal whose stated rationale is "it has not traded recently".

### Do not tune merely to restore trade frequency (PID line 196)

**Forbidden:** a candidate whose rationale is frequency. A revision must be
justified by evidence about the strategy's *thesis* — that the logic is
wrong, mis-specified, or invalidated — never by how often it fires.

Because `derive_candidate` requires a written `rationale` and records it in
`lifecycle.supersedes`, a frequency-restoration motive cannot be hidden: it
is on the record, in the document, permanently. This constraint is enforced
by making the motive visible and reviewable, not by machine — no schema can
tell an honest rationale from a dishonest one.

### Allow old proven strategies to remain available and reactivate (PID line 197)

A dormant strategy is kept, not deleted. `DORMANT -> PROMOTED` is a supported
transition precisely so a proven strategy comes back when its conditions
return.

**Forbidden:** retiring or deleting a strategy because it is currently
dormant. `RETIRED` is a deliberate withdrawal on evidence, and it is
terminal — reactivating a retired strategy means a new candidate version,
governed from scratch.

### Avoid overfitting (PID line 198)

**Forbidden:** a revision that narrows parameters or conditions to fit
observed history, and a promotion evaluated on fewer occurrences than the
package's own `minimum_sample_size`. Evidence requirements — including that
minimum — are stated in the package *before* evidence is gathered, so
thresholds cannot be moved to fit a result.

---

## 7. NEO

> **PID line 200** — *NEO may provide evidence/hypotheses. HSA governs any
> resulting candidate strategy redesign. NEO may never silently rewrite
> HELIOS.*

NEO-supplied material enters as ordinary CER references — typically
`RESEARCH_FINDING` or `STRATEGY_HYPOTHESIS`. It is input to a proposal, never
a proposal itself, and never a change.

Any redesign it motivates is a candidate version derived through
`derive_candidate`, carrying a rationale, passing the governed evidence gates
in its own right. The promoted version it proposes to replace stays exactly
as it is until HSA governs the replacement. There is no path — and there must
never be one — by which evidence from NEO reaches a promoted specification
without a new version and a governed decision.

HSA does not build NEO (PID line 271). This section constrains how HSA treats
what NEO provides.

---

## 8. Reference

```python
from hsa.versioning import (
    derive_candidate,            # propose a modification -> a new version
    refuse_in_place_mutation,    # enforce PID lines 185-187
    describe_in_place_mutation,  # the same check, without raising
    apply_status_transition,     # dormancy and reactivation
    lineage,                     # order a strategy's versions
    status_of, is_promoted, identity_of, supersedes_of,
    parse_version, bump_version,
)
```

Everything is a pure function over `strategy_package` documents. Nothing is
written, indexed or cached: Git is the durable authority (PID line 226), and
the strategy inventory is a set of package files, not a database.

`VersioningError` and `PromotedVersionImmutableError` subclass `HSAError`, so
`hsa/cli.py` maps them onto exit code 3 without knowing they exist.

## Related

* `contracts/strategy_package.schema.json` — the frozen `lifecycle` and
  `supersedes` fields.
* `docs/CER-CONTRACT.md` — why evidence is anchored to one immutable version.
