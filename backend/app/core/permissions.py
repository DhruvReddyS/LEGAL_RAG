CORPUS_READ = "corpus:read"
CHAT_USE = "chat:use"
BOOKMARK_MANAGE_OWN = "bookmark:manage:own"
FEEDBACK_CREATE = "feedback:create"

CASE_CREATE = "case:create"
CASE_READ_OWN = "case:read:own"
CASE_EDIT_OWN = "case:edit:own"
CASE_DELETE_OWN = "case:delete:own"
CASE_DOCUMENT_MANAGE_OWN = "case:document:manage:own"

POLICE_INVESTIGATION_OWN = "police:investigation:own"
ADVOCATE_STRATEGY_OWN = "advocate:strategy:own"
ADVOCATE_DEBATE_OWN = "advocate:debate:own"

ADMIN_AUDIT_READ = "admin:audit:read"
ADMIN_USER_MANAGE = "admin:user:manage"
ADMIN_CORPUS_MANAGE = "admin:corpus:manage"

ALL_PERMISSIONS = frozenset(
    {
        CORPUS_READ,
        CHAT_USE,
        BOOKMARK_MANAGE_OWN,
        FEEDBACK_CREATE,
        CASE_CREATE,
        CASE_READ_OWN,
        CASE_EDIT_OWN,
        CASE_DELETE_OWN,
        CASE_DOCUMENT_MANAGE_OWN,
        POLICE_INVESTIGATION_OWN,
        ADVOCATE_STRATEGY_OWN,
        ADVOCATE_DEBATE_OWN,
        ADMIN_AUDIT_READ,
        ADMIN_USER_MANAGE,
        ADMIN_CORPUS_MANAGE,
    }
)
