"""The deterministic scan over a raw strategy description.

WHAT THIS IS: a rules-based analyser over the declared lexicon. It matches
declared surface patterns, first the ruled terms and then the discretionary
markers, and reports every marker occurrence that no ruled term consumed.

Between those two passes sits the basis-qualifier check. A ruled
PARAMETERISE term is only ruled for the claim the lexicon declares: "large
wick" is ratified onto a single-bar wick-over-range basis, and "large wick
relative to the recent average" is a different claim that ruling does not
cover. So before a PARAMETERISE term is allowed to resolve, the declared
window around it is scanned against the declared basis-qualifier vocabulary,
and a term whose context re-bases it becomes an unresolved item instead of a
resolution. Its limits are declared alongside it in the lexicon and are real:
it recognises listed constructions inside a declared window, nothing more.

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

from hsa.intake.lexicon import PARAMETERISE, BasisQualifier, Lexicon, Marker, Term

__all__ = [
    "Occurrence",
    "TermFinding",
    "QualifierHit",
    "RebasedFinding",
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


@dataclass(frozen=True)
class QualifierHit:
    """One declared re-basing construction, found in a term's window."""

    qualifier: BasisQualifier
    occurrence: Occurrence

    def describe(self) -> str:
        return "%s (%s) at %s: %r" % (
            self.qualifier.qualifier_id,
            self.qualifier.reason,
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
class Analysis:
    text: str
    lexicon: Lexicon
    term_findings: tuple[TermFinding, ...]
    unknown_findings: tuple[UnknownFinding, ...]
    rebased_findings: tuple[RebasedFinding, ...] = ()

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


def _sentence_bounds(norm: str, terminators: str) -> list[tuple[int, int]]:
    """Cut ``norm`` into sentence spans on the declared terminator set.

    The terminators come from the lexicon, not from here, because the size of
    the inspected window is the reviewable half of the basis-qualifier guard.
    Runs of terminators and the space after them belong to the sentence they
    close, so every offset in ``norm`` falls inside exactly one span.
    """
    stops = set(terminators)
    bounds: list[tuple[int, int]] = []
    start = 0
    index = 0
    length = len(norm)
    while index < length:
        if norm[index] in stops:
            while index < length and norm[index] in stops:
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


def _qualifier_hits(
    norm: str,
    qualifiers: Sequence[BasisQualifier],
    window: tuple[int, int],
    term_span: tuple[int, int],
) -> list[tuple[int, int, BasisQualifier]]:
    """Declared re-basing constructions inside ``window``, excluding the term.

    A hit wholly inside the term's own matched span is part of the ruled
    phrase the lexicon already declares, not context that re-bases it, so it
    is dropped. Order is fixed: leftmost, then longest, then the order the
    lexicon declares them in.
    """
    found: list[tuple[int, int, BasisQualifier]] = []
    seen: set[tuple[int, int, str]] = set()
    window_start, window_end = window
    for order, qualifier in enumerate(qualifiers):
        for match in qualifier.pattern.finditer(norm, window_start, window_end):
            start, end = match.start(), match.end()
            if end <= start:
                continue
            if term_span[0] <= start and end <= term_span[1]:
                continue
            key = (start, end, qualifier.qualifier_id)
            if key in seen:
                continue
            seen.add(key)
            found.append((start, end, qualifier))
    found.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2].qualifier_id))
    return found


