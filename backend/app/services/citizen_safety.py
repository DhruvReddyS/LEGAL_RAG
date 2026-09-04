"""Deterministic pre-checks that run before any retrieval or generation.

Two categories of request must not reach the RAG pipeline at all.

Urgent situations need help now, not a legal research answer. A citizen
describing immediate danger should see an emergency number first; a
four-minute Deep review is the wrong response even if it would be accurate.

Out-of-scope requests need a refusal with a route to a human. The pipeline
would happily answer "should I plead guilty" from statute text, and the
verifier would pass it, because every claim would be grounded. Grounding is not
the same as appropriateness: that question needs a lawyer who knows the file.

This is code, not a prompt. A model asked to self-police these produces a
different answer on a reworded question, and the failure is silent. Detection
here is conservative by design - it only fires on explicit phrasing, because a
false refusal on an ordinary legal question is its own harm.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

InterventionKind = Literal["emergency", "refusal"]


@dataclass(frozen=True)
class SafetyIntervention:
    kind: InterventionKind
    reason: str
    answer: str


# Numbers are national and toll-free. Kept in one place so a deployment for
# another jurisdiction changes data, not logic.
EMERGENCY_CONTACTS = (
    ("Police, fire or ambulance", "112"),
    ("Women's helpline", "1091"),
    ("Child helpline", "1098"),
    ("Mental health support (Tele-MANAS)", "14416"),
    ("Cyber crime", "1930"),
)


# Immediate physical danger, self-harm, or an offence in progress. Matched on
# explicit phrasing only: "domestic violence law" is research, "he is hitting
# me right now" is not.
_EMERGENCY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "immediate_violence",
        re.compile(
            r"\b(?:is|are|being)\s+(?:currently\s+)?"
            r"(?:hitting|beating|attacking|assaulting|strangling|threatening to kill)\b"
            r"|\b(?:he|she|they|someone)\s+(?:is|are)\s+going to kill\b"
            # "help me now" is a real distress phrase and also how a citizen
            # opens a polite request -- "can you help me now with the FIR
            # procedure" was screened as immediate violence. Only the standalone
            # cry counts, so a continuation that asks *about* something does not.
            r"|\bin danger right now\b"
            r"|\bhelp me (?:right )?now\b"
            r"(?!\s+(?:with|to|understand|about|on|in|regarding|for|by)\b)",
            re.I,
        ),
    ),
    (
        "self_harm",
        # First-person expression only. Abetment of suicide is a real charge
        # under BNS s.108 and "suicide prevention" is a real policy question,
        # so a bare mention of the word must reach the corpus, not a helpline.
        # Someone in crisis writes in the first person.
        re.compile(
            r"\b(?:kill|harm|hurt|cut)(?:ing)?\s+myself\b"
            r"|\bend(?:ing)?\s+my\s+(?:own\s+)?life\b"
            r"|\b(?:i|i'm|im)\s+(?:want|wanna|going|plan|am|feel|feeling)\b[^.?!]{0,20}"
            r"\b(?:to\s+die|suicidal|to\s+end\s+it)\b"
            r"|\bi\s+(?:want|wish)\s+to\s+die\b"
            r"|\bfeeling\s+suicidal\b"
            r"|\bdon'?t\s+want\s+to\s+(?:live|be\s+alive)\b",
            re.I,
        ),
    ),
    (
        "offence_in_progress",
        re.compile(
            r"\b(?:breaking into|someone is inside)\b.{0,30}\b(?:house|home|flat)\b"
            # "being kidnapped" alone screened "what is the punishment for
            # being kidnapped?" as an emergency. A report needs someone it is
            # happening to, or an explicit now.
            r"|\b(?:i|we|she|he|they|someone|my\s+\w+)\s+(?:is|am|are)\s+being\s+kidnapped\b"
            r"|\bbeing kidnapped\s+(?:right\s+)?now\b"
            r"|\bbeing followed right now\b"
            r"|\bheld against (?:my|her|his) will\b",
            re.I,
        ),
    ),
    (
        # 1930 is listed as a contact but nothing reached it. For online
        # financial fraud the first hour decides whether the transfer can be
        # frozen, so a citizen reporting one needs the number before they need
        # the law -- the corpus answer is worth less than the phone call.
        #
        # Three signals, matching the amendment-footnote discipline elsewhere:
        # a fraud marker, something that holds money, and money actually
        # moving. "What is the punishment for fraud?" carries only the first
        # and stays a research question, which is the failure mode to avoid --
        # an emergency reply replaces the answer, so a false positive costs a
        # citizen their answer exactly as a false refusal would.
        "financial_fraud_in_progress",
        re.compile(
            r"(?=.*\b(?:scam(?:med|mer|ming)?|frauds?|fraudulent|defrauded|"
            r"phish\w*|unauthoris\w*|unauthoriz\w*)\b)"
            r"(?=.*\b(?:money|amount|funds|rupees|savings|salary|account|"
            r"upi|otp|card|wallet|bank)\b)"
            r"(?=.*\b(?:debited|deducted|withdrawn|transferred|lost|gone|"
            r"stolen|taken|emptied|siphoned)\b)",
            re.I | re.S,
        ),
    ),
    (
        "child_at_risk",
        re.compile(
            r"\b(?:child|minor|girl|boy)\b.{0,40}\b(?:being abused|is being hurt|in danger)\b"
            r"|\bchild marriage\b.{0,30}\b(?:tomorrow|today)\b",
            re.I,
        ),
    ),
)


# Requests the platform must not answer regardless of what the corpus supports.
_REFUSAL_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "personalised_advice",
        "decide-for-me",
        re.compile(
            r"\bshould i\b.{0,40}\b(?:plead|accept|settle|sign|confess|admit|sue|withdraw)\b"
            r"|\bwhat should i do\b.{0,20}\bin (?:my|this) case\b"
            r"|\btell me what to do\b.{0,20}\b(?:in court|at the hearing)\b",
            re.I,
        ),
    ),
    (
        "outcome_prediction",
        "outcome-prediction",
        re.compile(
            r"\b(?:will i|would i|am i going to|chances? (?:of|that) i)\b"
            r".{0,40}\b(?:win|lose|convicted|acquitted|jail|prison|granted bail)\b"
            r"|\bwhat are my chances\b|\bhow likely am i to\b",
            re.I,
        ),
    ),
    (
        "evidence_interference",
        "evidence-interference",
        re.compile(
            r"\b(?:hide|destroy|delete|erase|fabricate|forge|plant|tamper with)\b"
            r".{0,30}\b(?:evidence|record|document|message|proof|cctv|footage)\b"
            r"|\bhow (?:do|can) i\b.{0,30}\b(?:avoid|escape|dodge)\b.{0,20}\b(?:arrest|police|summons)\b"
            r"|\bmake it look like\b",
            re.I,
        ),
    ),
    (
        "false_statement",
        "false-statement",
        re.compile(
            r"\b(?:lie|false statement|false affidavit|fake)\b.{0,30}\b(?:court|police|affidavit|fir|complaint)\b"
            r"|\bwhat should i say\b.{0,30}\bso (?:they|he|she|it) (?:believe|think)\b",
            re.I,
        ),
    ),
)


_EMERGENCY_PREAMBLE = (
    "## If you are in immediate danger\n\n"
    "Please contact emergency services now. They can act immediately; this "
    "service cannot.\n\n"
)

_LEGAL_AID = (
    "## Free legal help\n\n"
    "- **National Legal Services Authority (NALSA)** — helpline **15100**. Free "
    "legal aid is a right under the Legal Services Authorities Act, 1987 for "
    "those who qualify, including women, children, and people below the "
    "prescribed income limit.\n"
    "- Your **District Legal Services Authority** operates from the district "
    "court complex and can assign a lawyer without charge.\n"
)


def _contact_list() -> str:
    return "\n".join(f"- **{label}** — **{number}**" for label, number in EMERGENCY_CONTACTS)


def _emergency_answer() -> str:
    return (
        _EMERGENCY_PREAMBLE
        + _contact_list()
        + "\n\n## After you are safe\n\n"
        "Come back and ask your legal question, and this service can explain "
        "the law and the procedure that applies. It can research the law; it "
        "cannot send help.\n\n"
        + _LEGAL_AID
    )


_REFUSAL_ANSWERS = {
    "decide-for-me": (
        "## This needs a lawyer, not a research tool\n\n"
        "Whether to plead, settle, sign or withdraw depends on the evidence in "
        "your file, the strength of the case against you, and consequences that "
        "reach beyond the law itself. Nobody should answer that without reading "
        "your papers, and this service has not read them.\n\n"
        "It can still help you prepare: ask what a provision means, what a "
        "procedure requires, or what rights apply at a particular stage, and "
        "you will get a sourced answer to take to your lawyer.\n\n"
        + _LEGAL_AID
    ),
    "outcome-prediction": (
        "## Case outcomes cannot be predicted here\n\n"
        "This service will not estimate whether a case is won, lost, or what "
        "sentence might follow. Outcomes turn on evidence, procedure and "
        "judicial assessment of facts that are not in the legal corpus, and a "
        "confident-sounding number would be misleading rather than useful.\n\n"
        "What it can do is set out the governing law, the tests a court "
        "applies, and the procedure — each traced to its source.\n\n"
        + _LEGAL_AID
    ),
    "evidence-interference": (
        "## This is not something this service will help with\n\n"
        "Concealing, destroying or fabricating evidence, and evading lawful "
        "process, are themselves offences, and they routinely make the original "
        "situation considerably worse.\n\n"
        "If you are facing an investigation or a proceeding, a lawyer can act "
        "for you lawfully, including where you believe the process against you "
        "is unfair.\n\n"
        + _LEGAL_AID
    ),
    "false-statement": (
        "## This is not something this service will help with\n\n"
        "Making a false statement to the police or a court is a criminal "
        "offence in its own right.\n\n"
        "If your account is true but you are unsure how to present it, that is "
        "exactly what a lawyer is for, and legal aid is available free of "
        "charge to those who qualify.\n\n"
        + _LEGAL_AID
    ),
}


def screen_citizen_query(query: str) -> SafetyIntervention | None:
    """Return an intervention when a query must not reach the pipeline.

    Emergencies are checked first: a message can contain both an emergency and
    a request the service would otherwise refuse, and the emergency wins.
    """
    text = str(query or "")
    if not text.strip():
        return None

    for reason, pattern in _EMERGENCY_PATTERNS:
        if pattern.search(text):
            return SafetyIntervention(
                kind="emergency", reason=reason, answer=_emergency_answer()
            )

    for reason, answer_key, pattern in _REFUSAL_PATTERNS:
        if pattern.search(text):
            return SafetyIntervention(
                kind="refusal", reason=reason, answer=_REFUSAL_ANSWERS[answer_key]
            )

    return None
