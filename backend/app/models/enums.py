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
