from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LegalRoleProfile:
    role: str
    label: str
    objective: str
    response_contract: str
    safety_boundary: str


@dataclass(frozen=True, slots=True)
class SpecialistAgent:
    id: str
    label: str
    objective: str


ROLE_PROFILES: dict[str, LegalRoleProfile] = {
    "citizen": LegalRoleProfile(
        role="citizen",
        label="Citizen legal information assistant",
        objective="Explain the located law and procedure in plain language so a member of the public can understand practical next steps.",
        response_contract="Prefer a short explanation, a numbered procedural checklist, required documents or facts, and when professional or emergency help may be appropriate.",
        safety_boundary="Do not present research as personalised legal advice, predict an outcome, or invent a police/court procedure not established by the evidence.",
    ),
    "police": LegalRoleProfile(
        role="police",
        label="Police investigation and procedure assistant",
        objective="Support lawful, evidence-led investigation and procedural compliance while preserving facts, uncertainty and chain-of-custody concerns.",
        response_contract="Separate known facts, governing authority, procedural duties, evidence gaps and review checkpoints. Never fill an unknown fact.",
        safety_boundary="Do not recommend coercion, rights violations, evidence manipulation, discriminatory action or bypassing mandatory safeguards and supervisory review.",
    ),
    "advocate": LegalRoleProfile(
        role="advocate",
        label="Advocate research and strategy assistant",
        objective="Produce two-sided, authority-grounded legal research that identifies issues, support, weaknesses and lawful counterarguments.",
        response_contract="Structure analysis as issue, governing rule, application, adverse argument, response and evidence still required.",
        safety_boundary="Do not fabricate precedent, guarantee an outcome, conceal adverse authority, coach false evidence or suggest unethical evasion of law or procedure.",
    ),
    "admin": LegalRoleProfile(
        role="admin",
        label="Administrative legal research assistant",
        objective="Provide neutral corpus-grounded legal research while keeping operational administration separate from legal conclusions.",
        response_contract="Use the same verified authority and uncertainty standards as general legal research.",
        safety_boundary="Administrative access does not authorise unsupported legal claims or disclosure of private case material outside an explicitly authorised matter.",
    ),
}


SPECIALIST_AGENTS: dict[str, tuple[SpecialistAgent, ...]] = {
    "citizen": (
        SpecialistAgent("procedure_navigator", "Procedure Navigator", "Turn verified law into a plain-language sequence of practical steps and missing information."),
        SpecialistAgent("rights_explainer", "Rights Explainer", "Explain verified constitutional and statutory protections, limits and escalation points in plain language."),
        SpecialistAgent("authority_finder", "Authority Finder", "Locate and distinguish the exact Acts, provisions and decisions supporting the answer."),
    ),
    "police": (
        SpecialistAgent("fir_review", "FIR Review Agent", "Preserve reported facts and uncertainty while checking FIR requirements and missing fields."),
        SpecialistAgent("evidence_integrity", "Evidence Integrity Agent", "Examine authenticity, preservation and chain-of-custody safeguards without filling factual gaps."),
        SpecialistAgent("procedure_compliance", "Procedure Compliance Agent", "Check verified arrest, search, seizure, recording and supervisory safeguards."),
        SpecialistAgent("case_evidence_search", "Case Evidence Search Agent", "Compare public authority with only the authorised police matter evidence."),
    ),
    "advocate": (
        SpecialistAgent("defence_strategy", "Defence Strategy Agent", "Build a lawful two-sided issue analysis with adverse arguments and evidence gaps."),
        SpecialistAgent("authority_mapper", "Authority Mapper", "Map each legal proposition to verified provisions and controlling authority."),
        SpecialistAgent("evidence_challenge", "Evidence Challenge Agent", "Identify verified admissibility, authenticity, contradiction and proof issues."),
        SpecialistAgent("precedent_comparator", "Precedent Comparator", "Compare decision hierarchy, material similarities and legally relevant distinctions."),
    ),
    "admin": (
        SpecialistAgent("corpus_inspector", "Corpus Inspector", "Inspect provenance and return neutral verified corpus research."),
    ),
}


def select_specialist_agent(role: object, query: str, case_id: str | None = None) -> SpecialistAgent:
    resolved_role = str(role) if str(role) in SPECIALIST_AGENTS else "citizen"
    agents = {agent.id: agent for agent in SPECIALIST_AGENTS[resolved_role]}
    text = query.casefold()

    if resolved_role == "citizen":
        if any(term in text for term in ("authority", "judgment", "case law", "section", " act ")):
            return agents["authority_finder"]
        if any(term in text for term in ("right", "article", "constitution", "protection", "fundamental")):
            return agents["rights_explainer"]
        return agents["procedure_navigator"]

    if resolved_role == "police":
        if any(term in text for term in ("fir", "first information", "complaint")):
            return agents["fir_review"]
        if any(term in text for term in ("authentic", "chain of custody", "electronic evidence", "forensic", "integrity")):
            return agents["evidence_integrity"]
        if case_id and any(term in text for term in ("case", "matter", "statement", "private evidence")):
            return agents["case_evidence_search"]
        return agents["procedure_compliance"]

    if resolved_role == "advocate":
        if any(term in text for term in ("admissib", "authentic", "contradiction", "proof", "evidence")):
            return agents["evidence_challenge"]
        if any(term in text for term in ("precedent", "compare", "distinguish", "judgment", "case law")):
            return agents["precedent_comparator"]
        if any(term in text for term in ("authority", "section", "statute", "provision", " act ")):
            return agents["authority_mapper"]
        return agents["defence_strategy"]

    return agents["corpus_inspector"]


def specialist_prompt(state: dict) -> str:
    label = state.get("specialist_agent_label")
    objective = state.get("specialist_agent_objective")
    if not label or not objective:
        return ""
    return f"SPECIALIST AGENT: {label}\nSPECIALIST OBJECTIVE: {objective}"


def get_role_profile(role: object) -> LegalRoleProfile:
    return ROLE_PROFILES.get(str(role), ROLE_PROFILES["citizen"])


def profile_prompt(role: object) -> str:
    profile = get_role_profile(role)
    return (
        f"ROLE PROFILE: {profile.label}\n"
        f"OBJECTIVE: {profile.objective}\n"
        f"RESPONSE CONTRACT: {profile.response_contract}\n"
        f"SAFETY BOUNDARY: {profile.safety_boundary}"
    )
