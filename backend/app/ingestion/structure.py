from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from app.ingestion.classifier import LegalDocumentType
from app.ingestion.extract import ExtractedDocument


@dataclass
class StructuralUnit:
    kind: str
    text: str
    page_start: int
    page_end: int
    heading_path: list[str] = field(default_factory=list)
    section: str | None = None
    subsection: str | None = None
    paragraph_number: str | None = None
    # (character offset, page) for each page change within `text`, so a window
    # cut from a long unit can say which pages it really spans.
    page_marks: list[tuple[int, int]] = field(default_factory=list)


def _unit_text(lines: list[str], pages: list[int]) -> tuple[str, list[tuple[int, int]]]:
    joined = "\n".join(lines)
    leading = len(joined) - len(joined.lstrip())
    marks: list[tuple[int, int]] = []
    offset = 0
    for line, page in zip(lines, pages, strict=True):
        if not marks or marks[-1][1] != page:
            marks.append((max(0, offset - leading), page))
        offset += len(line) + 1
    return joined.strip(), marks


# Case-sensitive on purpose. Ignoring case made wrapped prose into headings:
# "section 13 of the Code shall apply" opened section 13, and "Part III of the
# Constitution applies" cleared the current section.
_ACT_HEADING = re.compile(
    r"^\s*(?P<kind>PART|Part|CHAPTER|Chapter|SECTION|Section|SEC\.|Sec\.|SCHEDULE|Schedule|"
    r"APPENDIX|Appendix|ANNEXURE|Annexure)\s+"
    r"(?P<label>[0-9IVXLC]+[A-Z]?)(?:\s*[-—:.]\s*|\s+|$)(?P<title>(?![a-z]).*)$"
)
_SCHEDULE_LINE = re.compile(
    r"^\s*(?:THE\s+)?(?:[A-Z]+\s+)?SCHEDULE(?:\s+[IVXLC\d]+)?\s*[.:—-]?\s*$"
)
# A head may open with a quote or a footnote bracket: `15. "Coercion" defined`,
# `[34. Acts done`, `2[354A. Assault`. Requiring a capital straight after the
# number merged about ten thousand heads into whichever section came before.
_HEAD_TITLE = r"(?P<title>[\"“‘'\[]?\d{0,2}\[?[A-Z][^\n]{2,})"
_NUMBERED_SECTION = re.compile(
    r"^\s*(?:\d{0,2}\[)?(?P<label>\d+[A-Z]{0,2})\.\s*(?:[-—–]\s*)?" + _HEAD_TITLE + r"$"
)
_COLUMN_SECTION = re.compile(
    r"^\s*.{1,70}?\s{2,}(?:\d{0,2}\[)?(?P<label>\d+[A-Z]{0,2})\.\s+" + _HEAD_TITLE + r"$"
)
# Extraction can leave the number alone on a line: "...other than this\n6.\n
# Sanhita, there shall be". Weak evidence, so only accepted as the next section.
_BARE_NUMBER = re.compile(r"^\s*(?P<label>\d+[A-Z]{0,2})\.\s*$")
# "2. Ins. by Act 52 of 1964" is a footnote, and the text of the next page would
# otherwise be cited as section 2.
_FOOTNOTE_TITLE = re.compile(
    r"^[\"“‘'\[]?(?:Subs|Ins|Rep|Omitted|Added|Renumbered|Substituted|Inserted|Amended|"
    r"The\s+words?|Cl\.|Sub-s\.|Sub-section|Section\s+\d|Sec\.|See\b|Vide|Now\b|Came\s+into|"
    r"Ibid|Act\s+\d|Explanation\s+(?:ins|added)|w\.e\.f)\b"
)
# The layout the 2023 Sanhitas are published in, and the reason half of the
# BNSS was invisible to retrieval. Both patterns above require the section
# title to follow the number:
#
#     14. Subordination of Executive Magistrates.
#
# The Sanhitas print the title as a marginal note in a side column, so
# extraction interleaves it and what actually follows the number is the
# sub-section marker:
#
#     Definitions.            2. (1) In this Sanhita, unless the context ...
#                             3. (1) Unless the context otherwise requires, ...
#
# "(" is not "[A-Z]", so neither pattern matched and 271 of 531 BNSS sections
# were never labelled -- present in the text, absent from every query that
# needed them. The IPC, typeset heading-first, kept 93% of its sections, which
# is why the corpus looked systematically richer in repealed law.
_MARGINAL_SECTION = re.compile(
    # The marginal note's trailing period is optional. Requiring it matched
    # "Definitions.   2. (1) ..." and missed "Information    173. (1) ..." --
    # the note is a wrapped phrase in a narrow column and frequently carries no
    # full stop, which cost 134 further sections including s.173, the FIR
    # provision that is the most-asked question in this corpus.
    r"^\s*(?:(?P<margin>[^\W\d_][^\n]{0,70}?)\s{2,})?"
    # Gazette scans commonly extract ``9. (1)`` as ``9, (/)``. Accept those
    # two punctuation/OCR variants only in this strongly anchored heading
    # shape; ordinary prose still cannot open a section.
    # Clause letters too, for "5. (a) Whoever, being a police officer". Sequence
    # decides whether this opens a section or is a list item, so it can be broad.
    r"(?P<label>\d+[A-Z]?)[.,:]\s*\((?:\d+[A-Z]?|[/#Il]|[a-z])\)\s*(?P<body>\S.*)$"
)
_MARGINAL_PLAIN_SECTION = re.compile(
    # A margin plus a large whitespace column is enough structure to identify
    # provisions without a subsection, such as the POSH Act's section 24.
    r"^\s*(?P<margin>[^\W\d_][^\n]{0,70}?)\s{2,}"
    r"(?P<label>\d+[A-Z]?)[.,:]\s+(?P<body>\S.*)$"
)

