/**
 * C-05: where to go, by when, and what it costs. A wrong limitation period loses
 * a case, so this is a fixed table and it abstains readily.
 *
 * Rules of the table:
 * - A period appears only if its provision is in provisions.json, quoted from
 *   the corpus. The Limitation Act 1963, Consumer Protection Act 2019,
 *   Negotiable Instruments Act 1881, RTI Act 2005, the Workplace Harassment Act
 *   2013 and the BNSS are the sources.
 * - Fees are stated only where a rule gives a figure. Nothing else is guessed:
 *   court fees vary by state and the corpus holds no consumer fee rules.
 * - Any answer of "not sure" abstains. So does anything outside the table.
 */
import { l, type L } from "./law";

export type Answer = "yes" | "no" | "unsure";

export type GateQuestion = {
  id: string;
  text: L;
  /** The answer that keeps the person on this route. Anything else abstains. */
  proceedOn: "yes" | "no";
  abstainReason: L;
  cites?: string[];
};

export type DeadlineRule = {
  id: string;
  label: L;
  /** What the person enters: the date this period runs from. */
  fromLabel: L;
  add: { days?: number; months?: number; years?: number };
  /** Added after `add`. The cheque complaint period runs from the end of the 15 days. */
  thenAdd?: { months?: number };
  cites: string[];
  extensionNote?: L;
  extensionCites?: string[];
};

export type Situation = {
  id: string;
  title: L;
  blurb: L;
  questions: GateQuestion[];
  /** Set when the table can say what the law is but cannot route. Always abstains. */
  alwaysAbstain?: L;
  forum: L;
  forumCites: string[];
  rules: DeadlineRule[];
  noPeriod?: L;
  noPeriodCites?: string[];
  cost: L;
  costCites: string[];
  notes: { text: L; cites: string[] }[];
};

const FEE_UNKNOWN = l(
  "Our sources do not state the fee for this, and it can vary by state. Ask the office where you file, or legal aid.",
  "हमारे स्रोतों में इसका शुल्क नहीं है, और यह राज्य के अनुसार बदल सकता है। जहाँ दाखिल करें वहाँ या विधिक सहायता से पूछें।",
  "మా మూలాల్లో దీని రుసుము లేదు, రాష్ట్రాన్ని బట్టి మారవచ్చు. దాఖలు చేసే కార్యాలయంలో లేదా న్యాయ సహాయాన్ని అడగండి.",
);

