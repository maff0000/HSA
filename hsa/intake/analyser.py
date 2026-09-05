"""The deterministic scan over a raw strategy description.

WHAT THIS IS: a rules-based analyser over the declared lexicon. It matches
declared surface patterns, first the ruled terms and then the discretionary
markers, and reports every marker occurrence that no ruled term consumed.

WHAT "CONSUMED" MEANS, EXACTLY. A term pattern is part literal and part
wildcard. The literal parts are the phrase the lexicon rules on; the declared
``basis_slot`` group is a wildcard run of words that merely sits between them.
Only the literal parts suppress further scanning. The slot does not, and
treating it as if it did was a silent hole: "a large near resistance wick"
matched ``large_wick`` end to end, so ``near_resistance`` — a PID line 115
must-not-guess phrase — and the proximity marker both fell inside a span the
analyser had already written off as ruled, and the source resolved at exit 0
with no refusal and no advisory. Text in the slot is now scanned exactly like
any other prose, and a PARAMETERISE term whose slot holds unresolved language
does not resolve (``term_match_policy`` in the lexicon).

SUPPRESSION REQUIRES COVERAGE, NOT OVERLAP, AND OVERLAP RESOLUTION NEVER
DELETES A REFUSAL. Those are the same rule stated twice, and they are the
general form of everything above. Matches are collected first and overlaps
resolved by a fixed rule, which is fine for deciding which term PARAMETERISES
and was catastrophic for deciding what gets REPORTED: the loser was discarded.
"no-wick close to resistance" hands the ruled word "close" to
``no_wick_candle``, so ``near_resistance`` overlapped an accepted ruling, lost,
and vanished — exit 0, nothing unresolved, a PID line 115 phrase gone without
trace. That is the same silent path as the slot bug one phrasing further out,
which is why it is now closed on the MATCH rather than on the slot:

    A match is dropped as "already ruled on" only when the accepted rulings
    COVER it end to end. Partial overlap is not a ruling — it is two readings
    of one stretch of text — so both are kept and reported, and any
    PARAMETERISE term whose matched span collides with unresolved language or
    with a second ruling does not resolve at all
    (``term_match_policy.overlap_resolution``).

The scan that finds those collisions asks about the whole matched span, its
literal head nouns included. Scoping it to the wildcard slot is what left this
open after the previous repair, and scoping is exactly what a fifth phrasing
walks around.

A TERM MATCH MAY NOT SPAN A SENTENCE BOUNDARY, AND DECLINING TO READ ONE IS NOT
PERMISSION TO DELETE IT. The same wildcard let a match run across a full stop —
"a large trade. some wick setups only" matched ``large_wick`` — and swallow the
start of the next sentence with it. The rule is enforced here, on the match,
rather than by tightening each pattern: patterns are tightened too, but a
pattern-level fix protects only the patterns that exist today, and this one
holds for a term nobody has declared yet.

That rule is two decisions and for four audits only one of them was made. The
match is NOT ACCEPTED — it resolves nothing and suppresses nothing, so
everything on the far side of the boundary is still scanned, which is the
concern that justified the rule. It is also NOT DISCARDED, which nothing ever
justified: a recognised term left no finding of any kind, so

    "XAUUSD 15m breakout rules. I only take a valid m.a breakout of the range."

drafted at exit 0 with nothing unresolved, while the same sentence without the
dotted token refused for ``good_breakout`` — a PID line 118 must-not-guess
phrase. It is now refused AND reported, like the other two rules in
``term_match_policy``.

The way in was the sentence splitter, not the patterns: only a ``.`` between
two DIGITS was exempt, so "m.a", "h.4", "4.hour", "vwap.session" and "a.m" each
read as a sentence ending mid-word. A terminator with a word character on both
sides is now treated as inside a token; "1.5" is the special case of that, and
"trade. some" still ends a sentence.

NOTHING MAY CAUSE A RECOGNISED TERM TO GO UNREPORTED, AND THAT IS CHECKED. R7
stated this over overlap resolution; the general form is one word wider, and
stating it is what the previous four repairs also did. Every recognised match
is written into a ledger with the single reason it is accounted for, and
``_verify_every_recognised_match_is_reported`` checks that ledger against the
findings actually emitted before ``analyse`` returns. There is no reason
meaning "dropped", so a sixth deletion path raises ``UnreportedMatchError``
rather than going quiet.

Between those two passes sits the basis-qualifier check. A ruled
PARAMETERISE term is only ruled for the claim the lexicon declares: "large
wick" is ratified onto a single-bar wick-over-range basis, and "large wick
relative to the recent average" is a different claim that ruling does not
cover. So before a PARAMETERISE term is allowed to resolve, the declared
window around it is scanned against the declared basis-qualifier vocabulary.

FINDING A QUALIFIER IS NOT ENOUGH TO REFUSE. The window says where to look;
what decides the outcome is ATTACHMENT — whether the qualifier modifies the
ruled measurement, or merely shares a sentence with it. Three declared forms
attach (``basis_qualifier_policy.attachment`` in the lexicon):

    SLOT        the qualifier sits in the term's own modifier slot, the
                ``basis_slot`` group its pattern declares — "a large ATR
                wick", "a larger than average wick". The slot is a wildcard
                INSIDE the matched span, which is exactly where a re-basing
                lands, so hits inside the match are inspected, never dropped.
    COMPLEMENT  a COMPARATIVE qualifier stands as the term's own complement,
                separated from it only by declared filler — "a large wick
                RELATIVE TO the recent average". Comparatives are the
                connectives that bind a yardstick to a measurement; a bare
                yardstick noun attaches to whatever else the clause is about.
    GLOSS       the source restates the term's own ruled word and defines it
                — "a large wick, and by large I mean twice the 14-period
                ATR". The gloss must NAME a word the match consumed.

Everything else co-occurs and is left alone, deliberately. An ATR stop, a
bar-count expiry (which PID line 137 requires a package to state), a
moving-average trend filter and a prior-bar price reference are ordinary,
correct trading prose; refusing them would be a defect of its own, not
caution. This is PRECISION chosen over RECALL, and what makes that safe is
that the guard is not the only thing telling the truth: every resolution it
permits still carries ``source_basis_agreement: NOT_VERIFIED``, and now also
names the declared qualifiers that were seen and deliberately left
unattached. Its limits are declared alongside it in the lexicon and are
real: it recognises listed constructions, attached in listed ways, inside a
declared window, and nothing more.

WHAT THIS IS NOT: an LLM call, or anything that understands English. It
cannot prove a description is unambiguous — absence of declared markers is
not evidence of precision. What it does guarantee is narrower and is the
whole point: nothing it recognises as discretionary passes through without a
ruling. See ``docs/AMBIGUITY-POLICY.md``, section "What the analyser
actually is, and what it is not".

Determinism: given the same text and the same lexicon, the same findings
come out in the same order. Overlaps are resolved by a fixed rule (leftmost,
then longest, then lexicon order), never by iteration order of a set or a
dict. That rule decides which term parameterises; it decides nothing about
what is reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from hsa.intake.errors import UnreportedMatchError
from hsa.intake.lexicon import (
    BASIS_SLOT_GROUP,
    PARAMETERISE,
    BasisQualifier,
    Lexicon,
    Marker,
    Term,
)

__all__ = [
    "Occurrence",
    "TermFinding",
    "QualifierHit",
    "RebasedFinding",
    "UnruledSlotFinding",
    "ContestedMatchFinding",
    "StraddledMatchFinding",
    "UnknownFinding",
    "Analysis",
    "normalise",
    "analyse",
]

#: Characters that end a quoted phrase when widening an unknown marker hit.
_PHRASE_STOP = set(" .,;:!?()[]{}\"'“”‘’—–\n")

#: How many words after the marker are quoted as the offending phrase.
_PHRASE_WORDS = 3

#: Trailing function words are dropped from a quoted phrase so it reads as a
#: phrase rather than trailing off ("healthy pullback", not "healthy pullback
#: into the"). Presentation only: the result is still a verbatim substring of
#: the source, and dropping a word never changes which marker fired.
_PHRASE_TRAILING = frozenset(
    """a an the and or but into onto on of to in at for from with by is are
    was were be been that this those these it its as if then than""".split()
)


@dataclass(frozen=True)
class Occurrence:
    """One match, located in the original text.

    Line and column are 1-based and point into the source as the author
    wrote it, not into the normalised copy the scan runs over. A phrase that
    straddles a line break is described by its line span and absolute
    character offsets, because a column range would be meaningless there.
    """

    text: str
    line: int
    column: int
    end_line: int
    end_column: int
    start: int
    end: int

    def describe(self) -> str:
        if self.line == self.end_line:
            return "line %d, characters %d-%d" % (
                self.line,
                self.column,
                self.end_column,
            )
        return "lines %d-%d, character offsets %d-%d" % (
            self.line,
            self.end_line,
            self.start,
            self.end - 1,
        )


@dataclass(frozen=True)
class TermFinding:
    """A ruled lexicon term found in the source."""

    term: Term
    occurrences: tuple[Occurrence, ...]
    #: The declared windows scanned for re-basing, one per occurrence, in the
    #: same order. Empty for a REFUSE term, which is not scanned: it refuses
    #: already, and there is no ruled basis for context to displace.
    scanned_windows: tuple[Occurrence, ...] = ()
    #: Declared qualifiers found inside those windows that attached to
    #: nothing, and so did not re-base the term. This is the honest half of a
    #: precision-first guard: the resolution reports what it saw and passed
    #: over, so a reviewer can judge the call instead of taking it on trust.
    unattached: tuple[QualifierHit, ...] = ()

    @property
    def location(self) -> str:
        return "; ".join(occurrence.describe() for occurrence in self.occurrences)

    @property
    def scanned_text(self) -> str:
        """The inspected windows, verbatim, deduplicated in order."""
        seen: list[str] = []
        for window in self.scanned_windows:
            if window.text not in seen:
                seen.append(window.text)
        return " / ".join(seen)


#: Recorded on a hit the guard saw but did not treat as re-basing. Emitted
#: rather than discarded: a resolution that says which declared qualifiers it
#: chose to ignore is reviewable, and one that silently drops them is not.
NOT_ATTACHED = "NOT_ATTACHED"


@dataclass(frozen=True)
class QualifierHit:
    """One declared re-basing construction, found in a term's window.

    ``attachment`` is the declared form by which it attaches to the ruled
    measurement (SLOT, COMPLEMENT or GLOSS), or ``NOT_ATTACHED`` when it was
    found and deliberately not treated as re-basing.
    """

    qualifier: BasisQualifier
    occurrence: Occurrence
    attachment: str

    def describe(self) -> str:
        return "%s (%s) attached as %s at %s: %r" % (
            self.qualifier.qualifier_id,
            self.qualifier.reason,
            self.attachment,
            self.occurrence.describe(),
            self.occurrence.text,
        )


@dataclass(frozen=True)
class RebasedFinding:
    """A ruled PARAMETERISE term whose context re-bases it. Fails closed.

    The term matched, and its ruling would have resolved it. What stops that
    is the declared vocabulary finding a construction in the term's window
    that names a different measurement basis. The ruling covers the phrase
    the lexicon declares, not a different claim built around it, so this is
    an undeclared term and an undeclared term refuses.
    """

    item_id: str
    term: Term
    occurrences: tuple[Occurrence, ...]
    hits: tuple[QualifierHit, ...]
    #: The full span from the earliest to the latest of the term match and
    #: the qualifying text, quoted verbatim. This, not the bare matched
    #: phrase, is what a human needs in order to see the mis-resolution.
    context: Occurrence
    #: The declared window that was inspected, quoted verbatim.
    window: Occurrence

    @property
    def location(self) -> str:
        return "; ".join(occurrence.describe() for occurrence in self.occurrences)

    @property
    def qualifier_summary(self) -> str:
        return "; ".join(hit.describe() for hit in self.hits)

    @property
    def qualifier_phrases(self) -> str:
        """Just the offending phrases, quoted, for a one-line restatement."""
        seen: list[str] = []
        for hit in self.hits:
            text = " ".join(hit.occurrence.text.split())
            if text not in seen:
                seen.append(text)
        return ", ".join('"%s"' % text for text in seen)


@dataclass(frozen=True)
class UnknownFinding:
    """Discretionary language with no lexicon ruling. Fails closed."""

    item_id: str
    marker: Marker
    phrase: str
    occurrences: tuple[Occurrence, ...]

    @property
    def location(self) -> str:
        return "; ".join(occurrence.describe() for occurrence in self.occurrences)


@dataclass(frozen=True)
class SlotOccupant:
    """One unresolved thing found inside a term's wildcard slot."""

    #: ``REFUSE_TERM``, ``DISCRETIONARY_MARKER`` or ``RULED_TERM`` — the last
    #: being a second PARAMETERISE ruling claiming the same words.
    kind: str
    #: The lexicon identity that recognised it: a term_id or a marker_id.
    identity: str
    #: Why it is unresolved, in the lexicon's own words.
    reason: str
    occurrence: Occurrence

    def describe(self) -> str:
        return "%s (%s: %s) at %s: %r" % (
            self.identity,
            self.kind,
            self.reason,
            self.occurrence.describe(),
            " ".join(self.occurrence.text.split()),
        )


