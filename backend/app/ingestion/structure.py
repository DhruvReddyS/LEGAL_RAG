from __future__ import annotations

import re
from dataclasses import dataclass, field

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


_ACT_HEADING = re.compile(
    r"^\s*(?P<kind>PART|CHAPTER|SECTION|SEC\.|SCHEDULE|APPENDIX|ANNEXURE)\s+"
    r"(?P<label>[0-9IVXLC]+[A-Z]?)(?:\s*[-—:.]\s*|\s+)(?P<title>.*)$",
    re.IGNORECASE,
)
_NUMBERED_SECTION = re.compile(
    r"^\s*(?P<label>\d+[A-Z]?)\.\s+(?P<title>[A-Z][^\n]{2,})$"
)
_COLUMN_SECTION = re.compile(
    r"^\s*.{1,70}?\s{2,}(?P<label>\d+[A-Z]?)\.\s+(?P<title>[A-Z][^\n]{2,})$"
)
_SUBSECTION = re.compile(r"^\s*\((?P<label>\d+[A-Z]?)\)\s+")
_LEGAL_SUBUNIT = re.compile(
    r"^\s*(?P<kind>PROVISO|PROVIDED\s+THAT|EXPLANATION|ILLUSTRATION|CLAUSE)\b",
    re.IGNORECASE,
)
_JUDGMENT_PARAGRAPH = re.compile(r"^\s*(?P<number>\d{1,4})[.)]\s+(?P<text>.+)")
_GENERIC_HEADING = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]?\s+)?[A-Z][A-Z0-9 ,/&()'’:-]{4,120}\s*$")

_JUDGMENT_HEADINGS = (
    ("facts", re.compile(r"^(?:BRIEF\s+)?FACTS(?:\s+OF\s+THE\s+CASE)?$", re.IGNORECASE)),
    ("issues", re.compile(r"^(?:ISSUES?|QUESTIONS?\s+FOR\s+(?:CONSIDERATION|DETERMINATION))$", re.IGNORECASE)),
    ("appellant_arguments", re.compile(r"^(?:ARGUMENTS?|SUBMISSIONS?)\s+(?:OF|ON\s+BEHALF\s+OF)\s+(?:THE\s+)?(?:APPELLANT|PETITIONER)S?$", re.IGNORECASE)),
    ("respondent_arguments", re.compile(r"^(?:ARGUMENTS?|SUBMISSIONS?)\s+(?:OF|ON\s+BEHALF\s+OF)\s+(?:THE\s+)?RESPONDENTS?$", re.IGNORECASE)),
    ("court_analysis", re.compile(r"^(?:ANALYSIS|DISCUSSION|REASONS?|CONSIDERATION\s+BY\s+THE\s+COURT)$", re.IGNORECASE)),
    ("authorities_cited", re.compile(r"^(?:AUTHORITIES|CASES|PRECEDENTS)\s+CITED$", re.IGNORECASE)),
    ("ratio", re.compile(r"^(?:RATIO|RATIO\s+DECIDENDI|LEGAL\s+PRINCIPLES?)$", re.IGNORECASE)),
    ("final_order", re.compile(r"^(?:FINAL\s+)?(?:ORDER|DECISION|CONCLUSION|OPERATIVE\s+DIRECTIONS?)$", re.IGNORECASE)),
)


def _lines(document: ExtractedDocument) -> list[tuple[int, str]]:
    return [
        (page.page_number, line.rstrip())
        for page in document.pages
        for line in page.text.splitlines()
        if line.strip()
    ]


def _parse_acts(document: ExtractedDocument) -> list[StructuralUnit]:
    units: list[StructuralUnit] = []
    path: list[str] = []
    current_lines: list[str] = []
    start_page = 1
    end_page = 1
    section: str | None = None

    def flush() -> None:
        nonlocal current_lines
        if current_lines:
            text = "\n".join(current_lines).strip()
            subsection_match = _SUBSECTION.match(text)
            units.append(
                StructuralUnit(
                    kind="section" if section else "preamble",
                    text=text,
                    page_start=start_page,
                    page_end=end_page,
                    heading_path=list(path),
                    section=section,
                    subsection=subsection_match.group("label") if subsection_match else None,
                )
            )
            current_lines = []

    for page_number, line in _lines(document):
        heading = _ACT_HEADING.match(line)
        numbered = _NUMBERED_SECTION.match(line) or _COLUMN_SECTION.match(line)
        legal_subunit = _LEGAL_SUBUNIT.match(line)
        if heading or numbered:
            flush()
            start_page = page_number
            end_page = page_number
            if heading:
                kind = heading.group("kind").upper().rstrip(".")
                label = heading.group("label")
                title = heading.group("title").strip()
                display = " ".join(part for part in (kind, label, title) if part)
                if kind in {"PART", "CHAPTER"}:
                    path = [entry for entry in path if not entry.upper().startswith(("PART", "CHAPTER", "SECTION", "SEC."))]
                    path.append(display)
                    section = None
                elif kind in {"SECTION", "SEC"}:
                    path = [entry for entry in path if not entry.upper().startswith(("SECTION", "SEC."))]
                    path.append(display)
                    section = label
                else:
                    path = [display]
                    section = None
            else:
                section = numbered.group("label")
                display = f"Section {section} {numbered.group('title').strip()}"
                path = [entry for entry in path if not entry.upper().startswith(("SECTION", "SEC."))]
                path.append(display)
            current_lines.append(line)
            continue
        if legal_subunit and current_lines:
            current_lines.append(line)
        else:
            current_lines.append(line)
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
    start_page = 1
    end_page = 1
    explicit_section = "metadata"
    paragraph_number: str | None = None

    def flush() -> None:
        nonlocal current_lines
        if current_lines:
            units.append(
                StructuralUnit(
                    kind=explicit_section,
                    text="\n".join(current_lines).strip(),
                    page_start=start_page,
                    page_end=end_page,
                    heading_path=[explicit_section.replace("_", " ").title()],
                    paragraph_number=paragraph_number,
                )
            )
            current_lines = []

    for page_number, line in _lines(document):
        detected_heading = _judgment_heading(line)
        paragraph = _JUDGMENT_PARAGRAPH.match(line)
        if detected_heading:
            flush()
            explicit_section = detected_heading
            paragraph_number = None
            start_page = end_page = page_number
            current_lines.append(line)
        elif paragraph:
            flush()
            paragraph_number = paragraph.group("number")
            start_page = end_page = page_number
            current_lines.append(line)
        else:
            current_lines.append(line)
            end_page = page_number
    flush()
    return units


def _parse_generic(document: ExtractedDocument, *, forms: bool = False) -> list[StructuralUnit]:
    units: list[StructuralUnit] = []
    heading = "Form" if forms else "Document"
    current_lines: list[str] = []
    start_page = 1
    end_page = 1

    def flush() -> None:
        nonlocal current_lines
        if current_lines:
            units.append(
                StructuralUnit(
                    kind="form_section" if forms else "paragraph",
                    text="\n".join(current_lines).strip(),
                    page_start=start_page,
                    page_end=end_page,
                    heading_path=[heading],
                )
            )
            current_lines = []

    for page_number, line in _lines(document):
        is_label = forms and bool(re.match(r"^\s*[A-Za-z][A-Za-z /()_-]{2,50}:\s*", line))
        if _GENERIC_HEADING.fullmatch(line) or is_label:
            flush()
            heading = line.strip()
            start_page = end_page = page_number
        current_lines.append(line)
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
    return _parse_generic(document, forms=document_type == LegalDocumentType.FORM_TEMPLATE)
