"""The deterministic scan over a raw strategy description.

WHAT THIS IS: a rules-based analyser over the declared lexicon. It matches
declared surface patterns, first the ruled terms and then the discretionary
markers, and reports every marker occurrence that no ruled term consumed.

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

from hsa.intake.lexicon import PARAMETERISE, Lexicon, Marker, Term

__all__ = [
    "Occurrence",
    "TermFinding",
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

    @property
    def location(self) -> str:
        return "; ".join(occurrence.describe() for occurrence in self.occurrences)


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

    term_occurrences: dict[str, list[Occurrence]] = {}
    term_by_id: dict[str, Term] = {}
    for start, end, term in sorted(accepted, key=lambda item: item[0]):
        term_occurrences.setdefault(term.term_id, []).append(
            _occurrence(text, index_map, starts, start, end)
        )
        term_by_id[term.term_id] = term

    term_findings = tuple(
        TermFinding(term=term_by_id[term_id], occurrences=tuple(occurrences))
        for term_id, occurrences in term_occurrences.items()
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
    used_ids: set[str] = {finding.term.term_id for finding in term_findings}
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
    )
