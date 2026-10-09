"""Chunk enrichment: quality, structural role, and the embedded form.

Three pure functions that decide what a chunk *is* before it reaches the index.
All of them run at ingestion, and each exists because its absence would
otherwise force another full re-embed later.

`classify_quality` is the highest-risk piece here. A fifth of the current index
is furniture — contents lines, amendment footnotes, bare headings — but a
genuine definition clause can also be one line long. Every rule below is
written to fire only on a positive signal of furniture, never on shortness
alone, and every rejection carries a reason so the ingestion report can be
reviewed rather than trusted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Quality = Literal["indexed", "noise"]

# Roles that describe a whole chunk. Proviso, explanation and illustration are
# spans within a provision and live in `sub_units` instead; keeping them here
# implied the corpus had been checked for something it never could be.
StructuralRole = Literal[
    "provision", "definition", "schedule", "prose",
    "facts", "issues", "arguments", "reasoning", "ratio", "order",
    "heading", "footnote", "toc",
]


@dataclass(frozen=True)
class ChunkQuality:
    quality: Quality
    reason: str | None = None

    @property
    def indexed(self) -> bool:
        return self.quality == "indexed"


# --- furniture signals -------------------------------------------------------

# "1. Short title ......................... 7" or "... 14 - 15" at the end.
_TOC_LEADERS = re.compile(r"\.{4,}\s*\d+\s*$|\s\d{1,4}\s*[-–]\s*\d{1,4}\s*$")

# "Subs. by s. 2 and Sch. I, ibid., for "or Naval"." — an editorial note
# recording an amendment, not the amended text.
_AMENDMENT_NOTE = re.compile(
    r"^\s*\d*\.?\s*(?:subs\.|ins\.|omitted|rep\.|added|renumbered|cl\.)\s",
    re.IGNORECASE,
)
_AMENDMENT_MARKERS = re.compile(r"\bibid\b|\bw\.e\.f\.|\bsupra\b", re.IGNORECASE)

# An editorial note that names the instrument it was made by. This is the
# second signal the rule above wants, for the notes that carry neither "ibid"
# nor "w.e.f." -- which is most of them.
#
# Measured against 8,000 indexed chunks of global_legal_corpus_v5: 44 chunks
# are an amendment footnote and nothing else, every one indexed and every one
# carrying a section number taken from its own leading digit. "4. Subs. by Act
# 24 of 1995, s. 2." is indexed as section 4 of the Act it annotates, so a
# section-filtered query for s.4 can return it and a citation can say
# "section 4" while showing an editorial note.
#
# "by Act 24 of 1995", "by G.S.R. 1567, dated...", "by the A.O. 1950" -- no
# provision opens this way. Paired with the anchored marker above and the
# absence of operative language, that is three signals, which is the standard
# the rule already sets for itself.
_AMENDMENT_INSTRUMENT = re.compile(
    r"\bby\s+(?:the\s+)?(?:act\b|acts\b|a\.\s*o\.|g\.?\s*s\.?\s*r\.?|"
    r"s\.?\s*o\.?\b|ordinance\b|regulation\b|notification\b)",
    re.IGNORECASE,
)

# Furniture that is the whole chunk, each anchored on the chunk's own leading
# number so a provision that merely mentions one of these words is untouched.
# An earlier unanchored version of this measurement counted 779 "furniture"
# chunks, almost all of them 700-word provisions containing the word
# "Address" or "Shri" somewhere; anchored, the real count is 87 in 8,000.
#
# Every one of the classes below was read out of the live index, not imagined:
#
#   32  "35. Mr, V.N. Rai, (1.P.S.), DIG Rules, Panchkula."   a distribution
#       or committee list, indexed as section 35
#    7  "4. Address Telephone Mobile No. E-mail"              a form field,
#       indexed as section 4
#    3  "2. (1980) 1 SCC 81."                                 a footnote
#       citation, indexed as section 2
#    1  "7. Ibid."
_NUMBERED_PERSON = re.compile(
    r"^\s*\d+\.\s*(?:mr|mrs|ms|shri|smt|dr|justice|hon)\b[.,]?\s",
    re.IGNORECASE,
)
_NUMBERED_FORM_FIELD = re.compile(
    r"^\s*\d+\.\s*(?:address|telephone|mobile\s*no|e-?mail|fax|"
    r"place\s+of\s+birth|date\s+of\s+birth|signature|nativity)\b",
    re.IGNORECASE,
)
_NUMBERED_CASE_CITATION = re.compile(
    r"^\s*\d+\.\s*\(?(?:19|20)\d{2}\)?\s*\d*\s*"
    r"(?:scc|air|scr|cri\.?\s*l\.?\s*j|crlj)\b",
    re.IGNORECASE,
)
_NUMBERED_FOOTNOTE_REF = re.compile(
    r"^\s*\d+\.\s*(?:ibid|supra|id)\.?\s*$", re.IGNORECASE
)

# Above this, a chunk is long enough that it probably runs on from the
# furniture into the provision it sits beside, and the project's standing
# trade applies: keeping a footnote costs a little precision, deleting a
# provision costs a citizen their answer. Every one of the 87 measured chunks
# is 11 words or fewer.
_MAXIMUM_FURNITURE_WORDS = 12

# "No.V-17013/9/2006-PR", "F.No. 11012/1/2019", "S.O. 3097(E)"
_REFERENCE_NUMBER = re.compile(
    r"^\s*(?:no\.?|f\.\s*no\.?|s\.\s*o\.?|g\.\s*s\.\s*r\.?)\s*[\w()./-]+\s*$",
    re.IGNORECASE,
)

# "CHAPTER II", "PART III", "THE FIRST SCHEDULE" standing alone.
_BARE_HEADING = re.compile(
    r"^\s*(?:part|chapter|schedule|appendix|annexure|the\s+\w+\s+schedule)\b"
    r"[\sIVXLCDM0-9.—–-]*$",
    re.IGNORECASE,
)

# A page artefact: a bare number, or a running header of digits and dashes.
_PAGE_ARTEFACT = re.compile(r"^\s*[\d\s.,\[\]()/-]{1,40}\s*$")

# A legal sentence states something. These are the shapes a provision takes.
_OPERATIVE_LANGUAGE = re.compile(
    r"\b(?:shall|must|may|means|includes|is\s+entitled|shall\s+not|"
    r"no\s+person|every\s+person|any\s+person|whoever|provided\s+that)\b",
    re.IGNORECASE,
)

# The masthead every Gazette of India PDF opens with. The Devanagari in these
# scans is ISCII rendered through a Latin font, so "रजिस्ट्री सं" arrives as
# "jftLVªh lañ" and "प्राधिकार से प्रकाशित" as "izkf/kdkj ls izdkf'kr". It is
# unreadable to a reader and to an embedding model alike.
#
# These matter more than their count suggests. They sit on the first page of
# the most-queried Acts -- the BNSS, the BNS, the Bharatiya Sakshya Adhiniyam --
# and build_embed_text prefixes each chunk with its Act name, so an indexed
# masthead becomes a well-labelled candidate for every query naming that Act,
# carrying no law at all.
_GAZETTE_TRANSLITERATION = re.compile(
    r"jftLVªh|izkf/kdkj|izdkf'kr|Hkkjr\s+dk\s+jkti=|vlk/kkj\.k",
)
_GAZETTE_MASTHEAD = re.compile(
    r"REGISTERED\s+NO\.|PUBLISHED\s+BY\s+AUTHORITY|"
    r"THE\s+GAZETTE\s+OF\s+INDIA|EXTRAORDINARY",
    re.IGNORECASE,
)

_MINIMUM_INDEXED_WORDS = 6


def classify_quality(
    text: str,
    *,
    section: str | None = None,
    minimum_words: int = _MINIMUM_INDEXED_WORDS,
) -> ChunkQuality:
    """Decide whether a chunk can carry a legal answer.

    Rejects only on a positive signal of furniture. A short chunk that uses
    operative legal language — "means", "shall", "whoever" — is kept whatever
    its length, because that is what a definition clause looks like.
    """
    stripped = (text or "").strip()
    if not stripped:
        return ChunkQuality("noise", "empty")

    words = stripped.split()

    if _REFERENCE_NUMBER.match(stripped):
        return ChunkQuality("noise", "reference_number")
    if _PAGE_ARTEFACT.match(stripped):
        return ChunkQuality("noise", "page_artefact")
    if _TOC_LEADERS.search(stripped):
        return ChunkQuality("noise", "table_of_contents")
    if (
        _AMENDMENT_NOTE.match(stripped)
        and (
            _AMENDMENT_MARKERS.search(stripped)
            # Or it names the instrument it was made by, which is the same
            # quality of evidence and far more common. See
            # _AMENDMENT_INSTRUMENT.
            or (
                _AMENDMENT_INSTRUMENT.search(stripped)
                and len(words) <= _MAXIMUM_FURNITURE_WORDS
            )
        )
        and not _OPERATIVE_LANGUAGE.search(stripped)
    ):
        # Three signals required. "Omitted" alone appears in real provisions
        # about omitted particulars; paired with "ibid" or "w.e.f." it reads as
        # an editorial note. The third test is the one that matters: chunk
        # boundaries do not respect footnotes, so a chunk can open with an
        # editorial note and carry on into the provision it annotates. If
        # operative language appears anywhere in the chunk, there is a
        # provision in here and it is kept.
        #
        # This does keep the occasional footnote that quotes amended text
        # containing "shall". Keeping a footnote costs a little precision;
        # deleting a provision costs a citizen their answer.
        return ChunkQuality("noise", "amendment_footnote")
    if _BARE_HEADING.match(stripped) and len(words) <= 8:
        return ChunkQuality("noise", "bare_heading")
    if len(words) <= _MAXIMUM_FURNITURE_WORDS and not _OPERATIVE_LANGUAGE.search(stripped):
        # Each of these is anchored on the chunk's own leading number, so a
        # provision that mentions an address or a judge's name is untouched;
        # only a chunk that *is* the list entry matches. The length bound and
        # the absence of operative language are the other two signals.
        if _NUMBERED_FOOTNOTE_REF.match(stripped):
            return ChunkQuality("noise", "footnote_reference")
        if _NUMBERED_CASE_CITATION.match(stripped):
            return ChunkQuality("noise", "case_citation_footnote")
        if _NUMBERED_PERSON.match(stripped):
            return ChunkQuality("noise", "numbered_person_list")
        if _NUMBERED_FORM_FIELD.match(stripped):
            return ChunkQuality("noise", "numbered_form_field")
    if (
        _GAZETTE_TRANSLITERATION.search(stripped)
        and _GAZETTE_MASTHEAD.search(stripped)
        and not _OPERATIVE_LANGUAGE.search(stripped)
    ):
        # Three signals, for the same reason the amendment-footnote rule needs
        # three: a chunk that opens on the masthead can run on into section 1
        # of the Act. Operative language anywhere in the chunk keeps it.
        return ChunkQuality("noise", "gazette_masthead")

    if len(words) < minimum_words:
        # The escape hatch that keeps one-line provisions: a numbered section
        # with operative language is a provision however short it is.
        if _OPERATIVE_LANGUAGE.search(stripped) or section:
            return ChunkQuality("indexed")
        return ChunkQuality("noise", "too_short_no_operative_language")

    return ChunkQuality("indexed")


# --- structural role ---------------------------------------------------------

# A chunk gets exactly one role, so only roles that describe a whole chunk
# belong here. Proviso, explanation and illustration do not: they are spans
# inside a provision, and a 700-token window holds several. Anchored at the
# start of a chunk they matched almost nothing -- 1,280 chunks contain a
# proviso and none were labelled one -- while implying the corpus had been
# checked for them.
_ROLE_PATTERNS: tuple[tuple[StructuralRole, re.Pattern[str]], ...] = (
    ("definition", re.compile(r'\bmeans\b|\bshall\s+mean\b|\bis\s+defined\s+as\b', re.I)),
    ("schedule", re.compile(r"^\s*(?:the\s+)?\w*\s*schedule\b", re.I)),
)

# What a chunk *contains*, which is a fact about the whole chunk and can be
# several things at once. This is where proviso and its relatives belong: an
# advocate asking for the exceptions to a section wants the chunk carrying the
# proviso, and that chunk's role is still "provision".
_SUB_UNIT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("proviso", re.compile(r"\bprovided\s+(?:that|further|also)\b", re.I)),
    # These begin a sub-unit wherever they appear -- at the start of a line, or
    # mid-line after the sentence they qualify. Requiring line-start is the
    # same anchoring mistake that left 1,280 provisos unlabelled.
    ("explanation", re.compile(r"(?:^|[\n.;–—])\s*explanation\b\s*[\d]*\s*[.\-–—:]", re.I)),
    ("illustration", re.compile(r"(?:^|[\n.;–—])\s*illustrations?\b\s*[\d]*\s*[.\-–—:()]", re.I)),
    ("exception", re.compile(r"(?:^|[\n.;–—])\s*exception\b\s*[\d]*\s*[.\-–—:]", re.I)),
)


def sub_units(text: str) -> tuple[str, ...]:
    """Which sub-provisions appear anywhere in this chunk.

    Distinct from the role: a chunk is one thing, but it can contain several.
    """
    body = text or ""
    return tuple(name for name, pattern in _SUB_UNIT_PATTERNS if pattern.search(body))

# Judgment sections, from the structural parser's own vocabulary.
_JUDGMENT_ROLES: dict[str, StructuralRole] = {
    "facts": "facts",
    "issues": "issues",
    "appellant_arguments": "arguments",
    "respondent_arguments": "arguments",
    "court_analysis": "reasoning",
    "authorities_cited": "reasoning",
    "ratio": "ratio",
    "final_order": "order",
}


def structural_role(
    text: str,
    *,
    unit_kind: str | None = None,
    section: str | None = None,
) -> StructuralRole:
    """What kind of legal material this chunk is.

    Police need procedure separated from substantive law; advocate needs a
    judgment's ratio separated from its recitation of facts. Both are decided
    here once rather than re-derived per feature.
    """
    if unit_kind:
        folded = unit_kind.casefold()
        if folded in _JUDGMENT_ROLES:
            return _JUDGMENT_ROLES[folded]

    stripped = (text or "").strip()
    for role, pattern in _ROLE_PATTERNS:
        if pattern.search(stripped):
            return role
    if section:
        return "provision"
    return "prose"


# --- embedded form -----------------------------------------------------------

# Long enough to place the chunk, short enough not to dominate its own
# embedding. A prefix that outweighs the text makes every chunk of one Act look
# alike, which is the opposite of the intent.
_MAX_PREFIX_CHARACTERS = 180


def build_embed_text(
    text: str,
    *,
    title: str | None = None,
    act_name: str | None = None,
    heading_path: list[str] | None = None,
    section: str | None = None,
) -> str:
    """The text to embed, as distinct from the text to quote.

    A citation must quote the provision as written. An embedding wants the
    provision plus enough context to know what it is: stored bare, the
    Constitution's Article 14 is the four words "14. Equality before law.",
    which is almost nothing for a citizen's question to match against.

    The prefix is built from metadata every chunk already carries, so this
    costs no inference. It is deliberately not written into `text`.
    """
    body = (text or "").strip()
    if not body:
        return body

    parts: list[str] = []
    name = (act_name or title or "").strip()
    if name:
        parts.append(name)

    # The innermost heading places the chunk; the whole path is usually longer
    # than the provision it introduces.
    if heading_path:
        innermost = str(heading_path[-1]).strip()
        if innermost and innermost.casefold() not in name.casefold():
            parts.append(innermost)

    if section:
        parts.append(f"Section {section}".strip())

    if not parts:
        return body

    prefix = " — ".join(parts)[:_MAX_PREFIX_CHARACTERS].rstrip(" —")
    return f"{prefix} — {body}"
