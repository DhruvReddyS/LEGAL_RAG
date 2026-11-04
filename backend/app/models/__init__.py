from app.models.advocate import AdvocateWorkProduct, MatterCalendarEvent
from app.models.admin_tools import (
    AccountFlag,
    CorpusWorkItem,
    DocumentQuarantine,
    FeedbackTriage,
    GateRun,
    ReleaseDecision,
    RetentionPolicy,
    RetentionRun,
)
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.case import Case, CaseDocument, GeneratedDocument
from app.models.chat import ChatMessage, ChatSession, Feedback
from app.models.corpus import Bookmark, CorpusIntake, CorpusSource
from app.models.enums import (
    CaseRoleType,
    ChatMessageRole,
    CorpusSourceType,
    FeedbackRating,
    JobStatus,
    JobType,
    OffenceGravity,
    UserRole,
)
from app.models.citizen import ChatMessageAnnotation, CitizenDeadline
from app.models.investigation import InvestigationFacts
from app.models.job import Job, JobEvent
from app.models import police as _police_models  # noqa: F401  (registers the tables)
from app.models.platform import (
    ChatSessionMeta,
    ConsentRecord,
    ErasureReceipt,
    PasswordResetCode,
    RecoveryCode,
    UserSecurity,
    UserSession,
)
from app.models.storage import StorageNamespace, StorageObject
from app.models.token import RevokedRefreshToken
from app.models.user import Permission, Role, RolePermission, User

__all__ = [
    "AdvocateWorkProduct",
    "AccountFlag",
    "CorpusWorkItem",
    "DocumentQuarantine",
    "FeedbackTriage",
    "GateRun",
    "ReleaseDecision",
    "RetentionPolicy",
    "RetentionRun",
    "AuditLog",
    "MatterCalendarEvent",
    "Base",
    "Bookmark",
    "Case",
    "CaseDocument",
    "CaseRoleType",
    "ChatMessage",
    "ChatMessageRole",
    "ChatSession",
    "ChatSessionMeta",
    "ConsentRecord",
    "ErasureReceipt",
    "PasswordResetCode",
    "RecoveryCode",
    "UserSecurity",
    "UserSession",
    "CorpusSource",
    "ChatMessageAnnotation",
    "CitizenDeadline",
    "InvestigationFacts",
    "OffenceGravity",
    "CorpusIntake",
    "CorpusSourceType",
    "Feedback",
    "FeedbackRating",
    "GeneratedDocument",
    "Job",
    "JobEvent",
    "JobStatus",
    "JobType",
    "Permission",
    "RevokedRefreshToken",
    "Role",
    "RolePermission",
    "StorageNamespace",
    "StorageObject",
    "User",
    "UserRole",
]
