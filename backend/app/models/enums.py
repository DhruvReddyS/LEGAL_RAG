from enum import StrEnum


class UserRole(StrEnum):
    CITIZEN = "citizen"
    POLICE = "police"
    ADVOCATE = "advocate"
    ADMIN = "admin"


class CaseRoleType(StrEnum):
    POLICE = "police"
    ADVOCATE = "advocate"


class ChatMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class OffenceGravity(StrEnum):
    """The distinction BNSS s.187(3) turns on, and nothing finer.

    UNKNOWN is a real member, not a missing value. An uncatalogued offence
    must produce a stated unknown rather than a plausible default: assuming
    the shorter period flatters compliance, and assuming the longer one
    hides a default-bail entitlement that has already accrued.
    """

    DEATH_LIFE_OR_TEN_YEARS_OR_MORE = "death_life_or_ten_years_or_more"
    OTHER = "other"
    UNKNOWN = "unknown"


class CorpusSourceType(StrEnum):
    ACT = "act"
    JUDGMENT = "judgment"
    NOTIFICATION = "notification"


class FeedbackRating(StrEnum):
    UP = "up"
    DOWN = "down"


class JobType(StrEnum):
    DEEP_REVIEW = "deep_review"
    OCR_INGESTION = "ocr_ingestion"
    DOCUMENT_ANALYSIS = "document_analysis"
    EXPORT = "export"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