export const SITUATIONS: Situation[] = [
  {
    id: "consumer",
    title: l("A faulty product or poor service I paid for", "ख़राब सामान या सेवा जिसका भुगतान किया", "డబ్బు చెల్లించిన లోపభూయిష్ట వస్తువు లేదా సేవ"),
    blurb: l("Consumer Commission complaints", "उपभोक्ता आयोग में शिकायत", "వినియోగదారుల కమిషన్ ఫిర్యాదులు"),
    questions: [
      {
        id: "own-use",
        text: l("Did you buy this for your own use, not for resale or a commercial purpose?", "क्या आपने इसे अपने उपयोग के लिए लिया, पुनर्विक्रय या व्यावसायिक उद्देश्य से नहीं?", "దీన్ని మీ స్వంత ఉపయోగం కోసం కొన్నారా, తిరిగి అమ్మడానికి లేదా వాణిజ్య ప్రయోజనం కోసం కాదా?"),
        proceedOn: "yes",
        abstainReason: l("The Act's definition of consumer leaves out purchases for resale or a commercial purpose, with an exception we cannot apply for you. Ask legal aid.", "अधिनियम की उपभोक्ता परिभाषा में पुनर्विक्रय या व्यावसायिक ख़रीद शामिल नहीं, एक अपवाद के साथ जिसे हम आपके लिए लागू नहीं कर सकते। विधिक सहायता से पूछें।", "చట్టంలోని వినియోగదారు నిర్వచనం తిరిగి అమ్మకం లేదా వాణిజ్య కొనుగోళ్లను వదిలేస్తుంది, ఒక మినహాయింపుతో, దాన్ని మేము మీకు వర్తింపజేయలేము. న్యాయ సహాయాన్ని అడగండి."),
        cites: ["cpa-2-7"],
      },
    ],
    forum: l("The District Consumer Commission where the other party is, where the problem arose, or where you live or work. The Act sets the District Commission's limit at one crore rupees of consideration paid, but the Government may prescribe a different value, and we could not confirm the current figure from our sources. Ask the Commission before filing if the amount is large. You may file electronically, and the Government's FAQs say you do not need an advocate.", "ज़िला उपभोक्ता आयोग, जहाँ दूसरा पक्ष है, जहाँ समस्या हुई, या जहाँ आप रहते या काम करते हैं। अधिनियम में ज़िला आयोग की सीमा एक करोड़ रुपये के भुगतान तक है, पर सरकार दूसरा मूल्य तय कर सकती है, और हम अपने स्रोतों से वर्तमान आँकड़े की पुष्टि नहीं कर सके। राशि बड़ी हो तो दाखिल करने से पहले आयोग से पूछें। आप इलेक्ट्रॉनिक रूप से दाखिल कर सकते हैं, और सरकारी FAQ के अनुसार वकील ज़रूरी नहीं।", "ఇతర పక్షం ఉన్న చోట, సమస్య వచ్చిన చోట, లేదా మీరు నివసించే లేదా పనిచేసే చోట జిల్లా వినియోగదారుల కమిషన్. చట్టంలో జిల్లా కమిషన్ పరిమితి చెల్లించిన మొత్తం ఒక కోటి రూపాయల వరకు, కానీ ప్రభుత్వం వేరే విలువ నిర్ణయించవచ్చు, ప్రస్తుత సంఖ్యను మా మూలాల నుండి నిర్ధారించలేకపోయాం. మొత్తం పెద్దదైతే దాఖలు చేసే ముందు కమిషన్‌ను అడగండి. ఎలక్ట్రానిక్‌గా దాఖలు చేయవచ్చు, ప్రభుత్వ FAQ ప్రకారం న్యాయవాది అవసరం లేదు."),
    forumCites: ["cpa-34-2", "cpa-34-1", "cpa-34-1-p", "cpa-35-1", "cpafaq-adv"],
    rules: [
      {
        id: "consumer-complaint",
        label: l("File the complaint", "शिकायत दाखिल करें", "ఫిర్యాదు దాఖలు చేయండి"),
        fromLabel: l("The date the problem arose (cause of action)", "समस्या उत्पन्न होने की तारीख (वाद-कारण)", "సమస్య వచ్చిన తేదీ (వాద కారణం)"),
        add: { years: 2 },
        cites: ["cpa-69-1"],
        extensionNote: l("A late complaint can be heard only if the Commission accepts sufficient cause and records its reasons.", "देर से की गई शिकायत तभी सुनी जा सकती है जब आयोग पर्याप्त कारण माने और कारण दर्ज करे।", "ఆలస్యమైన ఫిర్యాదును కమిషన్ తగిన కారణం అంగీకరించి నమోదు చేస్తేనే వింటుంది."),
        extensionCites: ["cpa-69-2"],
      },
      {
        id: "consumer-appeal",
        label: l("Appeal a District Commission order", "ज़िला आयोग के आदेश की अपील", "జిల్లా కమిషన్ ఉత్తర్వుపై అప్పీలు"),
        fromLabel: l("The date of the order", "आदेश की तारीख", "ఉత్తర్వు తేదీ"),
        add: { days: 45 },
        cites: ["cpa-41"],
      },
    ],
    cost: l("A fee is prescribed, but our sources do not hold the current figure. Ask the Commission.", "शुल्क निर्धारित है, पर हमारे स्रोतों में वर्तमान राशि नहीं है। आयोग से पूछें।", "రుసుము నిర్ణయించబడింది, కానీ ప్రస్తుత మొత్తం మా మూలాల్లో లేదు. కమిషన్‌ను అడగండి."),
    costCites: ["cpa-35-2"],
    notes: [],
  },
  {
    id: "cheque",
    title: l("A cheque given to me bounced", "मुझे दिया गया चेक बाउंस हुआ", "నాకు ఇచ్చిన చెక్ బౌన్స్ అయింది"),
    blurb: l("Negotiable Instruments Act, section 138", "परक्राम्य लिखत अधिनियम, धारा 138", "నెగోషియబుల్ ఇన్‌స్ట్రుమెంట్స్ చట్టం, సెక్షన్ 138"),
    questions: [
      {
        id: "debt",
        text: l("Was the cheque given to pay a debt or other liability that is legally enforceable?", "क्या चेक किसी क़ानूनन वसूली योग्य ऋण या दायित्व के भुगतान के लिए दिया गया था?", "చట్టప్రకారం వసూలు చేయగల అప్పు లేదా బాధ్యత చెల్లించడానికి చెక్ ఇచ్చారా?"),
        proceedOn: "yes",
        abstainReason: l("Section 138 applies only to a cheque for a debt or other liability. Ask legal aid about your position.", "धारा 138 केवल ऋण या दायित्व के चेक पर लागू है। अपनी स्थिति के बारे में विधिक सहायता से पूछें।", "సెక్షన్ 138 అప్పు లేదా బాధ్యత కోసం ఇచ్చిన చెక్‌కే వర్తిస్తుంది. మీ పరిస్థితి గురించి న్యాయ సహాయాన్ని అడగండి."),
        cites: ["ni-138"],
      },
      {
        id: "reason",
        text: l("Did the bank return it because of insufficient funds, or because it exceeded the arrangement?", "क्या बैंक ने इसे अपर्याप्त राशि या व्यवस्था से अधिक होने के कारण लौटाया?", "తగిన నిధులు లేక లేదా ఏర్పాటు మించినందున బ్యాంకు దీన్ని తిరిగి ఇచ్చిందా?"),
        proceedOn: "yes",
        abstainReason: l("The section names those two reasons. Other return reasons need a person's view of the facts and of case law we do not hold.", "धारा इन दो कारणों का उल्लेख करती है। अन्य कारणों के लिए किसी व्यक्ति की राय चाहिए, और ऐसे निर्णय जो हमारे पास नहीं हैं।", "సెక్షన్ ఈ రెండు కారణాలను చెబుతుంది. ఇతర కారణాలకు ఒక వ్యక్తి అభిప్రాయం, మా వద్ద లేని తీర్పులు కావాలి."),
        cites: ["ni-138"],
      },
      {
        id: "in-time",
        text: l("Was it presented to the bank within six months of its date, or within its validity if that is earlier?", "क्या इसे तारीख से छह महीने में, या उससे पहले वैधता में, बैंक में प्रस्तुत किया गया?", "తేదీ నుండి ఆరు నెలల్లో, లేదా అంతకంటే ముందు చెల్లుబాటులో, బ్యాంకులో సమర్పించారా?"),
        proceedOn: "yes",
        abstainReason: l("The section does not apply unless the cheque was presented in that time. Ask legal aid what else may be open to you.", "उस समय में प्रस्तुत न होने पर धारा लागू नहीं होती। विधिक सहायता से पूछें कि और क्या रास्ता हो सकता है।", "ఆ సమయంలో సమర్పించకపోతే సెక్షన్ వర్తించదు. ఇంకేం మార్గాలు ఉన్నాయో న్యాయ సహాయాన్ని అడగండి."),
        cites: ["ni-138-a"],
      },
    ],
    forum: l("A written complaint to a Metropolitan Magistrate or Judicial Magistrate of the first class. If you deposited the cheque through your account, the court is where your branch is. The section's wording still refers to the Code of Criminal Procedure 1973, which the BNSS has repealed.", "महानगर मजिस्ट्रेट या प्रथम श्रेणी न्यायिक मजिस्ट्रेट को लिखित शिकायत। यदि चेक अपने खाते से जमा किया, तो अदालत वह है जहाँ आपकी शाखा है। धारा के शब्द अब भी दंड प्रक्रिया संहिता 1973 का उल्लेख करते हैं, जिसे BNSS ने निरस्त कर दिया है।", "మెట్రోపాలిటన్ మేజిస్ట్రేట్ లేదా ఫస్ట్ క్లాస్ జ్యుడీషియల్ మేజిస్ట్రేట్‌కు రాతపూర్వక ఫిర్యాదు. చెక్‌ను మీ ఖాతా ద్వారా వేస్తే, మీ బ్రాంచ్ ఉన్న చోటి కోర్టు. సెక్షన్ మాటలు ఇంకా క్రిమినల్ ప్రొసీజర్ కోడ్ 1973ను ప్రస్తావిస్తాయి, దాన్ని BNSS రద్దు చేసింది."),
    forumCites: ["ni-142-c", "ni-142-2", "bnss-531"],
    rules: [
      {
        id: "cheque-notice",
        label: l("Send the written demand notice", "लिखित माँग नोटिस भेजें", "రాతపూర్వక డిమాండ్ నోటీసు పంపండి"),
        fromLabel: l("The date the bank told you the cheque was returned", "बैंक ने चेक लौटने की सूचना दी उस तारीख", "చెక్ తిరిగి వచ్చిందని బ్యాంకు చెప్పిన తేదీ"),
        add: { days: 30 },
        cites: ["ni-138-b"],
      },
      {
        id: "cheque-complaint",
        label: l("File the complaint", "शिकायत दाखिल करें", "ఫిర్యాదు దాఖలు చేయండి"),
        fromLabel: l("The date the drawer received your notice", "चेक देने वाले को आपका नोटिस मिलने की तारीख", "చెక్ ఇచ్చినవారికి మీ నోటీసు అందిన తేదీ"),
        add: { days: 15 },
        thenAdd: { months: 1 },
        cites: ["ni-138-c", "ni-142-b"],
        extensionNote: l("They have fifteen days to pay; the one month runs after that. Do not file before those fifteen days end. A late complaint needs sufficient cause.", "उनके पास भुगतान के लिए पंद्रह दिन हैं; एक महीना उसके बाद चलता है। पंद्रह दिन पूरे होने से पहले दाखिल न करें। देर के लिए पर्याप्त कारण चाहिए।", "చెల్లించడానికి వారికి పదిహేను రోజులు; ఒక నెల ఆ తర్వాత మొదలవుతుంది. పదిహేను రోజులు ముగియకముందు దాఖలు చేయవద్దు. ఆలస్యానికి తగిన కారణం కావాలి."),
        extensionCites: ["ni-142-p"],
      },
    ],
    cost: FEE_UNKNOWN,
    costCites: [],
    notes: [],
  },
  {
    id: "money",
    title: l("Someone owes me money or broke a contract", "कोई मेरा पैसा नहीं दे रहा या अनुबंध तोड़ा", "ఎవరో నా డబ్బు ఇవ్వడం లేదు లేదా ఒప్పందం ఉల్లంఘించారు"),
    blurb: l("Civil suits under the Limitation Act", "परिसीमा अधिनियम के तहत दीवानी वाद", "పరిమితి చట్టం కింద సివిల్ దావాలు"),
    questions: [
      {
        id: "no-arbitration",
        text: l("Is it true that your agreement has no arbitration clause?", "क्या यह सही है कि आपके अनुबंध में मध्यस्थता का खंड नहीं है?", "మీ ఒప్పందంలో మధ్యవర్తిత్వ నిబంధన లేదు అన్నది నిజమేనా?"),
        proceedOn: "yes",
        abstainReason: l("An arbitration clause can change where this goes. A lawyer or legal aid needs to read the agreement.", "मध्यस्थता खंड से रास्ता बदल सकता है। वकील या विधिक सहायता को अनुबंध पढ़ना होगा।", "మధ్యవర్తిత్వ నిబంధన మార్గాన్ని మార్చవచ్చు. న్యాయవాది లేదా న్యాయ సహాయం ఒప్పందం చదవాలి."),
      },
      {
        id: "not-business",
        text: l("Is this a personal matter, not a dispute between businesses?", "क्या यह निजी मामला है, व्यवसायों के बीच विवाद नहीं?", "ఇది వ్యక్తిగత విషయమా, వ్యాపారాల మధ్య వివాదం కాదా?"),
        proceedOn: "yes",
        abstainReason: l("Commercial disputes can go to a different court under a different procedure. Please ask a person.", "वाणिज्यिक विवाद अलग अदालत और प्रक्रिया में जा सकते हैं। कृपया किसी व्यक्ति से पूछें।", "వాణిజ్య వివాదాలు వేరే కోర్టు, ప్రక్రియకు వెళ్లవచ్చు. దయచేసి ఒక వ్యక్తిని అడగండి."),
      },
    ],
    forum: l("A civil suit in the lowest-grade court competent to try it, where the defendant lives or works or where the cause of action arose. Which court that is depends on the amount and your state, so ask at the court or legal aid.", "सबसे निचले सक्षम दर्जे की अदालत में दीवानी वाद, जहाँ प्रतिवादी रहता या काम करता है या जहाँ वाद-कारण उत्पन्न हुआ। कौन सी अदालत, यह राशि और राज्य पर निर्भर है, इसलिए अदालत या विधिक सहायता से पूछें।", "సమర్థమైన అత్యల్ప స్థాయి కోర్టులో సివిల్ దావా, ప్రతివాది నివసించే లేదా పనిచేసే చోట లేదా వాద కారణం వచ్చిన చోట. ఏ కోర్టు అనేది మొత్తం, రాష్ట్రంపై ఆధారపడుతుంది, కాబట్టి కోర్టులో లేదా న్యాయ సహాయాన్ని అడగండి."),
    forumCites: ["cpc-15", "cpc-20"],
    rules: [
      {
        id: "breach",
        label: l("Sue for breach of contract", "अनुबंध उल्लंघन का वाद", "ఒప్పంద ఉల్లంఘన దావా"),
        fromLabel: l("The date the contract was broken", "अनुबंध टूटने की तारीख", "ఒప్పందం ఉల్లంఘించిన తేదీ"),
        add: { years: 3 },
        cites: ["lim-a55", "lim-12"],
      },
      {
        id: "loan",
        label: l("Sue for money lent", "दिए गए ऋण का वाद", "అప్పు ఇచ్చిన డబ్బు దావా"),
        fromLabel: l("The date the loan was made", "ऋण दिए जाने की तारीख", "అప్పు ఇచ్చిన తేదీ"),
        add: { years: 3 },
        cites: ["lim-a19", "lim-12"],
      },
    ],
    cost: FEE_UNKNOWN,
    costCites: [],
    notes: [
      { cites: ["lim-3"], text: l("A suit filed after the period is dismissed, even if the other side does not raise it.", "अवधि के बाद दायर वाद ख़ारिज हो जाता है, चाहे दूसरा पक्ष यह न उठाए।", "గడువు తర్వాత వేసిన దావా కొట్టివేయబడుతుంది, ఇతర పక్షం లేవనెత్తకపోయినా.") },
      { cites: ["lim-5"], text: l("The section that lets a court accept lateness for sufficient cause speaks of appeals and applications, not suits.", "पर्याप्त कारण पर देरी स्वीकारने वाली धारा अपीलों और आवेदनों की बात करती है, वादों की नहीं।", "తగిన కారణంతో ఆలస్యాన్ని అంగీకరించే సెక్షన్ అప్పీళ్లు, దరఖాస్తుల గురించి చెబుతుంది, దావాల గురించి కాదు.") },
      { cites: ["lim-17"], text: l("Where fraud or mistake is involved, time can start later. That needs a lawyer's view.", "धोखाधड़ी या भूल में समय बाद में शुरू हो सकता है। इसके लिए वकील की राय चाहिए।", "మోసం లేదా పొరపాటు ఉంటే సమయం తర్వాత మొదలుకావచ్చు. దీనికి న్యాయవాది అభిప్రాయం కావాలి.") },
      { cites: ["lim-a113"], text: l("A suit no other article covers has three years from when the right to sue accrues. Which article fits your facts is a question for a person.", "जिस वाद पर कोई और अनुच्छेद लागू न हो, उसके लिए वाद का अधिकार बनने से तीन वर्ष हैं। आपके तथ्यों पर कौन सा लागू है, यह किसी व्यक्ति से पूछें।", "వేరే ఆర్టికల్ వర్తించని దావాకు దావా హక్కు వచ్చినప్పటి నుండి మూడేళ్లు. మీ వాస్తవాలకు ఏది వర్తిస్తుందో ఒక వ్యక్తిని అడగండి.") },
    ],
  },
  {
    id: "rti",
    title: l("I want information from a government office", "मुझे सरकारी दफ़्तर से जानकारी चाहिए", "ప్రభుత్వ కార్యాలయం నుండి సమాచారం కావాలి"),
    blurb: l("Right to Information Act", "सूचना का अधिकार अधिनियम", "సమాచార హక్కు చట్టం"),
    questions: [],
    forum: l("A written or electronic request to the Public Information Officer of that public authority, in English, Hindi or the official language of the area. You do not have to give a reason.", "उस लोक प्राधिकरण के लोक सूचना अधिकारी को लिखित या इलेक्ट्रॉनिक अनुरोध, अंग्रेज़ी, हिंदी या क्षेत्र की राजभाषा में। कारण बताना ज़रूरी नहीं।", "ఆ ప్రభుత్వ సంస్థ ప్రజా సమాచార అధికారికి రాతపూర్వక లేదా ఎలక్ట్రానిక్ అభ్యర్థన, ఇంగ్లీష్, హిందీ లేదా ప్రాంత అధికార భాషలో. కారణం చెప్పనక్కర్లేదు."),
    forumCites: ["rti-6-1", "rti-6-2"],
    rules: [
      {
        id: "rti-reply",
        label: l("The office must reply by", "दफ़्तर को उत्तर देना है", "కార్యాలయం జవాబివ్వాలి"),
        fromLabel: l("The date they received your request", "उन्हें आपका अनुरोध मिलने की तारीख", "వారికి మీ అభ్యర్థన అందిన తేదీ"),
        add: { days: 30 },
        cites: ["rti-7-1"],
        extensionNote: l("If it concerns someone's life or liberty, the period is forty-eight hours.", "यदि यह किसी के जीवन या स्वतंत्रता से जुड़ा है, तो अवधि अड़तालीस घंटे है।", "ఎవరి ప్రాణం లేదా స్వేచ్ఛకు సంబంధించినదైతే, గడువు నలభై ఎనిమిది గంటలు."),
        extensionCites: ["rti-7-1-p"],
      },
      {
        id: "rti-first-appeal",
        label: l("First appeal", "प्रथम अपील", "మొదటి అప్పీలు"),
        fromLabel: l("The date you got the decision, or the day the reply period ended", "निर्णय मिलने की तारीख, या उत्तर की अवधि समाप्त होने का दिन", "నిర్ణయం అందిన తేదీ, లేదా జవాబు గడువు ముగిసిన రోజు"),
        add: { days: 30 },
        cites: ["rti-19-1"],
      },
      {
        id: "rti-second-appeal",
        label: l("Second appeal to the Information Commission", "सूचना आयोग में द्वितीय अपील", "సమాచార కమిషన్‌కు రెండవ అప్పీలు"),
        fromLabel: l("The date the first appeal decision was made or received", "प्रथम अपील का निर्णय होने या मिलने की तारीख", "మొదటి అప్పీలు నిర్ణయం వచ్చిన లేదా అందిన తేదీ"),
        add: { days: 90 },
        cites: ["rti-19-3"],
      },
    ],
    cost: l("Ten rupees for an application under the central Rules of 2012. State rules can differ, and we do not hold them all. No fee for people below the poverty line, and information is free if the office misses the time limit.", "2012 के केंद्रीय नियमों के तहत आवेदन पर दस रुपये। राज्य नियम अलग हो सकते हैं, और वे सब हमारे पास नहीं हैं। ग़रीबी रेखा से नीचे वालों से शुल्क नहीं, और दफ़्तर समय चूके तो जानकारी निःशुल्क।", "2012 కేంద్ర నియమాల కింద దరఖాస్తుకు పది రూపాయలు. రాష్ట్ర నియమాలు వేరుగా ఉండవచ్చు, అవన్నీ మా వద్ద లేవు. దారిద్య్ర రేఖకు దిగువన ఉన్నవారికి రుసుము లేదు, కార్యాలయం గడువు దాటితే సమాచారం ఉచితం."),
    costCites: ["rtir-3", "rti-7-5", "rti-7-6"],
    notes: [],
  },
  {
    id: "domestic-violence",
    title: l("Violence or abuse at home", "घर पर हिंसा या दुर्व्यवहार", "ఇంట్లో హింస లేదా వేధింపులు"),
    blurb: l("Protection of Women from Domestic Violence Act", "घरेलू हिंसा से महिलाओं का संरक्षण अधिनियम", "గృహ హింస నుండి మహిళల రక్షణ చట్టం"),
    questions: [
      {
        id: "safe-now",
        text: l("Are you safe right now?", "क्या आप अभी सुरक्षित हैं?", "మీరు ఇప్పుడు సురక్షితంగా ఉన్నారా?"),
        proceedOn: "yes",
        abstainReason: l("Your safety comes first. Call 112 now. When you can, call 15100 for legal help.", "आपकी सुरक्षा पहले है। अभी 112 पर कॉल करें। जब हो सके, क़ानूनी मदद के लिए 15100 पर कॉल करें।", "మీ భద్రతే ముందు. ఇప్పుడే 112కు కాల్ చేయండి. వీలైనప్పుడు న్యాయ సహాయం కోసం 15100కు కాల్ చేయండి."),
        cites: ["helpline-112", "nalsa-15100"],
      },
    ],
    forum: l("Anyone can inform the Protection Officer. An application for protection, residence, money, custody or compensation orders goes to the Judicial Magistrate of the first class or Metropolitan Magistrate where you live, even temporarily, or work, where the other person lives or works, or where it happened. A police complaint can also be made: cruelty by a husband or his relatives is an offence under BNS s.85. Shelter homes and medical facilities have duties if asked.", "कोई भी संरक्षण अधिकारी को सूचना दे सकता है। संरक्षण, निवास, धन, अभिरक्षा या क्षतिपूर्ति आदेश का आवेदन प्रथम श्रेणी न्यायिक मजिस्ट्रेट या महानगर मजिस्ट्रेट को जाता है, जहाँ आप अस्थायी रूप से भी रहती या काम करती हैं, जहाँ दूसरा व्यक्ति रहता या काम करता है, या जहाँ घटना हुई। पुलिस शिकायत भी हो सकती है: पति या उसके संबंधियों की क्रूरता BNS धारा 85 के तहत अपराध है। माँगने पर आश्रय गृह और चिकित्सा केंद्रों के कर्तव्य हैं।", "ఎవరైనా రక్షణ అధికారికి తెలియజేయవచ్చు. రక్షణ, నివాసం, డబ్బు, సంరక్షణ లేదా పరిహారం ఉత్తర్వుల దరఖాస్తు ఫస్ట్ క్లాస్ జ్యుడీషియల్ మేజిస్ట్రేట్ లేదా మెట్రోపాలిటన్ మేజిస్ట్రేట్‌కు, మీరు తాత్కాలికంగానైనా నివసించే లేదా పనిచేసే చోట, ఇతర వ్యక్తి నివసించే లేదా పనిచేసే చోట, లేదా జరిగిన చోట. పోలీసు ఫిర్యాదు కూడా చేయవచ్చు: భర్త లేదా అతని బంధువుల క్రూరత్వం BNS సెక్షన్ 85 కింద నేరం. అడిగితే ఆశ్రయ గృహాలు, వైద్య కేంద్రాలకు బాధ్యతలు ఉన్నాయి."),
    forumCites: ["dv-4", "dv-12-1", "dv-18", "dv-19", "dv-20", "dv-21", "dv-22", "dv-27", "bns-85", "dv-6", "dv-7"],
    rules: [],
    noPeriod: l("We did not find a time limit for this application in the Act's sections, and we will not state one from elsewhere. The Act says the first hearing should not ordinarily be beyond three days from when the court receives it. Speak to legal aid soon.", "हमें अधिनियम की धाराओं में इस आवेदन की समय-सीमा नहीं मिली, और हम कहीं और से नहीं बताएँगे। अधिनियम कहता है कि पहली सुनवाई सामान्यतः अदालत को मिलने के तीन दिन से आगे नहीं होगी। जल्द विधिक सहायता से बात करें।", "చట్టంలోని సెక్షన్లలో ఈ దరఖాస్తుకు గడువు కనిపించలేదు, వేరే చోటి నుండి మేము చెప్పము. కోర్టుకు అందిన మూడు రోజులకు మించి మొదటి విచారణ సాధారణంగా ఉండరాదని చట్టం చెబుతుంది. త్వరగా న్యాయ సహాయంతో మాట్లాడండి."),
    noPeriodCites: ["dv-12-4"],
    cost: l("You have a right to free legal services, which police, Protection Officers, service providers and Magistrates must tell you about.", "आपको निःशुल्क विधिक सेवा का अधिकार है, जिसके बारे में पुलिस, संरक्षण अधिकारी, सेवा प्रदाता और मजिस्ट्रेट को बताना होगा।", "ఉచిత న్యాయ సేవల హక్కు మీకు ఉంది, పోలీసులు, రక్షణ అధికారులు, సేవా ప్రదాతలు, మేజిస్ట్రేట్‌లు దీని గురించి చెప్పాలి."),
    costCites: ["dv-5-d", "lsa-12-c"],
    notes: [],
  },
  {
    id: "workplace",
    title: l("Sexual harassment at my workplace", "कार्यस्थल पर यौन उत्पीड़न", "పని చోట లైంగిక వేధింపులు"),
    blurb: l("Workplace Harassment Act 2013", "कार्यस्थल उत्पीड़न अधिनियम 2013", "పని చోట వేధింపుల చట్టం 2013"),
    questions: [
      {
        id: "woman",
        text: l("Is the complaint by a woman who was harassed?", "क्या शिकायत उत्पीड़ित महिला की ओर से है?", "ఫిర్యాదు వేధింపులకు గురైన మహిళ నుండా?"),
        proceedOn: "yes",
        abstainReason: l("This Act's complaint route is for an aggrieved woman. Please ask legal aid about other routes.", "इस अधिनियम की शिकायत व्यवस्था पीड़ित महिला के लिए है। अन्य रास्तों के लिए विधिक सहायता से पूछें।", "ఈ చట్టంలోని ఫిర్యాదు మార్గం బాధిత మహిళకు. ఇతర మార్గాల కోసం న్యాయ సహాయాన్ని అడగండి."),
        cites: ["posh-9-1"],
      },
    ],
    forum: l("The Internal Committee at your workplace. If there is none because there are fewer than ten workers, or the complaint is against the employer, the Local Committee set up by the District Officer. Sexual harassment is also an offence under BNS s.75, so a police complaint can be made too.", "आपके कार्यस्थल की आंतरिक समिति। यदि दस से कम कर्मचारियों के कारण समिति नहीं है, या शिकायत नियोक्ता के विरुद्ध है, तो ज़िला अधिकारी की स्थानीय समिति। यौन उत्पीड़न BNS धारा 75 के तहत अपराध भी है, इसलिए पुलिस शिकायत भी हो सकती है।", "మీ పని చోటి అంతర్గత కమిటీ. పది మంది కంటే తక్కువ కార్మికుల వల్ల లేకపోతే, లేదా ఫిర్యాదు యజమానిపై అయితే, జిల్లా అధికారి ఏర్పాటు చేసిన స్థానిక కమిటీ. లైంగిక వేధింపు BNS సెక్షన్ 75 కింద నేరం కూడా, కాబట్టి పోలీసు ఫిర్యాదు కూడా చేయవచ్చు."),
    forumCites: ["posh-4", "posh-6", "bns-75"],
    rules: [
      {
        id: "posh-complaint",
        label: l("Make the written complaint", "लिखित शिकायत करें", "రాతపూర్వక ఫిర్యాదు చేయండి"),
        fromLabel: l("The date of the incident, or the last one if there were several", "घटना की तारीख, या कई हों तो आख़िरी की", "సంఘటన తేదీ, చాలా ఉంటే చివరిది"),
        add: { months: 3 },
        cites: ["posh-9-1"],
        extensionNote: l("The Committee may extend this by up to three months, for reasons recorded in writing, if circumstances prevented you.", "परिस्थितियों ने रोका हो तो समिति लिखित कारणों से अधिकतम तीन महीने बढ़ा सकती है।", "పరిస్థితులు అడ్డుపడితే, కమిటీ రాతపూర్వక కారణాలతో మూడు నెలల వరకు పొడిగించవచ్చు."),
        extensionCites: ["posh-9-p"],
      },
    ],
    cost: l("We found no fee for this complaint in the Act.", "अधिनियम में इस शिकायत का कोई शुल्क नहीं मिला।", "చట్టంలో ఈ ఫిర్యాదుకు రుసుము కనిపించలేదు."),
    costCites: [],
    notes: [
      { cites: ["posh-11-4"], text: l("The inquiry is to be completed within ninety days.", "जाँच नब्बे दिनों में पूरी होनी है।", "విచారణ తొంభై రోజుల్లో పూర్తి కావాలి.") },
      { cites: ["posh-12"], text: l("During the inquiry, on your written request, the Committee may recommend steps such as a transfer.", "जाँच के दौरान, आपके लिखित अनुरोध पर, समिति स्थानांतरण जैसे क़दमों की सिफ़ारिश कर सकती है।", "విచారణ సమయంలో, మీ రాతపూర్వక అభ్యర్థనపై, కమిటీ బదిలీ వంటి చర్యలను సిఫార్సు చేయవచ్చు.") },
      { cites: ["posh-18"], text: l("The recommendations can be appealed to a court or tribunal. We could not confirm the appeal period from our copy of the Act, so ask legal aid.", "सिफ़ारिशों की अपील अदालत या न्यायाधिकरण में हो सकती है। अपने अधिनियम की प्रति से हम अपील की अवधि की पुष्टि नहीं कर सके, इसलिए विधिक सहायता से पूछें।", "సిఫార్సులపై కోర్టు లేదా ట్రైబ్యునల్‌లో అప్పీలు చేయవచ్చు. మా చట్టం ప్రతి నుండి అప్పీలు గడువు నిర్ధారించలేకపోయాం, కాబట్టి న్యాయ సహాయాన్ని అడగండి.") },
    ],
  },
  {
    id: "report-crime",
    title: l("Police will not register my complaint", "पुलिस मेरी शिकायत दर्ज नहीं कर रही", "పోలీసులు నా ఫిర్యాదు నమోదు చేయడం లేదు"),
    blurb: l("BNSS section 173", "BNSS धारा 173", "BNSS సెక్షన్ 173"),
    questions: [],
    forum: l("Give it at a police station, in person or electronically, wherever the offence happened. If they refuse, send the substance in writing by post to the Superintendent of Police. If that fails, apply to the Magistrate.", "थाने में व्यक्तिगत रूप से या इलेक्ट्रॉनिक रूप से दें, अपराध कहीं भी हुआ हो। मना करें तो सार लिखित रूप में डाक से पुलिस अधीक्षक को भेजें। फिर भी न हो तो मजिस्ट्रेट को आवेदन करें।", "నేరం ఎక్కడ జరిగినా, పోలీస్ స్టేషన్‌లో స్వయంగా లేదా ఎలక్ట్రానిక్‌గా ఇవ్వండి. నిరాకరిస్తే సారాంశాన్ని రాతపూర్వకంగా పోస్టులో పోలీస్ సూపరింటెండెంట్‌కు పంపండి. అదీ కాకపోతే మేజిస్ట్రేట్‌కు దరఖాస్తు చేయండి."),
    forumCites: ["bnss-173-1", "bnss-173-4", "bnss-173-4-m"],
    rules: [],
    noPeriod: l("Courts cannot take up smaller offences after a set time, starting at six months for an offence with a fine only. It depends on the offence, so we will not compute it. Report as soon as you can.", "छोटे अपराधों पर अदालत तय समय के बाद विचार नहीं कर सकती, केवल जुर्माने वाले अपराध के लिए छह महीने से शुरू। यह अपराध पर निर्भर है, इसलिए हम गणना नहीं करेंगे। जल्द से जल्द सूचना दें।", "చిన్న నేరాలను నిర్ణీత సమయం తర్వాత కోర్టులు స్వీకరించలేవు, జరిమానా మాత్రమే ఉన్న నేరానికి ఆరు నెలలతో మొదలు. ఇది నేరంపై ఆధారపడుతుంది, కాబట్టి మేము లెక్కించము. వీలైనంత త్వరగా తెలియజేయండి."),
    noPeriodCites: ["bnss-514-2"],
    cost: l("A copy of the recorded information must be given to you free of cost.", "दर्ज सूचना की प्रति आपको निःशुल्क मिलनी चाहिए।", "నమోదు చేసిన సమాచారం ప్రతి మీకు ఉచితంగా ఇవ్వాలి."),
    costCites: ["bnss-173-2"],
    notes: [],
  },
  {
    id: "cyber",
    title: l("Online fraud or cyber crime", "ऑनलाइन धोखाधड़ी या साइबर अपराध", "ఆన్‌లైన్ మోసం లేదా సైబర్ నేరం"),
    blurb: l("BNSS, BNS and the IT Act", "BNSS, BNS और IT अधिनियम", "BNSS, BNS, IT చట్టం"),
    questions: [],
    forum: l("The police, in person or electronically, wherever it happened, and the National Cyber Crime Reporting Portal at cybercrime.gov.in. Cheating by personation and identity theft are offences. The IT Act also provides for a complaint to an adjudicating officer; ask legal aid whether that fits, since our copy of the Act predates later amendments.", "पुलिस, व्यक्तिगत रूप से या इलेक्ट्रॉनिक रूप से, घटना कहीं भी हो, और राष्ट्रीय साइबर अपराध रिपोर्टिंग पोर्टल cybercrime.gov.in। प्रतिरूपण द्वारा छल और पहचान की चोरी अपराध हैं। IT अधिनियम न्यायनिर्णायक अधिकारी को शिकायत का भी प्रावधान करता है; यह लागू है या नहीं, विधिक सहायता से पूछें, क्योंकि हमारी प्रति बाद के संशोधनों से पहले की है।", "పోలీసులు, స్వయంగా లేదా ఎలక్ట్రానిక్‌గా, ఎక్కడ జరిగినా, జాతీయ సైబర్ నేర నివేదన పోర్టల్ cybercrime.gov.in. మారువేషంతో మోసం, గుర్తింపు దొంగతనం నేరాలు. IT చట్టం న్యాయనిర్ణయ అధికారికి ఫిర్యాదును కూడా చెబుతుంది; అది వర్తిస్తుందో న్యాయ సహాయాన్ని అడగండి, మా ప్రతి తర్వాతి సవరణలకు ముందుది."),
    forumCites: ["bnss-173-1", "portal-cyber", "it-66c", "it-66d", "bns-319", "it-46", "it-form"],
    rules: [],
    noPeriod: l("Report straight away. We could not verify any time window for getting money back from our sources, and we will not state one. If you report electronically, you must sign within three days.", "तुरंत सूचना दें। पैसे वापस पाने की किसी समय-सीमा की पुष्टि हम अपने स्रोतों से नहीं कर सके, और नहीं बताएँगे। इलेक्ट्रॉनिक रूप से सूचना दें तो तीन दिन में हस्ताक्षर करने होंगे।", "వెంటనే తెలియజేయండి. డబ్బు తిరిగి పొందే సమయ పరిమితిని మా మూలాల నుండి నిర్ధారించలేకపోయాం, చెప్పము. ఎలక్ట్రానిక్‌గా తెలియజేస్తే మూడు రోజుల్లో సంతకం చేయాలి."),
    noPeriodCites: ["bnss-173-1-ii"],
    cost: l("A copy of the police information is free. Our sources do not state any fee for the portal or for adjudication.", "पुलिस सूचना की प्रति निःशुल्क है। पोर्टल या न्यायनिर्णयन के शुल्क का उल्लेख हमारे स्रोतों में नहीं है।", "పోలీసు సమాచారం ప్రతి ఉచితం. పోర్టల్ లేదా న్యాయనిర్ణయం రుసుము మా మూలాల్లో లేదు."),
    costCites: ["bnss-173-2"],
    notes: [],
  },
  {
    id: "tenant",
    title: l("A dispute with my landlord or tenant", "मकान मालिक या किरायेदार से विवाद", "ఇంటి యజమాని లేదా అద్దెదారుతో వివాదం"),
    blurb: l("State rent law decides this", "राज्य का किराया कानून तय करता है", "రాష్ట్ర అద్దె చట్టం నిర్ణయిస్తుంది"),
    questions: [],
    alwaysAbstain: l("Where to go depends on your state's rent law and your agreement, and we do not hold every state's law. We will not name a forum. Please speak to legal aid. What we can show is below.", "कहाँ जाना है यह आपके राज्य के किराया कानून और अनुबंध पर निर्भर है, और हमारे पास हर राज्य का कानून नहीं है। हम कोई मंच नहीं बताएँगे। कृपया विधिक सहायता से बात करें। जो हम दिखा सकते हैं वह नीचे है।", "ఎక్కడికి వెళ్లాలన్నది మీ రాష్ట్ర అద్దె చట్టం, ఒప్పందంపై ఆధారపడుతుంది, ప్రతి రాష్ట్ర చట్టం మా వద్ద లేదు. మేము వేదికను చెప్పము. దయచేసి న్యాయ సహాయంతో మాట్లాడండి. మేము చూపగలిగేది కింద ఉంది."),
    forum: l("", "", ""),
    forumCites: [],
    rules: [],
    cost: l("", "", ""),
    costCites: [],
    notes: [
      { cites: ["tpa-106", "tpa-106-b"], text: l("Default rule, unless a contract or local law says otherwise: a monthly lease ends on fifteen days' notice.", "सामान्य नियम, जब तक अनुबंध या स्थानीय कानून कुछ और न कहे: मासिक पट्टा पंद्रह दिन के नोटिस पर समाप्त होता है।", "సాధారణ నియమం, ఒప్పందం లేదా స్థానిక చట్టం వేరేగా చెబితే తప్ప: నెలవారీ లీజు పదిహేను రోజుల నోటీసుతో ముగుస్తుంది.") },
      { cites: ["lim-a67"], text: l("A landlord's suit to recover possession from a tenant: twelve years from when the tenancy ends.", "किरायेदार से कब्ज़ा वापस लेने का मकान मालिक का वाद: किरायेदारी समाप्त होने से बारह वर्ष।", "అద్దెదారు నుండి స్వాధీనం కోసం యజమాని దావా: అద్దె ముగిసినప్పటి నుండి పన్నెండేళ్లు.") },
      { cites: ["apten-1-3", "apten-11"], text: l("Andhra Pradesh has a 2017 Tenancy Act, with security deposit refund within one month of vacating. It comes into force on a notified date, and we could not confirm from our sources that it has been notified. Ask before relying on it.", "आंध्र प्रदेश में 2017 का किरायेदारी अधिनियम है, जिसमें जगह खाली करने के एक महीने में जमा राशि की वापसी है। यह अधिसूचित तारीख से लागू होता है, और हम स्रोतों से पुष्टि नहीं कर सके कि यह अधिसूचित हुआ। इस पर भरोसा करने से पहले पूछें।", "ఆంధ్రప్రదేశ్‌లో 2017 అద్దె చట్టం ఉంది, ఖాళీ చేసిన ఒక నెలలో డిపాజిట్ తిరిగి ఇవ్వాలి. ఇది నోటిఫై చేసిన తేదీ నుండి అమలులోకి వస్తుంది, నోటిఫై అయిందో మా మూలాల నుండి నిర్ధారించలేకపోయాం. దీనిపై ఆధారపడే ముందు అడగండి.") },
    ],
  },
];