@dataclass(frozen=True)
class UnruledSlotFinding:
    """A PARAMETERISE term whose own modifier slot holds unruled language.

    The slot is the run of words a term's pattern tolerates between its ruled
    adjective and its ruled head noun. Those words modify the MEASUREMENT, so
    if one of them is a REFUSE term or an unruled discretionary marker, the
    source has not finished saying what it wants measured. Resolving the term
    anyway would declare a parameter over the top of undefined language, which
    is the silent guess PID line 39 forbids — so it fails closed, exactly like
    an undeclared term.
    """

    item_id: str
    term: Term
    occurrences: tuple[Occurrence, ...]
    #: The slot text itself, quoted verbatim, one per offending occurrence.
    slots: tuple[Occurrence, ...]
    occupants: tuple[SlotOccupant, ...]

    @property
    def location(self) -> str:
        return "; ".join(occurrence.describe() for occurrence in self.occurrences)

    @property
    def slot_text(self) -> str:
        seen: list[str] = []
        for slot in self.slots:
            text = " ".join(slot.text.split()).strip(" -")
            if text and text not in seen:
                seen.append(text)
        return " / ".join(seen)

    @property
    def occupant_summary(self) -> str:
        return "; ".join(occupant.describe() for occupant in self.occupants)


@dataclass(frozen=True)
class ContestedMatchFinding:
    """A PARAMETERISE term whose ruled phrase itself overlaps a refusal.

    Not the slot — the LITERAL words. "no-wick close to resistance" gives the
    ruled word "close" to ``no_wick_candle`` and to ``near_resistance`` at the
    same time. One reading is a candle that closed without a wick; the other is
    an entry taken close to resistance. The lexicon rules on both phrases and
    the source has written them over the top of one another, so which one it
    means is exactly what is undefined.

    Overlap resolution is allowed to decide which term PARAMETERISES. It is not
    allowed to decide that the loser was never said. So the refusal is reported
    on its own terms, and the ruled term does not resolve: a parameter declared
    here would be a parameter for whichever reading the analyser happened to
    sort first, which is the silent guess PID line 39 forbids.
    """

    item_id: str
    term: Term
    occurrences: tuple[Occurrence, ...]
    #: The colliding text, quoted verbatim: from the earlier of the term match
    #: and the occupant to the later of the two, so a reader sees the collision
    #: rather than one half of it.
    contexts: tuple[Occurrence, ...]
    occupants: tuple[SlotOccupant, ...]

    @property
    def location(self) -> str:
        return "; ".join(occurrence.describe() for occurrence in self.occurrences)

    @property
    def context_text(self) -> str:
        seen: list[str] = []
        for context in self.contexts:
            text = " ".join(context.text.split())
            if text and text not in seen:
                seen.append(text)
        return " / ".join(seen)

    @property
    def occupant_summary(self) -> str:
        return "; ".join(occupant.describe() for occupant in self.occupants)