_SUBSECTION = re.compile(r"^\s*\((?P<label>\d+[A-Z]?)\)\s+")
_LEGAL_SUBUNIT = re.compile(
    r"^\s*(?P<kind>PROVISO|PROVIDED\s+THAT|EXPLANATION|ILLUSTRATION|CLAUSE)\b",
    re.IGNORECASE,
)
_JUDGMENT_PARAGRAPH = re.compile(r"^\s*(?P<number>\d{1,4})[.)]\s+(?P<text>.+)")
_GENERIC_HEADING = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*[.)]?\s+)?[A-Z][A-Z0-9 ,/&()'’:-]{4,120}\s*$"
)

_JUDGMENT_HEADINGS = (
    (
        "facts",
        re.compile(r"^(?:BRIEF\s+)?FACTS(?:\s+OF\s+THE\s+CASE)?$", re.IGNORECASE),
    ),
    (
        "issues",
        re.compile(
            r"^(?:ISSUES?|QUESTIONS?\s+FOR\s+(?:CONSIDERATION|DETERMINATION))$",
            re.IGNORECASE,
        ),
    ),
    (
        "appellant_arguments",
        re.compile(
            r"^(?:ARGUMENTS?|SUBMISSIONS?)\s+(?:OF|ON\s+BEHALF\s+OF)\s+(?:THE\s+)?(?:APPELLANT|PETITIONER)S?$",
            re.IGNORECASE,
        ),
    ),
    (
        "respondent_arguments",
        re.compile(
            r"^(?:ARGUMENTS?|SUBMISSIONS?)\s+(?:OF|ON\s+BEHALF\s+OF)\s+(?:THE\s+)?RESPONDENTS?$",
            re.IGNORECASE,
        ),
    ),
    (
        "court_analysis",
        re.compile(
            r"^(?:ANALYSIS|DISCUSSION|REASONS?|CONSIDERATION\s+BY\s+THE\s+COURT)$",
            re.IGNORECASE,
        ),
    ),
    (
        "authorities_cited",
        re.compile(r"^(?:AUTHORITIES|CASES|PRECEDENTS)\s+CITED$", re.IGNORECASE),
    ),
    (
        "ratio",
        re.compile(r"^(?:RATIO|RATIO\s+DECIDENDI|LEGAL\s+PRINCIPLES?)$", re.IGNORECASE),
    ),
    (
        "final_order",
        re.compile(
            r"^(?:FINAL\s+)?(?:ORDER|DECISION|CONCLUSION|OPERATIVE\s+DIRECTIONS?)$",
            re.IGNORECASE,
        ),
    ),
)


def _lines(document: ExtractedDocument) -> list[tuple[int, str]]:
    return [
        (page.page_number, line.rstrip())
        for page in document.pages
        for line in page.text.splitlines()
        if line.strip()
    ]


@dataclass(frozen=True)
class _SectionOption:
    line_index: int
    number: int
    suffix: str
    label: str
    score: float
    bare: bool