export const NOT_COVERED_ABSTAIN = l(
  "Other matters such as family, property, employment, accident claims or a case already in court are not in this table, and we will not guess a date or a court. A person can look at your facts: call NALSA on 15100 or go to your District Legal Services Authority.",
  "परिवार, संपत्ति, नौकरी, दुर्घटना दावे या अदालत में पहले से चल रहे मामले इस तालिका में नहीं हैं, और हम तारीख या अदालत का अनुमान नहीं लगाएँगे। कोई व्यक्ति आपके तथ्य देख सकता है: NALSA 15100 पर कॉल करें या ज़िला विधिक सेवा प्राधिकरण जाएँ।",
  "కుటుంబం, ఆస్తి, ఉద్యోగం, ప్రమాద క్లెయిమ్‌లు లేదా ఇప్పటికే కోర్టులో ఉన్న కేసులు ఈ పట్టికలో లేవు, తేదీ లేదా కోర్టును మేము ఊహించము. ఒక వ్యక్తి మీ వాస్తవాలు చూడగలరు: NALSA 15100కు కాల్ చేయండి లేదా జిల్లా న్యాయ సేవల ప్రాధికార సంస్థకు వెళ్లండి.",
);

export type RouteResult =
  | { status: "questions"; situation: Situation; next: GateQuestion }
  | { status: "abstain"; situation: Situation | null; reason: L; cites: string[] }
  | { status: "route"; situation: Situation };

