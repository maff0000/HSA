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

A TERM MATCH MAY NOT SPAN A SENTENCE BOUNDARY. The same wildcard let a match
run across a full stop — "a large trade. some wick setups only" matched
``large_wick`` — and swallow the start of the next sentence with it. The rule
is enforced here, on the match, rather than by tightening each pattern:
patterns are tightened too, but a pattern-level fix protects only the patterns
that exist today, and this one holds for a term nobody has declared yet. A
``.`` between two digits is a decimal point, not a terminator, so "1.5" stays
one token.

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
dict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

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

    #: ``REFUSE_TERM`` or ``DISCRETIONARY_MARKER``.
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
class Analysis:
    text: str
    lexicon: Lexicon
    term_findings: tuple[TermFinding, ...]
    unknown_findings: tuple[UnknownFinding, ...]
    rebased_findings: tuple[RebasedFinding, ...] = ()
    unruled_slot_findings: tuple[UnruledSlotFinding, ...] = ()
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

    A ``.`` between two digits is a decimal point, not a full stop. Without
    that exception "an upper wick of at least 0.60 of its range" is three
    sentences, and the sentence rules built on this — the qualifier window, and
    the rule that a term match may not cross a boundary — would both cut a
    number in half. The exception is declared in the lexicon beside the
    terminator set, not assumed here.
    """
    char = norm[index]
    if char not in stops:
        return False
    if char != ".":
        return True
    before = norm[index - 1] if index else ""
    after = norm[index + 1] if index + 1 < len(norm) else ""
    return not (before.isdigit() and after.isdigit())


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


def _slot_occupants(
    norm: str,
    text: str,
    index_map: Sequence[int],
    starts: Sequence[int],
    slot: tuple[int, int],
    lexicon: Lexicon,
) -> list[SlotOccupant]:
    """Unresolved language sitting inside a PARAMETERISE term's own slot.

    Two kinds count, and they are the two kinds that fail closed anywhere else
    in the source: a ruled term the lexicon REFUSES, and a discretionary marker
    with no ruling at all.

    THIS IS A DIRECT SCAN, not a filter over what the main passes accepted, and
    the difference is the whole point. The main passes resolve overlaps: one
    stretch of text belongs to one term. So a refusal that overlaps the ruled
    term BOTH ways — partly in the slot, partly sharing its head noun — loses
    that contest and vanishes, and "no wick confirmation candle" resolved at
    exit 0 while containing PID line 117's "confirmation candle" verbatim.
    Asking the narrower question here — is there unresolved language touching
    this slot? — does not care who won the overlap, so a refusal cannot be
    hidden by being adjacent to the ruled words as well as between them.

    A qualifier that RE-BASES the term is not one of these. That is the
    separate SLOT attachment form, ruled on by ``basis_qualifier_policy``, and
    it produces its own finding.
    """
    slot_start, slot_end = slot
    if slot_end <= slot_start:
        return []

    def touches(start: int, end: int) -> bool:
        return start < slot_end and slot_start < end

    refused: list[tuple[int, int, Term]] = []
    for term in lexicon.terms:
        if term.disposition == PARAMETERISE:
            continue
        for match in term.pattern.finditer(norm):
            if match.end() > match.start() and touches(match.start(), match.end()):
                refused.append((match.start(), match.end(), term))

    occupants = [
        SlotOccupant(
            kind="REFUSE_TERM",
            identity=term.term_id,
            reason='the ruled term "%s", which the lexicon refuses' % term.label,
            occurrence=_occurrence(text, index_map, starts, start, end),
        )
        for start, end, term in refused
    ]
    for marker in lexicon.markers:
        for match in marker.pattern.finditer(norm):
            start, end = match.start(), match.end()
            if end <= start or not touches(start, end):
                continue
            # A marker inside a refusal already listed above is that refusal's
            # own wording, not a second finding: "near" is why near_resistance
            # is unresolved, and reporting both says one thing twice.
            if any(start < taken_end and taken_start < end
                   for taken_start, taken_end, _term in refused):
                continue
            occupants.append(
                SlotOccupant(
                    kind="DISCRETIONARY_MARKER",
                    identity=marker.marker_id,
                    reason=marker.reason,
                    occurrence=_occurrence(
                        text, index_map, starts, start, _widen(norm, end)
                    ),
                )
            )

    unique: list[SlotOccupant] = []
    seen: set[tuple[str, int, int]] = set()
    for occupant in sorted(
        occupants, key=lambda item: (item.occurrence.start, item.kind, item.identity)
    ):
        key = (occupant.identity, occupant.occurrence.start, occupant.occurrence.end)
        if key in seen:
            continue
        seen.add(key)
        unique.append(occupant)
    return unique


def analyse(text: str, lexicon: Lexicon) -> Analysis:
    """Scan ``text`` against ``lexicon`` and return every finding."""
    norm, index_map = normalise(text)
    starts = _line_starts(text)

    # One text, one set of sentence boundaries. ``term_match_policy`` and
    # ``basis_qualifier_policy.window`` are checked at load time to declare the
    # same terminator set, so the boundary a match may not cross and the
    # boundary that bounds a window are the same boundary.
    bounds = _sentence_bounds(norm, lexicon.sentence_terminators)

    # Pass 1 — ruled lexicon terms. Every match is collected first, then
    # overlaps are resolved by a fixed rule, so a longer ruled phrase always
    # beats a shorter one that starts in the same place. A match that runs from
    # one sentence into the next is discarded before any of that: it is not a
    # phrase, it is a wildcard slot that swallowed a full stop, and keeping it
    # would hide everything on the far side of that stop.
    candidates: list[tuple[int, int, int, Term, "re.Match[str]"]] = []
    for order, term in enumerate(lexicon.terms):
        for match in term.pattern.finditer(norm):
            if match.end() <= match.start():
                continue
            if _crosses_sentence(bounds, match.start(), match.end()):
                continue
            candidates.append((match.start(), match.end(), order, term, match))
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))

    # ``ruled`` holds the LITERAL parts of the accepted matches only. A term's
    # declared basis_slot is wildcard text sitting between the ruled words, so
    # it neither belongs to the ruled phrase nor stops anything else being
    # found there — another ruled term, or a discretionary marker.
    ruled: list[tuple[int, int]] = []
    accepted: list[tuple[int, int, Term, "re.Match[str]", tuple[int, int]]] = []
    for start, end, _order, term, match in candidates:
        if _overlaps(ruled, start, end):
            continue
        slot = _slot_span(match, start)
        ruled.extend(_ruled_spans(start, end, slot))
        accepted.append((start, end, term, match, slot))
    accepted.sort(key=lambda item: item[0])

    # Pass 2 — fail closed. Any declared discretionary marker that no ruled
    # term consumed is an unresolved item. This is the mechanism that stops an
    # unknown term passing through silently (PID line 39), and it runs before
    # the PARAMETERISE terms are allowed to resolve, because what it finds
    # inside a term's slot is one of the things that stops them.
    unknown_hits: list[tuple[int, int, Marker]] = []
    for marker in lexicon.markers:
        for match in marker.pattern.finditer(norm):
            start, end = match.start(), match.end()
            if _overlaps(ruled, start, end):
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
        if term.disposition != PARAMETERISE:
            # A REFUSE term already refuses; there is no ruled basis for
            # context to displace, so scanning it would only add noise.
            continue

        slot_start, slot_end = slot
        occupants = _slot_occupants(
            norm, text, index_map, starts, slot, lexicon
        )
        if occupants:
            slot_occupants[term.term_id].extend(occupants)
            slot_texts.setdefault(term.term_id, []).append(
                _occurrence(text, index_map, starts, slot_start, slot_end)
            )
            slot_occurrences.setdefault(term.term_id, []).append(occurrence)

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
    # or holds unresolved language in its own slot, the term does not resolve
    # at all: its parameter would be declared once for the whole draft, so
    # there is no coherent way to half-declare it, and the fail-closed
    # direction is the one docs/AMBIGUITY-POLICY.md takes.
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
        if not term_hits[term_id] and not slot_occupants[term_id]
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

    return Analysis(
        text=text,
        lexicon=lexicon,
        term_findings=term_findings,
        unknown_findings=tuple(unknown_findings),
        rebased_findings=tuple(rebased_findings),
        unruled_slot_findings=tuple(unruled_slot_findings),
        normalised=norm,
        ruled_spans=tuple(sorted(ruled)),
    )