_ACT_BEGINS = re.compile(r"^\s*(?:.{0,70}\s{2,})?1\.\s*(?:\(1\)\s*)?(?:Short\s+title|This\s+Act)", re.I)
# Sections of a statute never reach a year, so "1993." is a line ending in a date.
_YEAR_LABEL = re.compile(r"^(?:18|19|20)\d\d$")
_SCHEDULES_START_AFTER = 0.2
_MAX_SECTION_GAP = 60  # Contract Act ss.76-123 were repealed; 48 is a real jump.
_RESTART_COST = 8.0
_SKIPPED_NUMBER_COST = 0.05
_TEXT_UNDER_HEAD_BONUS = 0.5
_WORDS_FOR_FULL_BONUS = 30
_GLUED_DIGIT_COST = 0.5
_DP_WINDOW = 300


def _section_head(line: str) -> tuple[re.Match[str] | None, re.Match[str] | None, bool]:
    """Numbered match, marginal match, and whether this is a bare number."""
    numbered = _NUMBERED_SECTION.match(line) or _COLUMN_SECTION.match(line)
    if numbered and _FOOTNOTE_TITLE.match(numbered.group("title")):
        numbered = None
    if numbered:
        return numbered, None, False
    marginal = _MARGINAL_SECTION.match(line) or _MARGINAL_PLAIN_SECTION.match(line)
    if marginal:
        return None, marginal, False
    bare = _BARE_NUMBER.match(line)
    return bare, None, bool(bare)


def _options_for(line_index: int, label: str, *, bare: bool) -> list[_SectionOption]:
    if _YEAR_LABEL.match(label):
        return []
    match = re.match(r"(\d+)([A-Z]*)$", label)
    if not match:
        return []
    digits, suffix = match.groups()
    options = [_SectionOption(line_index, int(digits), suffix, label, 1.0, bare)]
    # A superscript footnote digit glues onto the number: Contract Act s.151 is
    # extracted as "1151". The sequence decides which reading is right.
    remainder = digits[1:]
    if not bare and len(digits) >= 2 and remainder and not remainder.startswith("0"):
        options.append(
            _SectionOption(
                line_index, int(remainder), suffix, remainder + suffix, 1.0 - _GLUED_DIGIT_COST, bare
            )
        )
    return options


def _follows(previous: _SectionOption, current: _SectionOption) -> float | None:
    """The score change for this step, or None when it cannot follow."""
    if (current.number, current.suffix) > (previous.number, previous.suffix):
        limit = 2 if current.bare else _MAX_SECTION_GAP
        gap = current.number - previous.number
        if gap <= limit:
            # Skipping numbers needs explaining. Without a cost, a list inside s.45
            # makes 1, 2, 3, 46 beat 45, 46 simply by being longer.
            return -_SKIPPED_NUMBER_COST * max(0, gap - 1)
    if current.number == 1 and not current.suffix and not current.bare:
        return -_RESTART_COST
    return None


def _accepted_sections(lines: list[tuple[int, str]]) -> dict[int, str]:
    """Which lines really open a section, and with what number.

    A number followed by a capital also describes list items, footnotes and
    contents pages, and no pattern can tell them apart line by line. What they
    lack is sequence: real sections ascend. So every possible head is collected
    and the best ascending path through the whole document is kept. A restart at
    1 is allowed at a cost, which a contents page or a second instrument in the
    same file can pay and a short numbered list inside a section cannot.
    """
    options: list[_SectionOption] = []
    in_schedule = False
    # Contents pages name the schedules too, long before the Act's text begins.
    # The Constitution has no "Short title" to end that, and lost 209 articles.
    earliest_schedule = int(len(lines) * _SCHEDULES_START_AFTER)
    for index, (_, line) in enumerate(lines):
        heading = _ACT_HEADING.match(line)
        if heading:
            kind = heading.group("kind").upper().rstrip(".")
            if kind in {"SCHEDULE", "APPENDIX", "ANNEXURE"}:
                in_schedule = index >= earliest_schedule
            elif kind == "CHAPTER":
                in_schedule = False
            continue
        if _SCHEDULE_LINE.match(line):
            in_schedule = index >= earliest_schedule
            continue
        # An arrangement of sections names the schedule before the Act begins, so
        # the first section of the body ends schedule mode.
        if in_schedule and _ACT_BEGINS.match(line):
            in_schedule = False
        # Schedule entries are numbered, and are not sections of the Act.
        if in_schedule:
            continue
        numbered, marginal, bare = _section_head(line)
        match = numbered or marginal
        if match:
            options.extend(_options_for(index, match.group("label"), bare=bare))
    if not options:
        return {}

    # A head with text under it is better evidence than one without, which is what
    # separates an Act's body from its contents page when numbering ties.
    head_lines = sorted({option.line_index for option in options})
    next_head = dict(zip(head_lines, [*head_lines[1:], len(lines)], strict=True))
    options = [
        replace(
            option,
            score=option.score
            + _TEXT_UNDER_HEAD_BONUS
            * min(
                sum(len(lines[i][1].split()) for i in range(option.line_index + 1, next_head[option.line_index])),
                _WORDS_FOR_FULL_BONUS,
            )
            / _WORDS_FOR_FULL_BONUS,
        )
        for option in options
    ]
    best = [0.0] * len(options)
    previous_at: list[int | None] = [None] * len(options)
    for position, option in enumerate(options):
        # A chain may start anywhere, except on the weakest kind of evidence.
        best[position] = option.score if not option.bare or option.number <= 2 else float("-inf")
        for earlier in range(max(0, position - _DP_WINDOW), position):
            candidate = options[earlier]
            if candidate.line_index == option.line_index or best[earlier] == float("-inf"):
                continue
            step = _follows(candidate, option)
            if step is not None and best[earlier] + option.score + step > best[position]:
                best[position] = best[earlier] + option.score + step
                previous_at[position] = earlier

    position: int | None = max(range(len(options)), key=best.__getitem__)
    chain: list[_SectionOption] = []
    while position is not None:
        chain.append(options[position])
        position = previous_at[position]
    chain.reverse()
    return _without_contents_pages(chain, lines)


