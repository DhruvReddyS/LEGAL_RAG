from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FeedbackRequest(BaseModel):
    message_id: uuid.UUID
    rating: Literal["up", "down"]
    # Bounded because this is free text a user types about their own legal
    # situation; it is stored, not sent to a model.
    correction_text: str | None = Field(default=None, max_length=2000)

    @field_validator("correction_text")
    @classmethod
    def blank_is_absent(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: uuid.UUID
    rating: str
    correction_text: str | None
    created_at: datetime