@dataclass(frozen=True)
class StraddledMatchFinding:
    """A recognised term match that runs from one sentence into the next.

    A ruled term is a phrase and a phrase does not straddle a full stop, so
    this match may not be treated as a ruling: it may not resolve a parameter,
    and — the half that matters more — it may not suppress scanning, because
    keeping it would hide everything on the far side of that stop. Both of
    those were already true. What was NOT true is that it gets reported.

    For four audits this was a bare ``continue``. The match was thrown away
    before it entered any collection, so it never reached the overlap contest,
    never reached the slot scan, and produced no finding of any kind. It was
    the third of exactly three rules that can stop a recognised match
    resolving, and the only one with no declared disposition and no emitted
    item — which is why five audits in a row found "a recognised term deleted
    without being reported" and four repairs in a row closed a different door.

    So it now says both things at once, which is what the original comment's
    concern actually requires: the match is NOT accepted (nothing is
    suppressed, and every other term and marker still scans the far side of
    the boundary freely), AND the span is reported (the reader is told that
    HSA's pattern for a ruled term reached across a sentence boundary here,
    and that HSA will not read it as that term). Neither half is a guess.
    """

    item_id: str
    term: Term
    #: The straddling spans themselves, quoted verbatim, in document order.
    occurrences: tuple[Occurrence, ...]
    #: The declared terminator set the span ran across, for the message.
    terminators: str

    @property
    def location(self) -> str:
        return "; ".join(occurrence.describe() for occurrence in self.occurrences)

    @property
    def context_text(self) -> str:
        seen: list[str] = []
        for occurrence in self.occurrences:
            text = " ".join(occurrence.text.split())
            if text and text not in seen:
                seen.append(text)
        return " / ".join(seen)


#: The closed set of reasons a recognised term match may be accounted for.
#: Every recognised match must carry exactly one of these by the end of the
#: scan, and ``_verify_every_recognised_match_is_reported`` checks each one
#: against the findings actually emitted. Adding a new way to stop a match
#: resolving means adding a reason here and an emitted finding to back it;
#: there is deliberately no reason meaning "dropped".
RESOLVED_OR_REFUSED = "REPORTED_AS_TERM"
REBASED = "REPORTED_AS_REBASED"
UNRULED_SLOT = "REPORTED_AS_UNRULED_SLOT"
CONTESTED = "REPORTED_AS_CONTESTED"
STRADDLED = "REPORTED_AS_STRADDLING_A_SENTENCE_BOUNDARY"
COVERED_BY_RULING = "COVERED_END_TO_END_BY_AN_ACCEPTED_RULING"

_ACCOUNTING_REASONS = frozenset(
    {
        RESOLVED_OR_REFUSED,
        REBASED,
        UNRULED_SLOT,
        CONTESTED,
        STRADDLED,
        COVERED_BY_RULING,
    }
)


@dataclass(frozen=True)
class Analysis:
    text: str
    lexicon: Lexicon
    term_findings: tuple[TermFinding, ...]
    unknown_findings: tuple[UnknownFinding, ...]
    rebased_findings: tuple[RebasedFinding, ...] = ()
    unruled_slot_findings: tuple[UnruledSlotFinding, ...] = ()
    #: PARAMETERISE terms whose ruled phrase itself collides with a refusal or
    #: an unruled marker. Separate from the slot findings above only because
    #: the two need different words to explain themselves; both fail closed.
    contested_findings: tuple[ContestedMatchFinding, ...] = ()
    #: Recognised term matches that ran across a sentence boundary. Not
    #: accepted as rulings — they suppress nothing — and not discarded either,
    #: which is the whole of R8: this was the third and last rule that could
    #: stop a match resolving without saying so.
    straddled_findings: tuple[StraddledMatchFinding, ...] = ()
    #: The lowercased, whitespace-collapsed copy the scan actually ran over.
    normalised: str = ""
    #: Spans of ``normalised`` that a ruled term LITERALLY claimed — the
    #: matched spans minus their wildcard slots. Exposed because it is the
    #: exact thing this analyser is allowed to stop scanning, and a guarantee
    #: nobody can inspect is a guarantee nobody can check: see
    #: ``tests/test_ambiguity.py``, which asserts that nothing recognisable as
    #: discretionary hides outside these spans without being reported.
    ruled_spans: tuple[tuple[int, int], ...] = ()

    @property
    def parameterised(self) -> tuple[TermFinding, ...]:
        return tuple(f for f in self.term_findings if f.term.disposition == PARAMETERISE)

    @property
    def refused(self) -> tuple[TermFinding, ...]:
        return tuple(f for f in self.term_findings if f.term.disposition != PARAMETERISE)


def normalise(text: str) -> tuple[str, list[int]]:
    """Lowercase and collapse whitespace, keeping a map back to the original.

    ``index_map[i]`` is the offset in ``text`` of normalised character ``i``,
    which is what lets every finding quote the source verbatim and cite a
    real line and column rather than a position in a mangled copy.
    """
    chars: list[str] = []
    index_map: list[int] = []
    previous_was_space = False
    for offset, char in enumerate(text):
        if char.isspace():
            if previous_was_space or not chars:
                continue
            chars.append(" ")
            index_map.append(offset)
            previous_was_space = True
        else:
            chars.append(char.lower())
            index_map.append(offset)
            previous_was_space = False
    while chars and chars[-1] == " ":
        chars.pop()
        index_map.pop()
    return "".join(chars), index_map


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for offset, char in enumerate(text):
        if char == "\n":
            starts.append(offset + 1)
    return starts


def _locate(text: str, starts: Sequence[int], offset: int) -> tuple[int, int]:
    low, high = 0, len(starts) - 1
    while low < high:
        mid = (low + high + 1) // 2
        if starts[mid] <= offset:
            low = mid
        else:
            high = mid - 1
    return low + 1, offset - starts[low] + 1


def _occurrence(
    text: str, index_map: Sequence[int], starts: Sequence[int], start: int, end: int
) -> Occurrence:
    origin_start = index_map[start]
    origin_end = index_map[end - 1] + 1
    line, column = _locate(text, starts, origin_start)
    end_line, end_column = _locate(text, starts, origin_end - 1)
    return Occurrence(
        text=text[origin_start:origin_end],
        line=line,
        column=column,
        end_line=end_line,
        end_column=end_column,
        start=origin_start,
        end=origin_end,
    )


def _origin_occurrence(
    text: str, starts: Sequence[int], origin_start: int, origin_end: int
) -> Occurrence:
    """An Occurrence built from offsets already in the ORIGINAL text.

    ``_occurrence`` maps normalised offsets back through the index map. A span
    assembled from two findings that have already been located is in original
    coordinates and must not be mapped a second time.
    """
    line, column = _locate(text, starts, origin_start)
    end_line, end_column = _locate(text, starts, max(origin_start, origin_end - 1))
    return Occurrence(
        text=text[origin_start:origin_end],
        line=line,
        column=column,
        end_line=end_line,
        end_column=end_column,
        start=origin_start,
        end=origin_end,
    )


def _widen(norm: str, end: int) -> int:
    """Extend an unknown marker hit over the next few words, for context.

    A bare marker word is a poor thing to put in front of a human: "healthy"
    on its own does not say what was being described. Widening quotes the
    phrase the marker qualifies, still verbatim from the source.
    """
    cursor = end
    words = 0
    while words < _PHRASE_WORDS and cursor < len(norm):
        if norm[cursor] != " ":
            break
        probe = cursor + 1
        scan = probe
        while scan < len(norm) and norm[scan] not in _PHRASE_STOP:
            scan += 1
        if scan == probe:
            break
        cursor = scan
        words += 1
    while True:
        trimmed = norm[end:cursor].rstrip()
        if not trimmed:
            break
        last = trimmed.rsplit(" ", 1)[-1]
        if last not in _PHRASE_TRAILING:
            break
        cursor = end + len(trimmed) - len(last)
        cursor = end + len(norm[end:cursor].rstrip())
    return cursor


