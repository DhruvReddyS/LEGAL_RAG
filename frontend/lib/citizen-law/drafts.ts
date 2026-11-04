/**
 * C-06: templates filled from the user's own facts, in the browser. The facts
 * never leave the device. A draft is always marked as a draft, an empty field
 * stays a visible blank rather than being invented, and it names only provisions
 * in provisions.json. Sources: BNSS s.173, RTI Act s.6 and Rules 2012 r.3,
 * Consumer Protection Act s.34, s.35, s.69 and the Department of Consumer
 * Affairs FAQ 40 (particulars of a complaint), NI Act s.138.
 *
 * The text of a draft is English: it is what goes to an office. Its labels and
 * guidance translate.
 */
import { l, type L } from "./law";

export type DraftField = { id: string; label: L; multiline?: boolean; type?: "date" };

export type DraftTemplate = {
  id: "police_complaint" | "rti" | "consumer" | "legal_notice" | "cheque_notice";
  title: L;
  blurb: L;
  cites: string[];
  guidance: L;
  fields: DraftField[];
  body: (value: (id: string) => string) => string;
};

const COMMON = {
  name: { id: "name", label: l("Your name", "आपका नाम", "మీ పేరు") },
  address: { id: "address", label: l("Your address for replies", "उत्तर के लिए आपका पता", "జవాబుల కోసం మీ చిరునామా"), multiline: true },
  phone: { id: "phone", label: l("Your phone or email", "आपका फ़ोन या ईमेल", "మీ ఫోన్ లేదా ఈమెయిల్") },
  place: { id: "place", label: l("Place", "स्थान", "స్థలం") },
};

