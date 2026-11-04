"""The passage behind each duty and deadline the police tools assert.

The provision numbers elsewhere in the police services are written into code. This
pins each to a passage of the Act, so `tests/test_police_legal_sources.py` can read
the extracted text and fail if the passage is not there. It is what "checked against
the BNSS" means in practice.

Statute keys: BNSS, BNS, BSA, NDPS, POCSO.
"""

from __future__ import annotations

SOURCES: tuple[tuple[str, str, str], ...] = (
    # Deadlines
    ("BNSS", "s.58", "shall not, in the absence of a special order of a Magistrate under section 187, exceed"),
    ("BNSS", "s.78", "exclusive of the time necessary for the journey from the place of arrest to the Magistrate's Court"),
    ("BNSS", "s.187(2)", "for a term not exceeding fifteen days in the whole, or in parts, at any time during the initial forty days or sixty days"),
    ("BNSS", "s.187(3)(i)", "ninety days, where the investigation relates to an offence punishable with death, imprisonment for life or imprisonment for a term of ten years or more"),
    ("BNSS", "s.187(3)(ii)", "sixty days, where the investigation relates to any other offence"),
    ("BNSS", "s.173(3)", "prima facie case for proceeding in the matter within a period of fourteen days"),
    ("BNSS", "s.193(2)", "sections 64, 65, 66, 67, 68, 70, 71 of the Bharatiya Nyaya Sanhita, 2023 or under sections 4, 6, 8 or section 10"),
    ("BNSS", "s.193(3)(ii)", "the police officer shall, within a period of ninety days, inform the progress of the investigation"),
    ("BNSS", "s.184(1)", "within twenty-four hours from the time of receiving the information"),
    ("BNSS", "s.184(1) scope", "an offence of committing rape or attempt to commit rape is under investigation"),
    ("BNSS", "s.184(6)", "shall, within a period of seven days forward the report to the investigating officer"),
    ("BNSS", "s.184(7)", "rendering lawful any examination without the consent of the woman"),
    ("BNSS", "s.194(2)", "shall be forwarded to the District Magistrate or the Sub-divisional Magistrate within twenty-four hours"),
    ("BNSS", "s.196(6)", "within twenty-four hours of the death of a person, forward the body"),
    ("BNSS", "s.230", "the Magistrate shall without delay, and in no case beyond fourteen days"),
    # Arrest
    ("BNSS", "s.35(3)", "issue a notice directing the person against whom a reasonable complaint has been made"),
    ("BNSS", "s.35(4)", "it shall be the duty of that person to comply with the terms of the notice"),
    ("BNSS", "s.35(5)", "he shall not be arrested in respect of the offence referred to in the notice unless"),
    ("BNSS", "s.35(6)", "fails to comply with the terms of the notice or is unwilling to identify himself"),
    ("BNSS", "s.43(5)", "no woman shall be arrested after sunset and before sunrise"),
    ("BNSS", "s.47(2)", "he shall inform the person arrested that he is entitled to be released on bail"),
    ("BNSS", "s.48(2)", "shall inform the arrested person of his rights under sub-section (1) as soon as he is brought to the police station"),
    # Search and seizure
    ("BNSS", "s.94(1)", "officer may, by a written order, either in physical form or in electronic form, require the person"),
    ("BNSS", "s.94(2)", "shall be deemed to have complied with the requisition if he causes such document"),
    ("BNSS", "s.94(3)", "to apply to a letter, postcard, or other document or any parcel or thing in the custody of the postal authority"),
    ("BNSS", "s.103(1)", "on production of the warrant, allow him free ingress"),
    ("BNSS", "s.103(3)", "if such person is a woman, the search shall be made by another woman with strict regard to decency"),
    ("BNSS", "s.103(4)", "two or more independent and respectable inhabitants of the locality"),
    ("BNSS", "s.103(5)", "The search shall be made in their presence, and a list of all things seized"),
    ("BNSS", "s.103(6)", "shall, in every instance, be permitted to attend during the search"),
    ("BNSS", "s.103(7)", "a list of all things taken possession of shall be prepared"),
    ("BNSS", "s.105", "shall be recorded through any audio-video electronic means preferably mobile phone"),
    ("BNSS", "s.106(3)", "shall forthwith report the seizure to the Magistrate having jurisdiction"),
    ("BNSS", "s.185(1)", "after recording in writing the grounds of his belief in the case-diary"),
    ("BNSS", "s.185(2)", "shall, if practicable, conduct the search in person"),
    ("BNSS", "s.185(3)", "deliver to such subordinate officer an order in writing"),
    ("BNSS", "s.185(5)", "forthwith, but not later than forty-eight hours, be sent to the nearest Magistrate"),
    # Investigation
    ("BNSS", "s.179(1)", "shall be required to attend at any place other than the place in which such person resides"),
    ("BNSS", "s.180(3)", "shall be recorded, by a woman police officer or any woman officer"),
    ("BNSS", "s.187(1)", "if he is not below the rank of sub-inspector, shall forthwith transmit to the"),
    ("BNSS", "s.187(4)", "unless the accused is produced before him in person for the first time"),
    ("BNSS", "s.190(2)", "to execute a bond to appear before the Magistrate"),
    ("BNSS", "s.192(1)", "the time at which he began and closed his investigation, the place or places visited by him"),
    ("BNSS", "s.192(2)", "shall be inserted in the case diary"),
    ("BNSS", "s.192(3)", "shall be a volume and duly paginated"),
    ("BNSS", "s.193(3)(i)", "a report in the form as the State Government may, by rules, provide"),
    ("BNSS", "s.193(3)(i)(h)", "whether the report of medical examination of the woman has been attached"),
    ("BNSS", "s.193(3)(i)(i)", "the sequence of custody in case of electronic device"),
    ("BNSS", "s.193(8)", "copies of the police report along with other documents duly indexed"),
    ("BNSS", "s.193(6)(a)", "all documents or relevant extracts thereof on which the prosecution proposes to rely"),
    ("BNSS", "s.193(6)(b)", "the statements recorded under section 180 of all the persons whom the prosecution proposes to examine"),
    # Other Acts
    ("BSA", "s.63(4)", "a certificate doing any of the following things shall be submitted along with the electronic record"),
    ("NDPS", "s.36A(4)", "or section 24 or section 27A"),
    ("NDPS", "s.36A(4) extension", "said period up to one year"),
    ("POCSO", "s.27(1)", "The medical examination of a child in respect of whom any offence has been"),
)