def _slug(value: str, limit: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    return slug[:limit].rstrip("_")


def _is_terminator(norm: str, index: int, stops: frozenset) -> bool:
    """Whether the character at ``index`` actually ends a sentence.

    A ``.`` INSIDE a token is not a full stop. This used to be stated only for
    the decimal case — a ``.`` between two DIGITS — and that narrowness is
    where the fifth audit's defect came in. "1.5" was safe; "m.a", "h.4",
    "4.hour", "vwap.session" and "a.m" were each read as a sentence ending
    mid-word, so a term match spanning one of them was judged to cross a
    boundary and was thrown away. Those are exactly the abbreviations that
    arrive through VIDEO_DERIVED and TRADER_EXPLANATION intake (PID lines
    104-105), and "I only take a valid m.a breakout of the range" lost a PID
    line 118 must-not-guess phrase to it, silently, at exit 0.

    So the exception is stated at the level it was always about: a terminator
    character with a word character on BOTH sides is inside a token, not
    between two sentences. The decimal case is the special case of that, not
    the rule. "trade. some" still ends a sentence (a space follows), and so
    does "the range." at the end of the text, and "the range.)" before a
    bracket — the exception needs word characters on both sides, so it cannot
    swallow real punctuation.

    Only ``.`` takes the exception, because ``.`` is the only terminator that
    has an intra-token job in trading prose (decimals, abbreviations, dotted
    timeframe and session tokens) and the only one a term pattern's declared
    slot is allowed to consume. Widening it further would mean guessing.

    The terminator SET is declared in the lexicon; so is this exception, in
    ``term_match_policy.sentence_boundary.intra_token_exception``. Neither is
    assumed here.
    """
    char = norm[index]
    if char not in stops:
        return False
    if char != ".":
        return True
    before = norm[index - 1] if index else ""
    after = norm[index + 1] if index + 1 < len(norm) else ""
    return not (before.isalnum() and after.isalnum())


def _sentence_bounds(norm: str, terminators: str) -> list[tuple[int, int]]:
    """Cut ``norm`` into sentence spans on the declared terminator set.

    The terminators come from the lexicon, not from here, because the size of
    the inspected window is the reviewable half of the basis-qualifier guard.
    Runs of terminators and the space after them belong to the sentence they
    close, so every offset in ``norm`` falls inside exactly one span.
    """
    stops = frozenset(terminators)
    bounds: list[tuple[int, int]] = []
    start = 0
    index = 0
    length = len(norm)
    while index < length:
        if _is_terminator(norm, index, stops):
            while index < length and _is_terminator(norm, index, stops):
                index += 1
            while index < length and norm[index] == " ":
                index += 1
            bounds.append((start, index))
            start = index
            continue
        index += 1
    if start < length or not bounds:
        bounds.append((start, length))
    return bounds


def _sentence_index(bounds: Sequence[tuple[int, int]], offset: int) -> int:
    for index, (start, end) in enumerate(bounds):
        if start <= offset < end:
            return index
    return len(bounds) - 1


def _window_span(
    bounds: Sequence[tuple[int, int]], start: int, end: int, sentences_after: int
) -> tuple[int, int]:
    """The declared window around a term match: its sentence(s), plus N more."""
    first = _sentence_index(bounds, start)
    last = _sentence_index(bounds, max(start, end - 1))
    last = min(last + sentences_after, len(bounds) - 1)
    return bounds[first][0], bounds[last][1]


def _sentence_end(bounds: Sequence[tuple[int, int]], offset: int) -> int:
    """End of the sentence ``offset`` falls in."""
    return bounds[_sentence_index(bounds, offset)][1]


def _slot_span(match: "re.Match[str]", start: int) -> tuple[int, int]:
    """The term match's declared modifier slot, as an absolute span.

    Empty when the pattern's slot consumed no words, and empty when the
    branch that matched declares no slot at all (a pattern may declare the
    group on one alternative only). An empty slot attaches nothing, which is
    correct: there are no modifiers to attach.
    """
    try:
        slot_start, slot_end = match.span(BASIS_SLOT_GROUP)
    except (IndexError, re.error):
        return (start, start)
    if slot_start < 0:
        return (start, start)
    return (slot_start, slot_end)


def _ruled_spans(
    start: int, end: int, slot: tuple[int, int]
) -> list[tuple[int, int]]:
    """The parts of a term match that are actually the RULED phrase.

    Everything the pattern spelled out, and nothing the wildcard slot swept up.
    This is what suppresses further scanning: a ruled phrase should not be
    reported twice, but the words between "large" and "wick" were never ruled
    on by anybody, and suppressing them is how "near resistance" disappeared.
    """
    slot_start, slot_end = slot
    if not start <= slot_start <= slot_end <= end or slot_end == slot_start:
        return [(start, end)]
    spans = [span for span in ((start, slot_start), (slot_end, end)) if span[0] < span[1]]
    return spans or [(start, end)]


def _overlaps(spans: Sequence[tuple[int, int]], start: int, end: int) -> bool:
    return any(start < taken_end and taken_start < end for taken_start, taken_end in spans)


def _covered(spans: Sequence[tuple[int, int]], start: int, end: int) -> bool:
    """Whether EVERY character of ``[start, end)`` lies inside ``spans``.

    This is the only thing that justifies suppressing a recognised match, and
    it is deliberately stricter than ``_overlaps``. Suppression says "the
    lexicon has already ruled on this"; that claim is true when a ruling
    covers the whole of the thing, and false when a ruling covers part of it.
    Overlap was used for the claim for three audits, and every time the answer
    was the same silent hole: "close to resistance" merely TOUCHES the ruled
    word "close" in "no-wick close", so overlap called it ruled, dropped it,
    and a PID line 115 must-not-guess phrase left no trace at all.

    Partial coverage is not a ruling. It is two readings of the same words,
    which is precisely the condition the source has to resolve.
    """
    cursor = start
    for span_start, span_end in sorted(spans):
        if span_start > cursor:
            break
        if span_end > cursor:
            cursor = span_end
        if cursor >= end:
            return True
    return cursor >= end


def _crosses_sentence(
    bounds: Sequence[tuple[int, int]], start: int, end: int
) -> bool:
    """Whether a match runs from one sentence into the next.

    A ruled term is a phrase, and a phrase does not straddle a full stop. This
    is checked on the MATCH rather than left to each pattern's character
    classes, so it holds for every term the lexicon declares now and every one
    it declares later.
    """
    return _sentence_index(bounds, start) != _sentence_index(bounds, max(start, end - 1))


def _anchor_words(norm: str, start: int, end: int, slot: tuple[int, int]) -> tuple[str, ...]:
    """The ruled words this match actually consumed, slot contents excluded.

    These are what a GLOSS has to name in order to be attached to this term:
    "by LARGE I mean twice the ATR" is a re-basing of "a large wick"; the same
    sentence without "large" in it defines something else.
    """
    slot_start, slot_end = slot
    if start < slot_start and slot_end <= end:
        text = norm[start:slot_start] + " " + norm[slot_end:end]
    else:
        text = norm[start:end]
    words: list[str] = []
    for word in re.split(r"[^a-z0-9.%]+", text):
        if word and word not in words:
            words.append(word)
    return tuple(words)


def _declared_hits(
    norm: str,
    qualifiers: Sequence[BasisQualifier],
    window: tuple[int, int],
) -> list[tuple[int, int, BasisQualifier]]:
    """Every declared qualifier construction inside ``window``.

    Hits INSIDE the term's own matched span are kept, not dropped. They used
    to be dropped as "part of the ruled phrase the lexicon already declares",
    which is false: a PARAMETERISE pattern tolerates a wildcard run of words
    between its ruled adjective and its ruled head noun, and that wildcard is
    precisely where a re-basing lands ("a large ATR wick"). Whether a hit
    counts is decided by ``_attachment``, not by where the match happens to
    fall. Order is fixed: leftmost, then longest, then qualifier_id.
    """
    found: list[tuple[int, int, BasisQualifier]] = []
    seen: set[tuple[int, int, str]] = set()
    window_start, window_end = window
    for qualifier in qualifiers:
        for match in qualifier.pattern.finditer(norm, window_start, window_end):
            start, end = match.start(), match.end()
            if end <= start:
                continue
            key = (start, end, qualifier.qualifier_id)
            if key in seen:
                continue
            seen.add(key)
            found.append((start, end, qualifier))
    found.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2].qualifier_id))
    return found