/** The only way a situation reaches a route. Unknown and unsure both abstain. */
export function routeSituation(situationId: string | null, answers: Record<string, Answer>): RouteResult {
  const situation = SITUATIONS.find(item => item.id === situationId);
  if (!situation) return { status: "abstain", situation: null, reason: NOT_COVERED_ABSTAIN, cites: [] };
  if (situation.alwaysAbstain) return { status: "abstain", situation, reason: situation.alwaysAbstain, cites: [] };
  for (const question of situation.questions) {
    const answer = answers[question.id];
    if (answer === undefined) return { status: "questions", situation, next: question };
    if (answer !== question.proceedOn) {
      return { status: "abstain", situation, reason: question.abstainReason, cites: question.cites ?? [] };
    }
  }
  return { status: "route", situation };
}

function parseIso(iso: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return null;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return date.getUTCMonth() === Number(match[2]) - 1 ? date : null;
}

function format(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function addMonthsClamped(date: Date, months: number): Date {
  const day = date.getUTCDate();
  const shifted = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + months, 1));
  const last = new Date(Date.UTC(shifted.getUTCFullYear(), shifted.getUTCMonth() + 1, 0)).getUTCDate();
  shifted.setUTCDate(Math.min(day, last));
  return shifted;
}

/**
 * Last day by plain counting from the date given, excluding that first day
 * (Limitation Act s.12(1)). A month ending shorter clamps down, so 31 Jan plus
 * one month is 28 Feb: where a rule could be read two ways this takes the
 * earlier day, because being a day early costs nothing and a day late can cost
 * the case. Not legal advice on your exact last day: the rule's own exclusions
 * are not applied.
 */
export function computeDeadline(rule: Pick<DeadlineRule, "add" | "thenAdd">, fromIso: string): string | null {
  let date = parseIso(fromIso);
  if (!date) return null;
  const { days = 0, months = 0, years = 0 } = rule.add;
  date = addMonthsClamped(date, months + years * 12);
  date = new Date(date.getTime() + days * 86_400_000);
  if (rule.thenAdd?.months) date = addMonthsClamped(date, rule.thenAdd.months);
  return format(date);
}

export function isPast(iso: string, todayIso: string): boolean {
  return iso < todayIso;
}
