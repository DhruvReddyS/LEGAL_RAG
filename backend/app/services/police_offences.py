"""What each common BNS offence is made of, in the Sanhita's own words.

Every element carries the passage it was read from. `tests/test_police_legal_sources.py`
checks each passage against the BNS text in the corpus, so a passage that is not in
the Act fails the build instead of reaching an officer.

Whether the evidence establishes an element is the officer's assessment, recorded and
attributed. No model reads the evidence here, and nothing below concludes that an
offence is made out: the strongest thing this says is that every element has been
marked established and has something on record behind it. Exceptions, general defences
and sentencing are outside it and each offence says which it leaves out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = ["ElementState", "OFFENCES", "OverallFinding", "Offence", "OffenceElement", "assess"]


class ElementState(StrEnum):
    ESTABLISHED = "established"
    NOT_ESTABLISHED = "not_established"
    # The default. Nobody has assessed it, or nothing is on record for it.
    CANNOT_BE_DETERMINED = "cannot_be_determined"


class OverallFinding(StrEnum):
    ALL_ELEMENTS_SUPPORTED = "all_elements_supported"
    ELEMENT_NOT_ESTABLISHED = "element_not_established"
    CANNOT_BE_DETERMINED = "cannot_be_determined"


@dataclass(frozen=True)
class OffenceElement:
    key: str
    element: str
    provision: str
    # Verbatim from the Act, checked against the corpus by a test.
    source_quote: str


@dataclass(frozen=True)
class Offence:
    key: str
    title: str
    provision: str
    elements: tuple[OffenceElement, ...]
    # What this checklist does not cover for this offence.
    limits: str = ""
    related: tuple[str, ...] = field(default=())


def _e(key: str, element: str, provision: str, quote: str) -> OffenceElement:
    return OffenceElement(key, element, provision, quote)


OFFENCES: dict[str, Offence] = {
    offence.key: offence
    for offence in (
        Offence(
            "murder",
            "Murder",
            "BNS s.103(1)",
            (
                _e("death_caused", "The accused caused the death of the deceased by an act.", "BNS s.100",
                   "causes death by doing an act"),
                _e("clause_of_s101", "The act falls within a clause of s.101: done with the intention of causing death, or of such bodily injury as the offender knows is likely to cause death or as is sufficient in the ordinary course of nature to cause death; or so imminently dangerous that it must in all probability cause death, without excuse.", "BNS s.101",
                   "culpable homicide is murder"),
                _e("punishable", "The offence is murder as punished by s.103(1).", "BNS s.103(1)",
                   "Whoever commits murder shall be punished with death or imprisonment for life"),
            ),
            limits="The five Exceptions to s.101 and the general exceptions are not assessed here. If an Exception applies the offence is s.105.",
            related=("culpable_homicide",),
        ),
        Offence(
            "culpable_homicide",
            "Culpable homicide not amounting to murder",
            "BNS s.105",
            (
                _e("death_caused", "The accused caused the death by an act.", "BNS s.100",
                   "causes death by doing an act"),
                _e("intention_or_knowledge", "The act was done with the intention of causing death, or such bodily injury as is likely to cause death, or with the knowledge that it was likely to cause death.", "BNS s.100",
                   "with the knowledge that he is likely by such act to cause death"),
                _e("not_murder", "The homicide does not amount to murder.", "BNS s.105",
                   "Whoever commits culpable homicide not amounting to murder"),
            ),
            limits="s.105 sets different punishment for intention and for knowledge. The general exceptions are not assessed here.",
        ),
        Offence(
            "death_by_negligence",
            "Causing death by negligence",
            "BNS s.106(1)",
            (
                _e("death_caused", "The accused caused the death of a person.", "BNS s.106(1)",
                   "Whoever causes death of any person"),
                _e("rash_or_negligent", "The death was caused by a rash or negligent act.", "BNS s.106(1)",
                   "by doing any rash or negligent act"),
                _e("short_of_culpable_homicide", "The act does not amount to culpable homicide.", "BNS s.106(1)",
                   "not amounting to culpable homicide"),
            ),
            limits="s.106(2), rash and negligent driving and escaping without reporting, has its own elements and is not covered.",
        ),
        Offence(
            "abetment_of_suicide",
            "Abetment of suicide",
            "BNS s.108",
            (
                _e("suicide_committed", "A person committed suicide.", "BNS s.108",
                   "If any person commits suicide"),
                _e("abetment", "The accused abetted the commission of that suicide.", "BNS s.108",
                   "whoever abets the commission of such suicide"),
            ),
            limits="What amounts to abetment is defined elsewhere in the Sanhita and is not expanded here.",
        ),
        Offence(
            "attempt_to_murder",
            "Attempt to murder",
            "BNS s.109(1)",
            (
                _e("act_done", "The accused did an act.", "BNS s.109(1)", "Whoever does any act"),
                _e("intention_or_knowledge", "It was done with such intention or knowledge, and in such circumstances, that if it had caused death the accused would be guilty of murder.", "BNS s.109(1)",
                   "if he by that act caused death, he would be guilty of murder"),
                _e("hurt_caused", "Whether hurt was caused to any person. This changes the punishment, not the offence.", "BNS s.109(1)",
                   "if hurt is caused to any person by such act"),
            ),
        ),
        Offence(
            "voluntarily_causing_hurt",
            "Voluntarily causing hurt",
            "BNS s.115(2)",
            (
                _e("act_done", "The accused did an act.", "BNS s.115(1)", "Whoever does any act"),
                _e("intention_or_knowledge", "With the intention of causing hurt, or the knowledge that hurt was likely.", "BNS s.115(1)",
                   "with the intention of thereby causing hurt to any person"),
                _e("hurt_caused", "Hurt was in fact caused.", "BNS s.115(1)",
                   "does thereby cause hurt to any person"),
            ),
            limits="s.122(1), hurt on grave and sudden provocation, is excepted by s.115(2) and is not assessed here.",
        ),
        Offence(
            "voluntarily_causing_grievous_hurt",
            "Voluntarily causing grievous hurt",
            "BNS s.117(2)",
            (
                _e("hurt_voluntarily_caused", "The accused voluntarily caused hurt.", "BNS s.117(1)",
                   "Whoever voluntarily causes hurt"),
                _e("intended_grievous", "The hurt intended, or known to be likely, was grievous.", "BNS s.117(1)",
                   "if the hurt which he intends to cause or knows himself to be likely to cause is grievous hurt"),
                _e("caused_grievous", "The hurt caused was grievous, of a kind listed in s.116.", "BNS s.116",
                   "The following kinds of hurt only are designated as"),
            ),
            limits="s.117(3) and (4) and s.122(2) are not assessed here.",
        ),
        Offence(
            "hurt_by_dangerous_means",
            "Voluntarily causing hurt by dangerous weapons or means",
            "BNS s.118(1)",
            (
                _e("hurt_voluntarily_caused", "The accused voluntarily caused hurt.", "BNS s.118(1)",
                   "voluntarily causes hurt by means of any instrument"),
                _e("dangerous_means", "By an instrument for shooting, stabbing or cutting, or one likely to cause death when used as a weapon, or by fire, poison, a corrosive or explosive substance, or another means s.118(1) lists.", "BNS s.118(1)",
                   "instrument for shooting, stabbing or cutting"),
            ),
            limits="s.118(2), grievous hurt by the same means, is punished separately.",
        ),
        Offence(
            "rape",
            "Rape",
            "BNS s.64(1)",
            (
                _e("sexual_act", "An act within s.63(a) to (d), by a man, upon a woman.", "BNS s.63",
                   "under the circumstances falling under any of the following seven descriptions"),
                _e("circumstance", "One of the seven circumstances in s.63: against her will; without her consent; consent obtained by fear, by a false belief as to marriage, or while unable to understand; under eighteen years of age; or unable to communicate consent.", "BNS s.63",
                   "with or without her consent, when she is under eighteen years of age"),
                _e("not_excepted", "Neither Exception to s.63 applies.", "BNS s.63",
                   "A medical procedure or intervention shall not constitute rape"),
            ),
            limits="The aggravated forms in s.64(2) and the offences in ss.65 to 71 have their own elements and are not covered.",
        ),
        Offence(
            "outraging_modesty",
            "Assault or criminal force to a woman with intent to outrage her modesty",
            "BNS s.74",
            (
                _e("assault_or_force", "The accused assaulted or used criminal force.", "BNS s.74",
                   "Whoever assaults or uses criminal force to any woman"),
                _e("on_a_woman", "The person assaulted is a woman.", "BNS s.74", "to any woman"),
                _e("intent_or_knowledge", "With intent to outrage her modesty, or knowing it to be likely.", "BNS s.74",
                   "will thereby outrage her modesty"),
            ),
        ),
        Offence(
            "stalking",
            "Stalking",
            "BNS s.78",
            (
                _e("following_or_monitoring", "A man followed a woman and contacted or tried to contact her repeatedly to foster personal interaction, or monitored her use of the internet, e-mail or other electronic communication.", "BNS s.78(1)",
                   "follows a woman and contacts, or attempts to contact such woman"),
                _e("clear_disinterest", "Where it is contact: despite a clear indication of disinterest by her.", "BNS s.78(1)",
                   "despite a clear indication of disinterest by such woman"),
                _e("no_proviso", "None of the three statutory answers applies. The man who pursued the conduct must prove them.", "BNS s.78(1)",
                   "such conduct shall not amount to stalking"),
            ),
        ),
        Offence(
            "dowry_death",
            "Dowry death",
            "BNS s.80",
            (
                _e("abnormal_death", "A woman died by burns or bodily injury, or otherwise than under normal circumstances.", "BNS s.80(1)",
                   "otherwise than under normal circumstances"),
                _e("within_seven_years", "Within seven years of her marriage.", "BNS s.80(1)",
                   "within seven years of her marriage"),
                _e("cruelty_soon_before", "Soon before her death she was subjected to cruelty or harassment by her husband or his relative.", "BNS s.80(1)",
                   "soon before her death she was subjected to cruelty or harassment"),
                _e("dowry_connection", "The cruelty or harassment was for, or in connection with, a demand for dowry.", "BNS s.80(1)",
                   "any demand for dowry"),
            ),
            limits="Dowry takes its meaning from s.2 of the Dowry Prohibition Act, 1961.",
        ),
        Offence(
            "cruelty_by_husband",
            "Cruelty by husband or relative of husband",
            "BNS s.85",
            (
                _e("relationship", "The accused is the woman's husband or a relative of her husband.", "BNS s.85",
                   "being the husband or the relative of the husband of a woman"),
                _e("cruelty", "The accused subjected her to cruelty, as s.86 defines it: wilful conduct likely to drive her to suicide or cause grave injury or danger to life, limb or health; or harassment to coerce her or a relation to meet an unlawful demand.", "BNS s.86",
                   "any wilful conduct which is of such a nature as is likely to drive the woman"),
            ),
        ),
        Offence(
            "kidnapping",
            "Kidnapping from lawful guardianship",
            "BNS s.137(2)",
            (
                _e("child_or_unsound", "The person is a child or a person of unsound mind.", "BNS s.137(1)",
                   "any child or any person of unsound mind"),
                _e("taken_from_keeping", "The accused took or enticed that person out of the keeping of the lawful guardian.", "BNS s.137(1)",
                   "out of the keeping of the lawful guardian"),
                _e("without_consent", "Without the guardian's consent.", "BNS s.137(1)",
                   "without the consent of such guardian"),
            ),
            limits="Kidnapping from India, s.137(1)(a), has different elements. The Exception to s.137(1) is not assessed here.",
        ),
        Offence(
            "theft",
            "Theft",
            "BNS s.303(2)",
            (
                _e("dishonest_intention", "The accused intended to take the property dishonestly.", "BNS s.303(1)",
                   "intending to take dishonestly any movable property"),
                _e("movable_property", "The property is movable.", "BNS s.303(1)",
                   "any movable property"),
                _e("out_of_possession", "It was in another person's possession.", "BNS s.303(1)",
                   "out of the possession of any person"),
                _e("without_consent", "Without that person's consent.", "BNS s.303(1)",
                   "without that person"),
                _e("moved", "The accused moved the property in order to such taking.", "BNS s.303(1)",
                   "moves that property in order to such taking"),
            ),
            limits="The aggravated forms in ss.304 to 307 add their own elements. The s.303(2) proviso on low-value first offences concerns sentence.",
        ),
        Offence(
            "snatching",
            "Snatching",
            "BNS s.304",
            (
                _e("theft", "The conduct amounts to theft, or is in order to commit it.", "BNS s.304(1)",
                   "Theft is snatching if, in order to commit theft"),
                _e("sudden_seizure", "The offender suddenly, quickly or forcibly seized, secured, grabbed or took the property.", "BNS s.304(1)",
                   "suddenly or quickly or forcibly seizes or secures or grabs or takes away"),
                _e("from_person", "From a person or from the person's possession.", "BNS s.304(1)",
                   "from any person or from his possession"),
            ),
        ),
        Offence(
            "robbery",
            "Robbery",
            "BNS s.309(4)",
            (
                _e("theft_or_extortion", "There was a theft or an extortion.", "BNS s.309(1)",
                   "In all robbery there is either theft or extortion"),
                _e("violence_or_fear", "For theft: to commit it or carry the property away, the offender voluntarily caused or attempted death, hurt or wrongful restraint, or fear of instant death, hurt or wrongful restraint. For extortion: at the time, in the victim's presence, by fear of instant death, hurt or wrongful restraint.", "BNS s.309(2)",
                   "voluntarily causes or attempts to cause to any person death or hurt or wrongful"),
            ),
            limits="s.309(4) raises the punishment for a robbery on the highway between sunset and sunrise. Attempt and voluntarily caused hurt are s.309(5) and (6).",
        ),
        Offence(
            "dacoity",
            "Dacoity",
            "BNS s.310(2)",
            (
                _e("robbery", "A robbery was committed or attempted.", "BNS s.310(1)",
                   "conjointly commit or attempt to commit a robbery"),
                _e("five_or_more", "Five or more persons were conjointly involved, counting those present and aiding.", "BNS s.310(1)",
                   "persons present and aiding such commission or attempt, amount to five or"),
            ),
            limits="Dacoity with murder, preparation, assembly and gang membership are s.310(3) to (6).",
        ),
        Offence(
            "criminal_breach_of_trust",
            "Criminal breach of trust",
            "BNS s.316(2)",
            (
                _e("entrustment", "The accused was entrusted with property, or with dominion over property.", "BNS s.316(1)",
                   "being in any manner entrusted with property"),
                _e("misappropriation", "The accused dishonestly misappropriated or converted it, or dishonestly used or disposed of it against a direction of law or a contract, or wilfully suffered another to do so.", "BNS s.316(1)",
                   "dishonestly misappropriates or converts to his own use that property"),
            ),
            limits="s.316(3) to (5), by a carrier, a clerk or a public servant, carry higher punishment.",
        ),
        Offence(
            "receiving_stolen_property",
            "Dishonestly receiving stolen property",
            "BNS s.317(2)",
            (
                _e("stolen_property", "The property is stolen property as s.317(1) defines it.", "BNS s.317(1)",
                   "is designated as stolen property"),
                _e("received_or_retained", "The accused dishonestly received or retained it.", "BNS s.317(2)",
                   "Whoever dishonestly receives or retains any stolen property"),
                _e("knowledge", "Knowing or having reason to believe it to be stolen.", "BNS s.317(2)",
                   "knowing or having reason to believe the same to be stolen property"),
            ),
        ),
        Offence(
            "cheating",
            "Cheating",
            "BNS s.318(2)",
            (
                _e("deception", "The accused deceived a person.", "BNS s.318(1)", "by deceiving any person"),
                _e("inducement", "Fraudulently or dishonestly induced that person to deliver or retain property, or intentionally induced an act or omission the person would not otherwise have done.", "BNS s.318(1)",
                   "fraudulently or dishonestly induces the person so deceived to deliver any property"),
                _e("damage_for_omission_limb", "Where it is an induced act or omission: it caused or was likely to cause damage or harm in body, mind, reputation or property.", "BNS s.318(1)",
                   "causes or is likely to cause damage or harm to that person in body, mind, reputation or property"),
            ),
            limits="s.318(3) and (4) carry higher punishment. Intention at the time of the transaction separates cheating from breach of contract: s.318(1), illustration (g).",
        ),
        Offence(
            "criminal_trespass",
            "Criminal trespass and house-trespass",
            "BNS s.329(3)",
            (
                _e("entry_or_remaining", "The accused entered property in another's possession, or having entered lawfully remained unlawfully.", "BNS s.329(1)",
                   "enters into or upon property in the possession of another"),
                _e("intent", "With intent to commit an offence, or to intimidate, insult or annoy the person in possession.", "BNS s.329(1)",
                   "with intent to commit an offence or to intimidate, insult or annoy"),
            ),
            limits="House-trespass under s.329(2) and (4) also requires a building, tent or vessel used as a dwelling, a place of worship, or a place for custody of property.",
        ),
        Offence(
            "criminal_intimidation",
            "Criminal intimidation",
            "BNS s.351(2)",
            (
                _e("threat", "The accused threatened injury to the person, reputation or property of the victim, or of someone in whom the victim is interested.", "BNS s.351(1)",
                   "threatens another by any means, with any injury to his person"),
                _e("intent", "With intent to cause alarm, or to make the victim do what the victim was not legally bound to do, or omit what the victim was legally entitled to do.", "BNS s.351(1)",
                   "with intent to cause alarm to that person"),
            ),
            limits="s.351(3) and (4) carry higher punishment for a threat of death or grievous hurt, or an anonymous threat.",
        ),
    )
}


def assess(offence: Offence, stored: dict[str, dict] | None) -> list[dict]:
    """Every element with what is on record for it.

    An element marked established with nothing behind it falls back to cannot be
    determined. The API refuses to store that, so this only catches a linked item
    that has since been entered in error.
    """
    known = stored or {}
    out = []
    for element in offence.elements:
        record = known.get(element.key) or {}
        evidence = list(record.get("evidence_item_ids") or [])
        witnesses = list(record.get("witness_ids") or [])
        state = record.get("state", ElementState.CANNOT_BE_DETERMINED.value)
        if state not in set(ElementState):
            state = ElementState.CANNOT_BE_DETERMINED.value
        if state == ElementState.ESTABLISHED.value and not (evidence or witnesses):
            state = ElementState.CANNOT_BE_DETERMINED.value
        out.append(
            {
                "key": element.key,
                "element": element.element,
                "provision": element.provision,
                "source_quote": element.source_quote,
                "state": state,
                "evidence_item_ids": evidence,
                "witness_ids": witnesses,
                "note": record.get("note") or "",
            }
        )
    return out


def overall_finding(elements: list[dict]) -> OverallFinding:
    states = {item["state"] for item in elements}
    if ElementState.NOT_ESTABLISHED.value in states:
        return OverallFinding.ELEMENT_NOT_ESTABLISHED
    if ElementState.CANNOT_BE_DETERMINED.value in states or not elements:
        return OverallFinding.CANNOT_BE_DETERMINED
    return OverallFinding.ALL_ELEMENTS_SUPPORTED