def _attachment(
    norm: str,
    lexicon: Lexicon,
    bounds: Sequence[tuple[int, int]],
    window: tuple[int, int],
    term_span: tuple[int, int],
    slot_span: tuple[int, int],
    anchors: Sequence[str],
) -> tuple[
    list[tuple[int, int, BasisQualifier, str]],
    list[tuple[int, int, BasisQualifier]],
]:
    """Split the declared hits in ``window`` into attached and unattached.

    A qualifier re-bases the ruled term only when the lexicon's declared
    attachment ruling says it is bound to the measurement. Co-occurrence in
    the same sentence is not attachment: "a large wick. My stop is 2 ATR
    below entry" names ATR as the size of a STOP, and refusing that would
    refuse a correct strategy description. See the module docstring and
    ``basis_qualifier_policy.attachment``.

    Returns ``(attached, unattached)``; the term refuses if ``attached`` is
    non-empty, and reports ``unattached`` either way.
    """
    attachment = lexicon.attachment
    window_start, window_end = window
    term_start, term_end = term_span
    slot_start, slot_end = slot_span

    found = _declared_hits(norm, lexicon.basis_qualifiers, window)
    forms: dict[tuple[int, int, str], str] = {}

    # Form SLOT — inside the term's own modifier slot. Any category attaches:
    # a word sitting between "large" and "wick" modifies the measurement, and
    # there is nothing else in the slot for it to modify.
    if slot_end > slot_start:
        for start, end, qualifier in found:
            if start < slot_end and slot_start < end:
                forms[(start, end, qualifier.qualifier_id)] = "SLOT"

    # Form COMPLEMENT — a COMPARATIVE standing as the term's own complement.
    # ``zones`` collects the spans whose contents name the displacing basis,
    # so the refusal can quote the whole construction and not just its hinge.
    zones: list[tuple[int, int, str]] = []
    for start, end, qualifier in found:
        if qualifier.category not in attachment.complement_categories:
            continue
        if start < term_end:
            continue
        if attachment.complement_filler.fullmatch(norm[term_end:start]) is None:
            continue
        forms.setdefault((start, end, qualifier.qualifier_id), "COMPLEMENT")
        zones.append((start, min(_sentence_end(bounds, start), window_end), "COMPLEMENT"))

    # Form GLOSS — the source restates one of the term's own ruled words and
    # then defines it. This is the only form that reaches past the term's own
    # sentence; how far it reaches is window.sentences_after.
    if anchors:
        for gloss in attachment.gloss_constructions:
            for match in gloss.compile_for(anchors).finditer(
                norm, window_start, window_end
            ):
                if match.start() < term_start:
                    continue
                zones.append(
                    (
                        match.end(),
                        min(_sentence_end(bounds, match.start()), window_end),
                        "GLOSS",
                    )
                )

    # A qualifier lying inside an attached comparative's complement, or after
    # an attached gloss, is part of the basis that construction states.
    for start, end, qualifier in found:
        key = (start, end, qualifier.qualifier_id)
        if key in forms:
            continue
        for zone_start, zone_end, form in zones:
            if zone_start <= start < zone_end:
                forms[key] = form
                break

    attached = [
        (start, end, qualifier, forms[(start, end, qualifier.qualifier_id)])
        for start, end, qualifier in found
        if (start, end, qualifier.qualifier_id) in forms
    ]
    unattached = [
        (start, end, qualifier)
        for start, end, qualifier in found
        if (start, end, qualifier.qualifier_id) not in forms
    ]
    return attached, unattached


