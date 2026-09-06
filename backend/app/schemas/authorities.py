"""Request and response shapes for the authority check."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.authority_check import AuthorityFinding


class AuthorityCheckRequest(BaseModel):
    draft: str = Field(
        min_length=1,
        max_length=200_000,
        description="Draft text. Citations are extracted from it deterministically.",
    )


class CitationCheckResponse(BaseModel):
    citation: str
    code: str
    section: str
    finding: AuthorityFinding
    successors: list[str]
    advice: str
    needs_attention: bool


class AuthorityCheckResponse(BaseModel):
    checked: list[CitationCheckResponse]
    # Counts, so a long draft leads with the number that matters rather than
    # requiring the reader to scan every row.
    needs_attention: int
    not_re_enacted: int
    # Citations recognised but outside the 2023 concordance. Reported so the
    # reader knows the check was partial; an absent number would imply it
    # was complete.
    not_checked: int