export const DRAFT_TEMPLATES: DraftTemplate[] = [
  {
    id: "police_complaint",
    title: l("Complaint to the police", "पुलिस को शिकायत", "పోలీసులకు ఫిర్యాదు"),
    blurb: l("Information about an offence, for a police station", "थाने के लिए अपराध की सूचना", "పోలీస్ స్టేషన్ కోసం నేర సమాచారం"),
    cites: ["bnss-173-1", "bnss-173-2", "bnss-173-4"],
    guidance: l("Say what you saw and know. Do not guess who did it or name a section unless you are sure. Keep a copy, and ask for the free copy of what is recorded.", "जो देखा और जानते हैं वही लिखें। अनुमान न लगाएँ कि किसने किया, और निश्चित न हों तो धारा न लिखें। प्रति रखें और दर्ज सूचना की निःशुल्क प्रति माँगें।", "మీరు చూసినది, తెలిసినదే రాయండి. ఎవరు చేశారో ఊహించవద్దు, ఖచ్చితంగా తెలియకపోతే సెక్షన్ రాయవద్దు. ప్రతి ఉంచుకోండి, నమోదైనదాని ఉచిత ప్రతి అడగండి."),
    fields: [
      COMMON.name, COMMON.address, COMMON.phone,
      { id: "station", label: l("Police station", "थाना", "పోలీస్ స్టేషన్") },
      { id: "when", label: l("When it happened", "कब हुआ", "ఎప్పుడు జరిగింది") },
      { id: "where", label: l("Where it happened", "कहाँ हुआ", "ఎక్కడ జరిగింది") },
      { id: "what", label: l("What happened, in order", "क्या हुआ, क्रम से", "ఏం జరిగింది, క్రమంగా"), multiline: true },
      { id: "who", label: l("Who was involved, if known", "कौन शामिल था, यदि पता हो", "ఎవరు ఉన్నారు, తెలిస్తే"), multiline: true },
      { id: "evidence", label: l("What you have: documents, messages, witnesses", "आपके पास क्या है: दस्तावेज़, संदेश, गवाह", "మీ వద్ద ఏముంది: పత్రాలు, సందేశాలు, సాక్షులు"), multiline: true },
      COMMON.place,
    ],
    body: v => `To,
The Officer in Charge,
${v("station")} Police Station

Subject: Information about an offence

Sir or Madam,

I, ${v("name")}, of ${v("address")}, give this information under section 173 of the Bharatiya Nagarik Suraksha Sanhita, 2023.

When: ${v("when")}
Where: ${v("where")}

What happened:
${v("what")}

Persons involved, as far as known to me:
${v("who")}

What I have that may help:
${v("evidence")}

I ask that this information be recorded, and that a copy be given to me free of cost under section 173(2).

Contact: ${v("phone")}

Place: ${v("place")}
Date: ${v("date")}

Signature: ______________
${v("name")}`,
  },
  {
    id: "rti",
    title: l("RTI application", "RTI आवेदन", "RTI దరఖాస్తు"),
    blurb: l("A request for information from a public authority", "लोक प्राधिकरण से जानकारी का अनुरोध", "ప్రభుత్వ సంస్థ నుండి సమాచార అభ్యర్థన"),
    cites: ["rti-6-1", "rti-6-2", "rtir-3", "rti-7-1"],
    guidance: l("Ask for specific records with dates. You need not give a reason. The central rules ask for up to five hundred words and a fee of ten rupees; check your State's rules for a State office.", "तारीखों सहित विशिष्ट अभिलेख माँगें। कारण बताना ज़रूरी नहीं। केंद्रीय नियम पाँच सौ शब्द तक और दस रुपये शुल्क कहते हैं; राज्य कार्यालय के लिए राज्य के नियम देखें।", "తేదీలతో నిర్దిష్ట రికార్డులు అడగండి. కారణం చెప్పనక్కర్లేదు. కేంద్ర నియమాలు ఐదు వందల పదాల వరకు, పది రూపాయల రుసుము చెబుతాయి; రాష్ట్ర కార్యాలయానికి రాష్ట్ర నియమాలు చూడండి."),
    fields: [
      COMMON.name, COMMON.address,
      { id: "authority", label: l("Public authority (the office)", "लोक प्राधिकरण (दफ़्तर)", "ప్రభుత్వ సంస్థ (కార్యాలయం)") },
      { id: "information", label: l("The information you want, one point per line", "आपको चाहिए जानकारी, एक पंक्ति में एक बिंदु", "మీకు కావలసిన సమాచారం, ఒక్కో లైన్‌కు ఒక అంశం"), multiline: true },
      { id: "fee", label: l("How the fee is paid", "शुल्क कैसे दिया", "రుసుము ఎలా చెల్లించారు") },
      COMMON.place,
    ],
    body: v => `To,
The Public Information Officer,
${v("authority")}

Subject: Request for information under section 6(1) of the Right to Information Act, 2005

I request the following information:

${v("information")}

Fee: ${v("fee")}

I am a citizen of India. Please send the information to the address below.

Name: ${v("name")}
Address: ${v("address")}

Place: ${v("place")}
Date: ${v("date")}

Signature: ______________`,
  },
  {
    id: "consumer",
    title: l("Consumer complaint", "उपभोक्ता शिकायत", "వినియోగదారు ఫిర్యాదు"),
    blurb: l("To a District Consumer Commission", "ज़िला उपभोक्ता आयोग को", "జిల్లా వినియోగదారుల కమిషన్‌కు"),
    cites: ["cpa-35-1", "cpa-34-2", "cpa-69-1", "cpa-35-2"],
    guidance: l("The Commission may ask for its own form, copies and a fee. Attach bills and messages. Ask at the Commission or legal aid before filing.", "आयोग अपना प्रारूप, प्रतियाँ और शुल्क माँग सकता है। बिल और संदेश लगाएँ। दाखिल करने से पहले आयोग या विधिक सहायता से पूछें।", "కమిషన్ తన ఫారం, ప్రతులు, రుసుము అడగవచ్చు. బిల్లులు, సందేశాలు జత చేయండి. దాఖలు చేసే ముందు కమిషన్ లేదా న్యాయ సహాయాన్ని అడగండి."),
    fields: [
      COMMON.name, COMMON.address, COMMON.phone,
      { id: "district", label: l("District of the Commission", "आयोग का ज़िला", "కమిషన్ జిల్లా") },
      { id: "opposite", label: l("Name and address of the seller or provider", "विक्रेता या सेवा प्रदाता का नाम और पता", "అమ్మకందారు లేదా సేవా ప్రదాత పేరు, చిరునామా"), multiline: true },
      { id: "item", label: l("What you bought or hired", "आपने क्या ख़रीदा या लिया", "మీరు ఏం కొన్నారు లేదా తీసుకున్నారు") },
      { id: "bought", label: l("When and where", "कब और कहाँ", "ఎప్పుడు, ఎక్కడ") },
      { id: "paid", label: l("Amount paid", "भुगतान की राशि", "చెల్లించిన మొత్తం") },
      { id: "problem", label: l("What went wrong, and when you found out", "क्या ग़लत हुआ, और कब पता चला", "ఏం తప్పు జరిగింది, ఎప్పుడు తెలిసింది"), multiline: true },
      { id: "tried", label: l("What you did about it and what they said", "आपने क्या किया और उन्होंने क्या कहा", "మీరు ఏం చేశారు, వారు ఏం చెప్పారు"), multiline: true },
      { id: "relief", label: l("What you are asking for", "आप क्या माँग रहे हैं", "మీరు ఏం అడుగుతున్నారు"), multiline: true },
      { id: "documents", label: l("Documents you are attaching", "संलग्न दस्तावेज़", "జత చేస్తున్న పత్రాలు"), multiline: true },
      COMMON.place,
    ],
    body: v => `Before the District Consumer Disputes Redressal Commission, ${v("district")}

Complainant:
${v("name")}
${v("address")}
${v("phone")}

Versus

Opposite party:
${v("opposite")}

Complaint under section 35 of the Consumer Protection Act, 2019

1. I bought or hired the following for my own use, not for resale or a commercial purpose: ${v("item")}.
2. When and where: ${v("bought")}. Amount paid: ${v("paid")}.
3. What went wrong:
${v("problem")}
4. What I did and the response:
${v("tried")}
5. This Commission may hear this complaint under section 34(2) of the Act because: [say where the opposite party is, where the cause of action arose, or where you live or work].
6. This complaint is filed within two years of the cause of action, as section 69 requires. [Check this date. If it is late, say why.]
7. I ask for:
${v("relief")}

Documents attached:
${v("documents")}

Place: ${v("place")}
Date: ${v("date")}

Signature: ______________
${v("name")}`,
  },
  {
    id: "legal_notice",
    title: l("Legal notice (letter of demand)", "क़ानूनी नोटिस (माँग पत्र)", "లీగల్ నోటీసు (డిమాండ్ లేఖ)"),
    blurb: l("A written demand before you take the matter further", "आगे बढ़ने से पहले लिखित माँग", "ముందుకు వెళ్లే ముందు రాతపూర్వక డిమాండ్"),
    cites: [],
    guidance: l("This is a plain letter, not a statutory form. Do not count on it to change any time limit: check your date in the forum tool. Consider showing it to legal aid before sending.", "यह साधारण पत्र है, कोई वैधानिक प्रपत्र नहीं। समय-सीमा बदलने के लिए इस पर भरोसा न करें: फ़ोरम उपकरण में अपनी तारीख देखें। भेजने से पहले विधिक सहायता को दिखाने पर विचार करें।", "ఇది సాధారణ లేఖ, చట్టబద్ధ ఫారం కాదు. గడువు మార్చడానికి దీనిపై ఆధారపడవద్దు: ఫోరం సాధనంలో మీ తేదీ చూడండి. పంపే ముందు న్యాయ సహాయానికి చూపించండి."),
    fields: [
      COMMON.name, COMMON.address,
      { id: "to", label: l("Who it is to, with address", "किसे, पते सहित", "ఎవరికి, చిరునామాతో"), multiline: true },
      { id: "facts", label: l("The facts, in order", "तथ्य, क्रम से", "వాస్తవాలు, క్రమంగా"), multiline: true },
      { id: "demand", label: l("What you ask them to do", "आप उनसे क्या करने को कहते हैं", "వారిని ఏం చేయమంటున్నారు"), multiline: true },
      { id: "days", label: l("How many days you give", "आप कितने दिन देते हैं", "ఎన్ని రోజులు ఇస్తున్నారు") },
      COMMON.place,
    ],
    body: v => `To,
${v("to")}

Subject: Notice and demand

I, ${v("name")}, of ${v("address")}, write to you as follows.

${v("facts")}

I ask you to: ${v("demand")}

Please do this within ${v("days")} days of receiving this letter. If you do not, I will consider the steps open to me under the law. I reserve my rights.

Place: ${v("place")}
Date: ${v("date")}

Signature: ______________
${v("name")}`,
  },
  {
    id: "cheque_notice",
    title: l("Cheque bounce notice", "चेक बाउंस नोटिस", "చెక్ బౌన్స్ నోటీసు"),
    blurb: l("The demand section 138 requires", "धारा 138 की आवश्यक माँग", "సెక్షన్ 138 కోరే డిమాండ్"),
    cites: ["ni-138-b", "ni-138-c", "ni-142-b"],
    guidance: l("It must reach them in time: within thirty days of the bank telling you. Send it in a way you can prove, and keep the proof. Check the dates in the forum tool.", "यह समय पर पहुँचना चाहिए: बैंक की सूचना के तीस दिनों में। ऐसे भेजें जिसे सिद्ध कर सकें, और प्रमाण रखें। तारीखें फ़ोरम उपकरण में देखें।", "ఇది సమయానికి చేరాలి: బ్యాంకు చెప్పిన ముప్పై రోజుల్లో. రుజువు చేయగలిగే విధంగా పంపండి, రుజువు ఉంచుకోండి. తేదీలు ఫోరం సాధనంలో చూడండి."),
    fields: [
      COMMON.name, COMMON.address,
      { id: "drawer", label: l("Name and address of the person who gave the cheque", "चेक देने वाले का नाम और पता", "చెక్ ఇచ్చినవారి పేరు, చిరునామా"), multiline: true },
      { id: "cheque", label: l("Cheque number and date", "चेक संख्या और तारीख", "చెక్ నంబర్, తేదీ") },
      { id: "bank", label: l("Bank and branch of that cheque", "उस चेक का बैंक और शाखा", "ఆ చెక్ బ్యాంకు, బ్రాంచ్") },
      { id: "amount", label: l("Amount", "राशि", "మొత్తం") },
      { id: "for", label: l("What the cheque was for", "चेक किसलिए था", "చెక్ దేని కోసం") },
      { id: "returned", label: l("When the bank told you, and the reason on the memo", "बैंक ने कब बताया, और मेमो पर कारण", "బ్యాంకు ఎప్పుడు చెప్పింది, మెమోలో కారణం") },
      COMMON.place,
    ],
    body: v => `To,
${v("drawer")}

Subject: Notice under section 138 of the Negotiable Instruments Act, 1881

You gave me cheque ${v("cheque")} drawn on ${v("bank")} for ${v("amount")}, for: ${v("for")}.

The cheque was returned unpaid. The bank informed me on the following date and for the following reason: ${v("returned")}.

I demand payment of ${v("amount")} within fifteen days of your receipt of this notice.

Name: ${v("name")}
Address: ${v("address")}

Place: ${v("place")}
Date: ${v("date")}

Signature: ______________`,
  },
];

