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