def _dedupe_hits(hits: Sequence[tuple]) -> list[tuple]:
    """One construction, reported once, in a fixed order.

    A term matching twice inside one window finds the same constructions
    twice, and two occurrences can contribute them out of document order, so
    the emitted item would otherwise vary run to run.
    """
    seen: set[tuple[int, int, str]] = set()
    unique: list[tuple] = []
    for hit in hits:
        key = (hit[0], hit[1], hit[2].qualifier_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
    unique.sort(key=lambda hit: (hit[0], -(hit[1] - hit[0]), hit[2].qualifier_id))
    return unique


def _unique_item_id(candidate: str, used: set[str], fallback: str) -> str:
    """A contract-shaped, unique ``item_id``. One rule, used by every finding.

    An unresolved item is addressed by its ``item_id``, so two items sharing
    one would make a refusal ambiguous about which thing needs resolving.
    """
    item_id = candidate[:64]
    if not re.match(r"^[a-z][a-z0-9_]{2,63}$", item_id):
        item_id = fallback
    suffix = 2
    unique = item_id
    while unique in used:
        unique = "%s_%d" % (item_id[:60], suffix)
        suffix += 1
    used.add(unique)
    return unique


def _match_occupants(
    norm: str,
    text: str,
    index_map: Sequence[int],
    starts: Sequence[int],
    span: tuple[int, int],
    slot: tuple[int, int],
    literals: Sequence[tuple[int, int]],
    lexicon: Lexicon,
    collisions: Sequence[tuple[int, int, Term]] = (),
) -> tuple[list[SlotOccupant], list[SlotOccupant]]:
    """Unresolved language overlapping a PARAMETERISE term's own match.

    Two kinds count, and they are the two kinds that fail closed anywhere else
    in the source: a ruled term the lexicon REFUSES, and a discretionary marker
    with no ruling at all.

    THIS IS A DIRECT SCAN, not a filter over what the main passes accepted, and
    the difference is the whole point. The main passes resolve overlaps: one
    stretch of text belongs to one term. Asking the narrower question here — is
    there unresolved language touching this match? — does not care who won that
    contest, so a refusal cannot be hidden by winning or losing it.

    THE REGION SCANNED IS THE WHOLE MATCH, not the wildcard slot alone. Scoping
    it to the slot was the third repair of this defect and it held exactly as
    far as the slot did: "no-wick close to resistance" puts near_resistance on
    the term's own LITERAL head noun ("close"), nowhere near the slot, and the
    refusal vanished at exit 0. The region a ruled phrase can hide something in
    is the region it occupies, so that is the region that is asked about.

    WHAT IS EXCLUDED, AND WHY ONLY THAT. A discretionary marker COVERED end to
    end by this match's own literal spans is the term's own ruled word —
    "large" in "large wick" is why large_wick exists, and reporting it would
    refuse every term the lexicon parameterises. A REFUSE term is never
    excluded, even if it falls wholly inside a literal: that is two rulings
    claiming the same words, and preferring the PARAMETERISE one silently is
    the defect this function exists to stop. No lexicon declares such a pair
    today; the rule is written for the one that does.

    A qualifier that RE-BASES the term is not one of these. That is the
    separate SLOT attachment form, ruled on by ``basis_qualifier_policy``, and
    it produces its own finding.

    ``collisions`` carries the other accepted term matches. A second ruling
    overlapping this one is the same condition seen from the other side and is
    reported the same way, whatever its disposition: "a large no-wick candle"
    is large_wick and no_wick_candle claiming one phrase between them, and
    letting the sort order pick which threshold gets declared is a guess about
    a contradiction, not a resolution of it. A collision is always reported as
    contested, never as slot content, because what is undefined is the overlap
    and not the wildcard.

    Returns ``(slot_occupants, literal_occupants)``. Both stop the term
    resolving; they are separated only so the refusal can explain itself in the
    right words — a wildcard nobody ruled on is a different thing to say than
    two rulings claiming one phrase.
    """
    match_start, match_end = span
    slot_start, slot_end = slot
    if match_end <= match_start:
        return [], []

    def touches(start: int, end: int) -> bool:
        return start < match_end and match_start < end

    def in_slot(start: int, end: int) -> bool:
        return slot_end > slot_start and start < slot_end and slot_start < end

    refused: list[tuple[int, int, Term]] = []
    for term in lexicon.terms:
        if term.disposition == PARAMETERISE:
            continue
        for match in term.pattern.finditer(norm):
            if match.end() > match.start() and touches(match.start(), match.end()):
                refused.append((match.start(), match.end(), term))

    occupants: list[tuple[int, int, SlotOccupant]] = [
        (
            start,
            end,
            SlotOccupant(
                kind="REFUSE_TERM",
                identity=term.term_id,
                reason='the ruled term "%s", which the lexicon refuses' % term.label,
                occurrence=_occurrence(text, index_map, starts, start, end),
            ),
        )
        for start, end, term in refused
    ]
    for marker in lexicon.markers:
        for match in marker.pattern.finditer(norm):
            start, end = match.start(), match.end()
            if end <= start or not touches(start, end):
                continue
            # The term's own ruled word, ruled in full by this very match.
            if _covered(literals, start, end):
                continue
            # A marker inside a refusal already listed above is that refusal's
            # own wording, not a second finding: "near" is why near_resistance
            # is unresolved, and reporting both says one thing twice.
            if any(start < taken_end and taken_start < end
                   for taken_start, taken_end, _term in refused):
                continue
            occupants.append(
                (
                    start,
                    end,
                    SlotOccupant(
                        kind="DISCRETIONARY_MARKER",
                        identity=marker.marker_id,
                        reason=marker.reason,
                        occurrence=_occurrence(
                            text, index_map, starts, start, _widen(norm, end)
                        ),
                    ),
                )
            )

    colliding: list[SlotOccupant] = []
    for start, end, term in collisions:
        if (start, end) == span or not touches(start, end):
            continue
        colliding.append(
            SlotOccupant(
                kind="RULED_TERM",
                identity=term.term_id,
                reason=(
                    'the ruled term "%s", which the lexicon rules onto a '
                    "different measurement" % term.label
                ),
                occurrence=_occurrence(text, index_map, starts, start, end),
            )
        )

    in_the_slot: list[SlotOccupant] = []
    on_the_literal: list[SlotOccupant] = []
    seen: set[tuple[str, int, int]] = set()
    for start, end, occupant in sorted(
        occupants,
        key=lambda item: (item[2].occurrence.start, item[2].kind, item[2].identity),
    ):
        key = (occupant.identity, occupant.occurrence.start, occupant.occurrence.end)
        if key in seen:
            continue
        seen.add(key)
        if in_slot(start, end):
            in_the_slot.append(occupant)
        else:
            on_the_literal.append(occupant)
    for occupant in colliding:
        key = (occupant.identity, occupant.occurrence.start, occupant.occurrence.end)
        if key in seen:
            continue
        seen.add(key)
        on_the_literal.append(occupant)
    on_the_literal.sort(
        key=lambda item: (item.occurrence.start, item.kind, item.identity)
    )
    return in_the_slot, on_the_literal


def analyse(text: str, lexicon: Lexicon) -> Analysis:
    """Scan ``text`` against ``lexicon`` and return every finding."""
    norm, index_map = normalise(text)
    starts = _line_starts(text)

    # One text, one set of sentence boundaries. ``term_match_policy`` and
    # ``basis_qualifier_policy.window`` are checked at load time to declare the
    # same terminator set, so the boundary a match may not cross and the
    # boundary that bounds a window are the same boundary.
    bounds = _sentence_bounds(norm, lexicon.sentence_terminators)

    # THE LEDGER. Every recognised term match is written down here the moment
    # it is recognised, and every one of them must leave the scan carrying
    # exactly one reason from ``_ACCOUNTING_REASONS`` — checked at the end,
    # against the findings actually emitted, by
    # ``_verify_every_recognised_match_is_reported``.
    #
    # This exists because "nothing HSA recognises as discretionary goes
    # unreported" was prose for five audits and each audit found a different
    # way through it. It is now a structural property of the scan rather than a
    # promise about it: there is no reason meaning "dropped", so a sixth way to
    # stop a match resolving cannot be added silently — it either declares its
    # reason and emits a finding, or the analyser raises.
    recognised: list[tuple[str, int, int]] = []
    accounted: dict[tuple[str, int, int], str] = {}

    # Pass 1 — ruled lexicon terms. Every match is collected first, then
    # overlaps are resolved by a fixed rule, so a longer ruled phrase always
    # beats a shorter one that starts in the same place. A match that runs from
    # one sentence into the next takes no part in that contest: it is not a
    # phrase, it is a wildcard slot that swallowed a full stop, and accepting it
    # would hide everything on the far side of that stop.
    #
    # It is not DISCARDED, though, and that distinction is R8. It used to be a
    # bare ``continue``, which answered the hiding concern and created the
    # opposite one: the recognised term vanished with no finding at all, so
    # "XAUUSD 15m breakout rules. I only take a valid m.a breakout of the
    # range." drafted at exit 0 with nothing unresolved, while the same
    # sentence without the dotted token refused for good_breakout (PID line
    # 118). Not accepting it and not reporting it are two different decisions,
    # and only the first of them was ever justified.
    candidates: list[tuple[int, int, int, Term, "re.Match[str]"]] = []
    straddling: dict[str, list[tuple[int, int]]] = {}
    straddling_terms: dict[str, Term] = {}
    for order, term in enumerate(lexicon.terms):
        for match in term.pattern.finditer(norm):
            if match.end() <= match.start():
                continue
            key = (term.term_id, match.start(), match.end())
            if key not in accounted:
                recognised.append(key)
            if _crosses_sentence(bounds, match.start(), match.end()):
                accounted[key] = STRADDLED
                straddling.setdefault(term.term_id, []).append(
                    (match.start(), match.end())
                )
                straddling_terms[term.term_id] = term
                continue
            candidates.append((match.start(), match.end(), order, term, match))
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))

    # ``ruled`` holds the LITERAL parts of the accepted matches only. A term's
    # declared basis_slot is wildcard text sitting between the ruled words, so
    # it neither belongs to the ruled phrase nor stops anything else being
    # found there — another ruled term, or a discretionary marker.
    #
    # A candidate is skipped only when the rulings already accepted COVER it
    # end to end. Overlapping one was the old test and it is what made this
    # contest able to delete a refusal: "close to resistance" overlaps the
    # ruled word "close" in "no-wick close", so near_resistance — PID line 115
    # — lost the contest and was never reported. Coverage is the honest test,
    # because coverage is what the word "ruled" is actually claiming. Two
    # matches that merely overlap are two readings of the same words, and both
    # are recorded; which of them PARAMETERISES is settled below, and a term
    # whose match collides with unresolved language does not parameterise at
    # all (``term_match_policy.overlap_resolution``).
    ruled: list[tuple[int, int]] = []
    accepted: list[tuple[int, int, Term, "re.Match[str]", tuple[int, int]]] = []
    for start, end, _order, term, match in candidates:
        if _covered(ruled, start, end):
            # Accounted for, not dropped: the accepted rulings claim this text
            # end to end, and each of those rulings is itself reported. The
            # verifier re-checks that coverage rather than taking it on trust.
            accounted[(term.term_id, start, end)] = COVERED_BY_RULING
            continue
        slot = _slot_span(match, start)
        ruled.extend(_ruled_spans(start, end, slot))
        accepted.append((start, end, term, match, slot))
    accepted.sort(key=lambda item: item[0])

    # The accepted matches as bare spans, for the collision check below. Two
    # rulings claiming one phrase is undefined language whichever dispositions
    # they carry, so this is not filtered by disposition.
    collisions = [(start, end, term) for start, end, term, _match, _slot in accepted]

    # Pass 2 — fail closed. Any declared discretionary marker that no ruled
    # term consumed is an unresolved item. This is the mechanism that stops an
    # unknown term passing through silently (PID line 39), and it runs before
    # the PARAMETERISE terms are allowed to resolve, because what it finds
    # touching a term's match is one of the things that stops them.
    #
    # "Consumed" is COVERAGE, not overlap, for the same reason as above: a
    # marker half inside a ruled phrase and half outside it has been ruled on
    # by nobody. "close to" straddling the ruled word "close" in "a no-wick
    # close to the 200 MA" is a proximity claim with no stated tolerance, and
    # dropping it because one of its two words was ruled is the same silent
    # path in marker form.
    unknown_hits: list[tuple[int, int, Marker]] = []
    for marker in lexicon.markers:
        for match in marker.pattern.finditer(norm):
            start, end = match.start(), match.end()
            if _covered(ruled, start, end):
                continue
            unknown_hits.append((start, end, marker))
    unknown_hits.sort(key=lambda item: (item[0], -(item[1] - item[0])))

    claimed: list[tuple[int, int]] = []
    marker_hits: list[tuple[int, int, int, Marker]] = []
    for start, end, marker in unknown_hits:
        if _overlaps(claimed, start, end):
            continue
        widened_end = _widen(norm, end)
        claimed.append((start, widened_end))
        marker_hits.append((start, end, widened_end, marker))

    # Pass 1b — the basis-qualifier check, and the slot check beside it. A
    # PARAMETERISE ruling covers the phrase the lexicon declares and nothing
    # else, so before a ruled term is allowed to resolve two questions are
    # asked of it:
    #
    #   1. does the declared window hold a declared re-basing construction that
    #      is ATTACHED to the ruled measurement? Finding a qualifier is not
    #      enough: the window bounds the search, the declared attachment forms
    #      decide the outcome. What this does not cover is stated in the
    #      lexicon's own basis_qualifier_policy['limits'] and repeated in every
    #      emitted resolution, because a guard that overstates itself is worse
    #      than none.
    #   2. does its own wildcard slot hold language that is itself unresolved —
    #      a REFUSE term, or a marker with no ruling? Those words modify the
    #      measurement, so undefined language there is undefined language about
    #      the measurement (term_match_policy.unruled_slot_content).
    window_policy = lexicon.basis_qualifier_policy["window"]
    sentences_after = int(window_policy["sentences_after"])

    term_occurrences: dict[str, list[Occurrence]] = {}
    term_windows: dict[str, list[Occurrence]] = {}
    term_by_id: dict[str, Term] = {}
    term_hits: dict[str, list[tuple[int, int, BasisQualifier, str]]] = {}
    term_unattached: dict[str, list[tuple[int, int, BasisQualifier]]] = {}
    term_context: dict[str, tuple[int, int]] = {}
    term_window_span: dict[str, tuple[int, int]] = {}
    slot_occupants: dict[str, list[SlotOccupant]] = {}
    slot_texts: dict[str, list[Occurrence]] = {}
    slot_occurrences: dict[str, list[Occurrence]] = {}
    contested_occupants: dict[str, list[SlotOccupant]] = {}
    contested_contexts: dict[str, list[Occurrence]] = {}
    contested_occurrences: dict[str, list[Occurrence]] = {}
    for start, end, term, match, slot in accepted:
        window = _window_span(bounds, start, end, sentences_after)
        occurrence = _occurrence(text, index_map, starts, start, end)
        term_occurrences.setdefault(term.term_id, []).append(occurrence)
        term_windows.setdefault(term.term_id, []).append(
            _occurrence(text, index_map, starts, window[0], window[1])
        )
        term_by_id[term.term_id] = term
        term_hits.setdefault(term.term_id, [])
        term_unattached.setdefault(term.term_id, [])
        slot_occupants.setdefault(term.term_id, [])
        contested_occupants.setdefault(term.term_id, [])
        if term.disposition != PARAMETERISE:
            # A REFUSE term already refuses; there is no ruled basis for
            # context to displace, so scanning it would only add noise.
            continue

        slot_start, slot_end = slot
        literals = _ruled_spans(start, end, slot)
        in_slot, on_literal = _match_occupants(
            norm,
            text,
            index_map,
            starts,
            (start, end),
            slot,
            literals,
            lexicon,
            collisions,
        )
        if in_slot:
            slot_occupants[term.term_id].extend(in_slot)
            slot_texts.setdefault(term.term_id, []).append(
                _occurrence(text, index_map, starts, slot_start, slot_end)
            )
            slot_occurrences.setdefault(term.term_id, []).append(occurrence)
        if on_literal:
            contested_occupants[term.term_id].extend(on_literal)
            contested_contexts.setdefault(term.term_id, []).append(
                _origin_occurrence(
                    text,
                    starts,
                    min([occurrence.start] + [o.occurrence.start for o in on_literal]),
                    max([occurrence.end] + [o.occurrence.end for o in on_literal]),
                )
            )
            contested_occurrences.setdefault(term.term_id, []).append(occurrence)

        hits, unattached = _attachment(
            norm,
            lexicon,
            bounds,
            window,
            (start, end),
            slot,
            _anchor_words(norm, start, end, slot),
        )
        term_unattached[term.term_id].extend(unattached)
        if not hits:
            continue
        if term.term_id not in term_context:
            term_context[term.term_id] = (
                min([start] + [hit[0] for hit in hits]),
                max([end] + [hit[1] for hit in hits]),
            )
            term_window_span[term.term_id] = window
        term_hits[term.term_id].extend(hits)

    # One term_id, one ruling. If any occurrence of a ruled term is re-based,
    # holds unresolved language in its own slot, or has its ruled phrase
    # contested by a refusal, the term does not resolve at all: its parameter
    # would be declared once for the whole draft, so there is no coherent way
    # to half-declare it, and the fail-closed direction is the one
    # docs/AMBIGUITY-POLICY.md takes.
    term_findings = tuple(
        TermFinding(
            term=term_by_id[term_id],
            occurrences=tuple(occurrences),
            scanned_windows=tuple(term_windows[term_id]),
            unattached=tuple(
                QualifierHit(
                    qualifier=qualifier,
                    occurrence=_occurrence(text, index_map, starts, hit_start, hit_end),
                    attachment=NOT_ATTACHED,
                )
                for hit_start, hit_end, qualifier in _dedupe_hits(
                    term_unattached[term_id]
                )
            ),
        )
        for term_id, occurrences in term_occurrences.items()
        if not term_hits[term_id]
        and not slot_occupants[term_id]
        and not contested_occupants[term_id]
    )

    used_item_ids: set[str] = {finding.term.term_id for finding in term_findings}

    rebased_findings: list[RebasedFinding] = []
    for term_id, occurrences in term_occurrences.items():
        # A term matching twice inside one window finds the same
        # constructions twice. Report each construction once.
        hits = _dedupe_hits(term_hits[term_id])
        if not hits:
            continue
        context_start, context_end = term_context[term_id]
        window = term_window_span[term_id]
        rebased_findings.append(
            RebasedFinding(
                item_id=_unique_item_id(
                    "rebased_" + term_id, used_item_ids, "rebased_term"
                ),
                term=term_by_id[term_id],
                occurrences=tuple(occurrences),
                hits=tuple(
                    QualifierHit(
                        qualifier=qualifier,
                        occurrence=_occurrence(
                            text, index_map, starts, hit_start, hit_end
                        ),
                        attachment=form,
                    )
                    for hit_start, hit_end, qualifier, form in hits
                ),
                context=_occurrence(
                    text, index_map, starts, context_start, context_end
                ),
                window=_occurrence(text, index_map, starts, window[0], window[1]),
            )
        )

    unruled_slot_findings: list[UnruledSlotFinding] = []
    for term_id, occupants in slot_occupants.items():
        if not occupants:
            continue
        unruled_slot_findings.append(
            UnruledSlotFinding(
                item_id=_unique_item_id(
                    "unruled_slot_" + term_id, used_item_ids, "unruled_slot_term"
                ),
                term=term_by_id[term_id],
                occurrences=tuple(slot_occurrences[term_id]),
                slots=tuple(slot_texts[term_id]),
                occupants=tuple(occupants),
            )
        )

    contested_findings: list[ContestedMatchFinding] = []
    for term_id, occupants in contested_occupants.items():
        if not occupants:
            continue
        contested_findings.append(
            ContestedMatchFinding(
                item_id=_unique_item_id(
                    "contested_" + term_id, used_item_ids, "contested_term"
                ),
                term=term_by_id[term_id],
                occurrences=tuple(contested_occurrences[term_id]),
                contexts=tuple(contested_contexts[term_id]),
                occupants=tuple(occupants),
            )
        )

    straddled_findings: list[StraddledMatchFinding] = []
    for term_id, spans in straddling.items():
        straddled_findings.append(
            StraddledMatchFinding(
                item_id=_unique_item_id(
                    "straddled_" + term_id, used_item_ids, "straddled_term"
                ),
                term=straddling_terms[term_id],
                occurrences=tuple(
                    _occurrence(text, index_map, starts, start, end)
                    for start, end in sorted(spans)
                ),
                terminators=lexicon.sentence_terminators,
            )
        )

    grouped: dict[tuple[str, str], list[Occurrence]] = {}
    markers_by_key: dict[tuple[str, str], Marker] = {}
    for start, _end, widened_end, marker in marker_hits:
        occurrence = _occurrence(text, index_map, starts, start, widened_end)
        key = (marker.marker_id, norm[start:widened_end])
        grouped.setdefault(key, []).append(occurrence)
        markers_by_key[key] = marker

    unknown_findings: list[UnknownFinding] = []
    for key, occurrences in grouped.items():
        _marker_id, phrase = key
        unknown_findings.append(
            UnknownFinding(
                item_id=_unique_item_id(
                    "unknown_" + (_slug(phrase, 55) or _slug(_marker_id, 55) or "term"),
                    used_item_ids,
                    "unknown_term",
                ),
                marker=markers_by_key[key],
                phrase=occurrences[0].text,
                occurrences=tuple(occurrences),
            )
        )

    # Every ACCEPTED match's reason is read off where its term_id actually
    # landed, not asserted here. A term_id that reached the end of the scan in
    # none of the finding collections has been deleted, and the verifier below
    # is what says so out loud.
    for start, end, term, _match, _slot in accepted:
        accounted[(term.term_id, start, end)] = _accepted_reason(
            term.term_id,
            term_findings,
            rebased_findings,
            unruled_slot_findings,
            contested_findings,
        )

    analysis = Analysis(
        text=text,
        lexicon=lexicon,
        term_findings=term_findings,
        unknown_findings=tuple(unknown_findings),
        rebased_findings=tuple(rebased_findings),
        unruled_slot_findings=tuple(unruled_slot_findings),
        contested_findings=tuple(contested_findings),
        straddled_findings=tuple(straddled_findings),
        normalised=norm,
        ruled_spans=tuple(sorted(ruled)),
    )
    _verify_every_recognised_match_is_reported(analysis, recognised, accounted, ruled)
    return analysis