def analyse(text: str, lexicon: Lexicon) -> Analysis:
    """Scan ``text`` against ``lexicon`` and return every finding."""
    norm, index_map = normalise(text)
    starts = _line_starts(text)

    # Pass 1 — ruled lexicon terms. Every match is collected first, then
    # overlaps are resolved by a fixed rule, so a longer ruled phrase always
    # beats a shorter one that starts in the same place.
    candidates: list[tuple[int, int, int, Term]] = []
    for order, term in enumerate(lexicon.terms):
        for match in term.pattern.finditer(norm):
            if match.end() > match.start():
                candidates.append((match.start(), match.end(), order, term))
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))

    consumed: list[tuple[int, int]] = []
    accepted: list[tuple[int, int, Term]] = []
    for start, end, _order, term in candidates:
        if any(start < taken_end and taken_start < end for taken_start, taken_end in consumed):
            continue
        consumed.append((start, end))
        accepted.append((start, end, term))

    # Pass 1b — the basis-qualifier check. A PARAMETERISE ruling covers the
    # phrase the lexicon declares and nothing else, so before a ruled term is
    # allowed to resolve, the declared window around it is scanned for
    # declared constructions that name a different measurement basis. This is
    # surface matching over a declared vocabulary inside a declared window;
    # what it does not cover is stated in the lexicon's own
    # basis_qualifier_policy['limits'] and repeated in every emitted
    # resolution, because a guard that overstates itself is worse than none.
    window_policy = lexicon.basis_qualifier_policy["window"]
    bounds = _sentence_bounds(norm, str(window_policy["sentence_terminators"]))
    sentences_after = int(window_policy["sentences_after"])

    term_occurrences: dict[str, list[Occurrence]] = {}
    term_windows: dict[str, list[Occurrence]] = {}
    term_by_id: dict[str, Term] = {}
    term_hits: dict[str, list[tuple[int, int, BasisQualifier]]] = {}
    term_context: dict[str, tuple[int, int]] = {}
    term_window_span: dict[str, tuple[int, int]] = {}
    for start, end, term in sorted(accepted, key=lambda item: item[0]):
        window = _window_span(bounds, start, end, sentences_after)
        term_occurrences.setdefault(term.term_id, []).append(
            _occurrence(text, index_map, starts, start, end)
        )
        term_windows.setdefault(term.term_id, []).append(
            _occurrence(text, index_map, starts, window[0], window[1])
        )
        term_by_id[term.term_id] = term
        term_hits.setdefault(term.term_id, [])
        if term.disposition != PARAMETERISE:
            # A REFUSE term already refuses; there is no ruled basis for
            # context to displace, so scanning it would only add noise.
            continue
        hits = _qualifier_hits(norm, lexicon.basis_qualifiers, window, (start, end))
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
    # the term does not resolve at all: its parameter would be declared once
    # for the whole draft, so there is no coherent way to half-declare it, and
    # the fail-closed direction is the one docs/AMBIGUITY-POLICY.md takes.
    term_findings = tuple(
        TermFinding(
            term=term_by_id[term_id],
            occurrences=tuple(occurrences),
            scanned_windows=tuple(term_windows[term_id]),
        )
        for term_id, occurrences in term_occurrences.items()
        if not term_hits[term_id]
    )

    rebased_findings: list[RebasedFinding] = []
    used_item_ids: set[str] = {finding.term.term_id for finding in term_findings}
    for term_id, occurrences in term_occurrences.items():
        # A term matching twice inside one window finds the same
        # constructions twice. Report each construction once.
        hits = []
        seen_hits: set[tuple[int, int, str]] = set()
        for hit in term_hits[term_id]:
            key = (hit[0], hit[1], hit[2].qualifier_id)
            if key in seen_hits:
                continue
            seen_hits.add(key)
            hits.append(hit)
        # Two occurrences of one term can contribute hits out of document
        # order; sort so the emitted item is byte-identical run to run.
        hits.sort(key=lambda hit: (hit[0], -(hit[1] - hit[0]), hit[2].qualifier_id))
        if not hits:
            continue
        context_start, context_end = term_context[term_id]
        window = term_window_span[term_id]
        item_id = ("rebased_" + term_id)[:64]
        if not re.match(r"^[a-z][a-z0-9_]{2,63}$", item_id):
            item_id = "rebased_term"
        suffix = 2
        unique = item_id
        while unique in used_item_ids:
            unique = "%s_%d" % (item_id[:60], suffix)
            suffix += 1
        used_item_ids.add(unique)
        rebased_findings.append(
            RebasedFinding(
                item_id=unique,
                term=term_by_id[term_id],
                occurrences=tuple(occurrences),
                hits=tuple(
                    QualifierHit(
                        qualifier=qualifier,
                        occurrence=_occurrence(
                            text, index_map, starts, hit_start, hit_end
                        ),
                    )
                    for hit_start, hit_end, qualifier in hits
                ),
                context=_occurrence(
                    text, index_map, starts, context_start, context_end
                ),
                window=_occurrence(text, index_map, starts, window[0], window[1]),
            )
        )

    # Pass 2 — fail closed. Any declared discretionary marker that no ruled
    # term consumed is an unresolved item. This is the mechanism that stops
    # an unknown term passing through silently (PID line 39).
    unknown_hits: list[tuple[int, int, Marker]] = []
    for marker in lexicon.markers:
        for match in marker.pattern.finditer(norm):
            start, end = match.start(), match.end()
            if any(
                start < taken_end and taken_start < end
                for taken_start, taken_end in consumed
            ):
                continue
            unknown_hits.append((start, end, marker))
    unknown_hits.sort(key=lambda item: (item[0], -(item[1] - item[0])))

    claimed: list[tuple[int, int]] = []
    grouped: dict[tuple[str, str], list[Occurrence]] = {}
    markers_by_key: dict[tuple[str, str], Marker] = {}
    for start, end, marker in unknown_hits:
        if any(start < taken_end and taken_start < end for taken_start, taken_end in claimed):
            continue
        widened_end = _widen(norm, end)
        claimed.append((start, widened_end))
        occurrence = _occurrence(text, index_map, starts, start, widened_end)
        key = (marker.marker_id, norm[start:widened_end])
        grouped.setdefault(key, []).append(occurrence)
        markers_by_key[key] = marker

    unknown_findings: list[UnknownFinding] = []
    used_ids: set[str] = set(used_item_ids)
    for key, occurrences in grouped.items():
        _marker_id, phrase = key
        item_id = "unknown_" + (_slug(phrase, 55) or _slug(_marker_id, 55) or "term")
        if not re.match(r"^[a-z][a-z0-9_]{2,63}$", item_id):
            item_id = "unknown_term"
        suffix = 2
        unique = item_id
        while unique in used_ids:
            unique = "%s_%d" % (item_id[:60], suffix)
            suffix += 1
        used_ids.add(unique)
        unknown_findings.append(
            UnknownFinding(
                item_id=unique,
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
    )