def _without_contents_pages(
    chain: list[_SectionOption], lines: list[tuple[int, str]]
) -> dict[int, str]:
    """Drop a run of heads with almost no text under them, if the numbering restarts.

    That is an arrangement of sections. Left labelled, every contents entry is a
    "section" that passes the short-chunk filter, which is how the corpus came to
    hold 20,437 of them and 41 documents with a "section 173".
    """
    segments: list[list[_SectionOption]] = []
    for option in chain:
        if segments and (option.number, option.suffix) > (segments[-1][-1].number, segments[-1][-1].suffix):
            segments[-1].append(option)
        else:
            segments.append([option])

    def median_words(segment: list[_SectionOption]) -> int:
        counts = sorted(
            sum(len(lines[i][1].split()) for i in range(left.line_index, right.line_index))
            for left, right in zip(segment, segment[1:], strict=False)
        )
        return counts[len(counts) // 2] if counts else 0

    accepted: dict[int, str] = {}
    for position, segment in enumerate(segments):
        is_contents = (
            position < len(segments) - 1 and len(segment) >= 5 and median_words(segment) <= 14
        )
        if not is_contents:
            accepted.update((option.line_index, option.label) for option in segment)
    return accepted


def _parse_acts(document: ExtractedDocument) -> list[StructuralUnit]:
    units: list[StructuralUnit] = []
    path: list[str] = []
    current_lines: list[str] = []
    current_pages: list[int] = []
    start_page = 1
    end_page = 1
    section: str | None = None

    def flush() -> None:
        nonlocal current_lines, current_pages
        if current_lines:
            text, marks = _unit_text(current_lines, current_pages)
            subsection_match = _SUBSECTION.match(text)
            units.append(
                StructuralUnit(
                    kind="section" if section else "preamble",
                    text=text,
                    page_start=start_page,
                    page_end=end_page,
                    heading_path=list(path),
                    section=section,
                    subsection=subsection_match.group("label")
                    if subsection_match
                    else None,
                    page_marks=marks,
                )
            )
            current_lines = []
            current_pages = []

    lines = _lines(document)
    accepted = _accepted_sections(lines)
    for line_index, (page_number, line) in enumerate(lines):
        heading = _ACT_HEADING.match(line)
        schedule_line = None if heading else _SCHEDULE_LINE.match(line)
        numbered = marginal = None
        if line_index in accepted and not heading:
            numbered, marginal, _ = _section_head(line)
        if heading or schedule_line or numbered or marginal:
            flush()
            start_page = page_number
            end_page = page_number
            if schedule_line:
                path = [line.strip()]
                section = None
            elif heading:
                kind = heading.group("kind").upper().rstrip(".")
                label = heading.group("label")
                title = heading.group("title").strip()
                display = " ".join(part for part in (kind, label, title) if part)
                if kind in {"PART", "CHAPTER"}:
                    path = [
                        entry
                        for entry in path
                        if not entry.upper().startswith(
                            ("PART", "CHAPTER", "SECTION", "SEC.")
                        )
                    ]
                    path.append(display)
                    section = None
                elif kind in {"SECTION", "SEC"}:
                    path = [
                        entry
                        for entry in path
                        if not entry.upper().startswith(("SECTION", "SEC."))
                    ]
                    path.append(display)
                    section = label
                else:
                    path = [display]
                    section = None
            elif numbered:
                section = accepted[line_index]
                title = numbered.groupdict().get("title") or ""
                display = f"Section {section} {title.strip()}".strip()
                path = [
                    entry
                    for entry in path
                    if not entry.upper().startswith(("SECTION", "SEC."))
                ]
                path.append(display)
            else:
                # Marginal-note layout. The title is the margin text when
                # extraction placed it on this line; otherwise the section is
                # still captured, because a section labelled without its title
                # is retrievable and an unlabelled one is not.
                section = accepted[line_index]
                margin = (marginal.group("margin") or "").strip().rstrip(".")
                display = f"Section {section} {margin}".strip()
                path = [
                    entry
                    for entry in path
                    if not entry.upper().startswith(("SECTION", "SEC."))
                ]
                path.append(display)
            current_lines.append(line)
            current_pages.append(page_number)
            continue
        current_lines.append(line)
        current_pages.append(page_number)
        end_page = page_number
    flush()
    return units


def _judgment_heading(line: str) -> str | None:
    compact = re.sub(r"\s+", " ", line).strip(" :-")
    for kind, pattern in _JUDGMENT_HEADINGS:
        if pattern.fullmatch(compact):
            return kind
    return None


def _parse_judgment(document: ExtractedDocument) -> list[StructuralUnit]:
    units: list[StructuralUnit] = []
    current_lines: list[str] = []
    current_pages: list[int] = []
    start_page = 1
    end_page = 1
    explicit_section = "metadata"
    paragraph_number: str | None = None

    def flush() -> None:
        nonlocal current_lines, current_pages
        if current_lines:
            text, marks = _unit_text(current_lines, current_pages)
            units.append(
                StructuralUnit(
                    kind=explicit_section,
                    text=text,
                    page_marks=marks,
                    page_start=start_page,
                    page_end=end_page,
                    heading_path=[explicit_section.replace("_", " ").title()],
                    paragraph_number=paragraph_number,
                )
            )
            current_lines = []
            current_pages = []

    for page_number, line in _lines(document):
        detected_heading = _judgment_heading(line)
        paragraph = _JUDGMENT_PARAGRAPH.match(line)
        if detected_heading:
            flush()
            explicit_section = detected_heading
            paragraph_number = None
            start_page = end_page = page_number
        elif paragraph:
            flush()
            paragraph_number = paragraph.group("number")
            start_page = end_page = page_number
        else:
            end_page = page_number
        current_lines.append(line)
        current_pages.append(page_number)
    flush()
    return units


def _parse_generic(
    document: ExtractedDocument, *, forms: bool = False
) -> list[StructuralUnit]:
    units: list[StructuralUnit] = []
    heading = "Form" if forms else "Document"
    current_lines: list[str] = []
    current_pages: list[int] = []
    start_page = 1
    end_page = 1

    def flush() -> None:
        nonlocal current_lines, current_pages
        if current_lines:
            text, marks = _unit_text(current_lines, current_pages)
            units.append(
                StructuralUnit(
                    kind="form_section" if forms else "paragraph",
                    text=text,
                    page_marks=marks,
                    page_start=start_page,
                    page_end=end_page,
                    heading_path=[heading],
                )
            )
            current_lines = []
            current_pages = []

    for page_number, line in _lines(document):
        is_label = forms and bool(
            re.match(r"^\s*[A-Za-z][A-Za-z /()_-]{2,50}:\s*", line)
        )
        if _GENERIC_HEADING.fullmatch(line) or is_label:
            flush()
            heading = line.strip()
            start_page = end_page = page_number
        current_lines.append(line)
        current_pages.append(page_number)
        end_page = page_number
    flush()
    return units


def parse_legal_structure(
    document: ExtractedDocument,
    document_type: LegalDocumentType,
) -> list[StructuralUnit]:
    if document_type in {
        LegalDocumentType.CONSTITUTION,
        LegalDocumentType.ACT,
        LegalDocumentType.RULE,
        LegalDocumentType.REGULATION,
        LegalDocumentType.AMENDMENT,
        LegalDocumentType.NOTIFICATION,
        LegalDocumentType.ORDER,
        LegalDocumentType.CIRCULAR,
    }:
        return _parse_acts(document)
    if document_type in {
        LegalDocumentType.SUPREME_COURT_JUDGMENT,
        LegalDocumentType.HIGH_COURT_JUDGMENT,
    }:
        return _parse_judgment(document)
    return _parse_generic(
        document, forms=document_type == LegalDocumentType.FORM_TEMPLATE
    )