def _accepted_reason(
    term_id: str,
    term_findings: Sequence[TermFinding],
    rebased_findings: Sequence[RebasedFinding],
    unruled_slot_findings: Sequence[UnruledSlotFinding],
    contested_findings: Sequence[ContestedMatchFinding],
) -> str:
    """Which finding collection an accepted term actually ended up in.

    Returned rather than assumed, and returned as ``""`` when the answer is
    "none of them" — which the verifier turns into a raised error naming the
    term. An accepted match that reaches the end of the scan in no collection
    is precisely the defect this whole repair sequence keeps re-finding.
    """
    if any(finding.term.term_id == term_id for finding in term_findings):
        return RESOLVED_OR_REFUSED
    if any(finding.term.term_id == term_id for finding in rebased_findings):
        return REBASED
    if any(finding.term.term_id == term_id for finding in unruled_slot_findings):
        return UNRULED_SLOT
    if any(finding.term.term_id == term_id for finding in contested_findings):
        return CONTESTED
    return ""


def _verify_every_recognised_match_is_reported(
    analysis: Analysis,
    recognised: Sequence[tuple[str, int, int]],
    accounted: Mapping[tuple[str, int, int], str],
    ruled: Sequence[tuple[int, int]],
) -> None:
    """THE CHOKE POINT. Every recognised match, or the scan raises.

    R6 closed the wildcard-slot path. R7 closed the overlap path. Both were
    correct and both left the general statement one word too narrow: the rule
    is not "overlap may never cause a recognised term to go unreported", it is
    that NOTHING may. R8's sentence-boundary path was the third of exactly
    three rules that can stop a recognised match resolving, and it survived
    four audits precisely because nothing checked the general statement.

    So this checks it, on the emitted Analysis, every run. Each recognised
    match must carry one declared reason, and the reason must be borne out by
    what was actually emitted:

    * a reason naming a finding kind must find the term in that collection;
    * ``COVERED_BY_RULING`` must still be covered end to end by the LITERAL
      spans of the accepted rulings when re-tested here. That is the same
      predicate the drop itself used, re-run against the finished span set
      rather than taken on trust — suppression requires a ruling that covers
      the text end to end, and a check that re-asked a weaker question would
      be checking something other than the rule.

    There is no reason meaning "dropped", which is the point. A future edit
    that adds a fourth way to stop a match resolving either declares a reason
    and emits a finding for it, or every source exercising it raises
    ``UnreportedMatchError`` — loudly, in the caller's face, instead of
    drafting at exit 0 with nothing unresolved.
    """
    reported: dict[str, set[str]] = {
        RESOLVED_OR_REFUSED: {f.term.term_id for f in analysis.term_findings},
        REBASED: {f.term.term_id for f in analysis.rebased_findings},
        UNRULED_SLOT: {f.term.term_id for f in analysis.unruled_slot_findings},
        CONTESTED: {f.term.term_id for f in analysis.contested_findings},
        STRADDLED: {f.term.term_id for f in analysis.straddled_findings},
    }
    for term_id, start, end in recognised:
        reason = accounted.get((term_id, start, end), "")
        quoted = analysis.normalised[start:end]
        if reason not in _ACCOUNTING_REASONS:
            raise UnreportedMatchError(
                "the analyser recognised the ruled term %r as %r at "
                "characters %d-%d and reached the end of the scan without "
                "either resolving it or reporting it (reason recorded: %r). "
                "That is the defect five audits found, in a new place: a "
                "recognised term deleted without being reported. Whatever "
                "stopped it resolving must declare a reason and emit a "
                "finding (see term_match_policy in the lexicon); nothing may "
                "simply drop it."
                % (term_id, quoted, start, end - 1, reason or None)
            )
        if reason == COVERED_BY_RULING:
            if not _covered(ruled, start, end):
                raise UnreportedMatchError(
                    "the analyser dropped its match of the ruled term %r (%r "
                    "at characters %d-%d) as already ruled on, but the "
                    "accepted rulings do not cover it end to end. Partial "
                    "coverage is not a ruling (term_match_policy."
                    "overlap_resolution)." % (term_id, quoted, start, end - 1)
                )
            continue
        if term_id not in reported[reason]:
            raise UnreportedMatchError(
                "the analyser recorded its match of the ruled term %r (%r at "
                "characters %d-%d) as %s, but no such finding was emitted for "
                "it. The reason and the report have come apart, which is how "
                "a recognised term goes missing without anything failing."
                % (term_id, quoted, start, end - 1, reason)
            )