export const DRAFT_MARK = "DRAFT. Check every fact. Not filed anywhere. Prepared with Corpusil from what you typed: legal information, not legal advice.";

export type RenderedDraft = { text: string; blanks: string[]; complete: boolean };

/**
 * Fill the template. A field left empty becomes a visible [BLANK: label], never
 * invented text, and is listed in `blanks` so it can be asked for.
 */
export function renderDraft(template: DraftTemplate, values: Record<string, string>): RenderedDraft {
  const blanks: string[] = [];
  const label = (id: string) => template.fields.find(field => field.id === id)?.label.en ?? id;
  const value = (id: string): string => {
    const given = (values[id] ?? "").trim();
    if (given) return given;
    if (id === "date") return "____________";
    if (!blanks.includes(id)) blanks.push(id);
    return `[BLANK: ${label(id)}]`;
  };
  const text = `${DRAFT_MARK}\n\n${template.body(value)}\n\n${DRAFT_MARK}\n`;
  return { text, blanks, complete: blanks.length === 0 };
}

const REPEALED_PATTERNS: { pattern: RegExp; warning: L; cite: string }[] = [
  {
    pattern: /\b(ipc|i\.p\.c\.?|indian penal code)\b/i,
    cite: "bns-358",
    warning: l("You mention the Indian Penal Code. It has been repealed by the Bharatiya Nyaya Sanhita, 2023. Check the current section, or leave the section out.", "आपने भारतीय दंड संहिता लिखी है। इसे भारतीय न्याय संहिता, 2023 ने निरस्त कर दिया है। वर्तमान धारा जाँचें, या धारा न लिखें।", "మీరు ఇండియన్ పీనల్ కోడ్ ప్రస్తావించారు. భారతీయ న్యాయ సంహిత, 2023 దీన్ని రద్దు చేసింది. ప్రస్తుత సెక్షన్ చూసుకోండి, లేదా సెక్షన్ రాయవద్దు."),
  },
  {
    pattern: /\b(cr\.?\s?p\.?\s?c\.?|code of criminal procedure)\b/i,
    cite: "bnss-531",
    warning: l("You mention the Code of Criminal Procedure. It has been repealed by the BNSS, 2023. Check the current section, or leave the section out.", "आपने दंड प्रक्रिया संहिता लिखी है। इसे BNSS, 2023 ने निरस्त कर दिया है। वर्तमान धारा जाँचें, या धारा न लिखें।", "మీరు క్రిమినల్ ప్రొసీజర్ కోడ్ ప్రస్తావించారు. BNSS, 2023 దీన్ని రద్దు చేసింది. ప్రస్తుత సెక్షన్ చూసుకోండి, లేదా సెక్షన్ రాయవద్దు."),
  },
];

export function repealWarnings(text: string): { warning: L; cite: string }[] {
  return REPEALED_PATTERNS.filter(item => item.pattern.test(text)).map(({ warning, cite }) => ({ warning, cite }));
}
