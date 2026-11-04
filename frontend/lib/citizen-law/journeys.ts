/**
 * C-08: guided journeys. A short decision tree for each situation people arrive
 * with. Every path ends in a tool or a good question, never a conclusion about
 * the person's case. Explanations cite provisions.json only.
 */
import { l, type L } from "./law";

export type ToolLink =
  | { tool: "rights"; topic: "arrest" | "stop" | "summons" | "search" | "report" }
  | { tool: "router"; situation: string }
  | { tool: "draft"; template: string }
  | { tool: "notice" }
  | { tool: "legal-aid" }
  | { tool: "matter" };

export type JourneyOption = { label: L; next: string };

export type JourneyStep = {
  id: string;
  title: L;
  body?: L;
  cites?: string[];
  emergency?: boolean;
  options?: JourneyOption[];
  /** Present on an end step: where this person goes next. */
  ask?: L;
  tools?: { label: L; to: ToolLink }[];
};

export type Journey = { id: string; title: L; blurb: L; start: string; steps: JourneyStep[] };

const TOOL = {
  legalAid: { label: l("Check legal aid", "विधिक सहायता देखें", "న్యాయ సహాయం చూడండి"), to: { tool: "legal-aid" } as ToolLink },
  matter: { label: l("Note the date in My matter", "मेरा मामला में तारीख लिखें", "నా విషయంలో తేదీ రాయండి"), to: { tool: "matter" } as ToolLink },
  notice: { label: l("Explain the paper I got", "मुझे मिला काग़ज़ समझाएँ", "నాకు వచ్చిన కాగితం వివరించండి"), to: { tool: "notice" } as ToolLink },
};

export const JOURNEYS: Journey[] = [
  {
    id: "arrested-relative",
    title: l("Someone close to me was arrested", "मेरे किसी अपने को गिरफ़्तार किया गया", "నా దగ్గరి వారిని అరెస్టు చేశారు"),
    blurb: l("What to ask for, and how soon", "क्या माँगें, और कितनी जल्दी", "ఏం అడగాలి, ఎంత త్వరగా"),
    start: "know",
    steps: [
      { id: "know", title: l("Do you know where they are being held?", "क्या आपको पता है कि उन्हें कहाँ रखा गया है?", "వారిని ఎక్కడ ఉంచారో తెలుసా?"), body: l("Police must tell a relative, friend or nominated person about the arrest and the place.", "पुलिस को संबंधी, मित्र या नामित व्यक्ति को गिरफ़्तारी और स्थान बताना होगा।", "అరెస్టు, స్థలం గురించి బంధువు, మిత్రుడు లేదా నామినేట్ చేసిన వ్యక్తికి పోలీసులు చెప్పాలి."), cites: ["bnss-48-1"], options: [{ label: l("Yes", "हाँ", "అవును"), next: "time" }, { label: l("No", "नहीं", "లేదు"), next: "find" }] },
      { id: "find", title: l("Ask the nearest police station, and call for help", "निकटतम थाने से पूछें, और मदद के लिए कॉल करें", "సమీప పోలీస్ స్టేషన్‌ను అడగండి, సహాయం కోసం కాల్ చేయండి"), body: l("An entry must be kept at the station of who was told about the arrest. A lawyer or legal aid can ask for you. 15100 is the NALSA helpline.", "थाने में रिकॉर्ड रखना होता है कि गिरफ़्तारी की सूचना किसे दी गई। वकील या विधिक सहायता आपके लिए पूछ सकते हैं। 15100 NALSA हेल्पलाइन है।", "అరెస్టు ఎవరికి చెప్పారో స్టేషన్‌లో నమోదు ఉంచాలి. న్యాయవాది లేదా న్యాయ సహాయం మీ కోసం అడగవచ్చు. 15100 NALSA హెల్ప్‌లైన్."), cites: ["bnss-48-3", "nalsa-15100"], tools: [{ label: l("See arrest rights", "गिरफ़्तारी के अधिकार देखें", "అరెస్టు హక్కులు చూడండి"), to: { tool: "rights", topic: "arrest" } }, TOOL.legalAid], ask: l("What must police do to inform family after an arrest, and what can we do if they have not?", "गिरफ़्तारी के बाद परिवार को सूचित करने के लिए पुलिस को क्या करना होता है, और न करने पर हम क्या कर सकते हैं?", "అరెస్టు తర్వాత కుటుంబానికి తెలియజేయడానికి పోలీసులు ఏం చేయాలి, చేయకపోతే మేం ఏం చేయవచ్చు?") },
      { id: "time", title: l("Do you know the time of arrest?", "क्या गिरफ़्तारी का समय पता है?", "అరెస్టు సమయం తెలుసా?"), body: l("A person arrested without a warrant is not to be held beyond twenty-four hours without a Magistrate's order, not counting the journey.", "बिना वारंट गिरफ़्तार व्यक्ति को मजिस्ट्रेट के आदेश के बिना, यात्रा छोड़कर, चौबीस घंटे से अधिक नहीं रखा जा सकता।", "వారెంట్ లేకుండా అరెస్టయిన వ్యక్తిని మేజిస్ట్రేట్ ఆదేశం లేకుండా, ప్రయాణం మినహా, ఇరవై నాలుగు గంటలకు మించి ఉంచరాదు."), cites: ["bnss-58", "const-22-2"], options: [{ label: l("Show me what to ask for", "मुझे बताएँ क्या माँगना है", "ఏం అడగాలో చూపించండి"), next: "ask" }] },
      { id: "ask", title: l("What you can ask for now", "अभी आप क्या माँग सकते हैं", "ఇప్పుడు మీరు ఏం అడగవచ్చు"), body: l("The grounds of arrest, the memorandum of arrest, a meeting with an advocate during questioning, a medical examination. If they cannot afford a lawyer, legal aid can help.", "गिरफ़्तारी के आधार, गिरफ़्तारी का ज्ञापन, पूछताछ के दौरान वकील से मिलना, चिकित्सीय जाँच। वकील का ख़र्च न उठा सकें तो विधिक सहायता मदद कर सकती है।", "అరెస్టు ఆధారాలు, అరెస్టు మెమో, విచారణ సమయంలో న్యాయవాదిని కలవడం, వైద్య పరీక్ష. న్యాయవాది ఖర్చు భరించలేకపోతే న్యాయ సహాయం సహాయపడుతుంది."), cites: ["bnss-47-1", "bnss-36-b", "bnss-38", "bnss-53-1", "lsa-12-g"], tools: [{ label: l("See arrest rights", "गिरफ़्तारी के अधिकार देखें", "అరెస్టు హక్కులు చూడండి"), to: { tool: "rights", topic: "arrest" } }, TOOL.legalAid], ask: l("What is the procedure for applying for bail after an arrest under the BNSS?", "BNSS के तहत गिरफ़्तारी के बाद ज़मानत के आवेदन की प्रक्रिया क्या है?", "BNSS కింద అరెస్టు తర్వాత బెయిల్ దరఖాస్తు ప్రక్రియ ఏమిటి?") },
    ],
  },
  {
    id: "cheque-bounce",
    title: l("A cheque bounced", "चेक बाउंस हुआ", "చెక్ బౌన్స్ అయింది"),
    blurb: l("Short deadlines. Start with the dates.", "समय-सीमा कम है। तारीखों से शुरू करें।", "గడువులు తక్కువ. తేదీలతో మొదలుపెట్టండి."),
    start: "role",
    steps: [
      { id: "role", title: l("Which is your position?", "आपकी स्थिति क्या है?", "మీ పరిస్థితి ఏమిటి?"), options: [{ label: l("Someone gave me the cheque", "किसी ने मुझे चेक दिया", "ఎవరో నాకు చెక్ ఇచ్చారు"), next: "payee" }, { label: l("I gave it and got a notice", "मैंने दिया और नोटिस आया", "నేను ఇచ్చాను, నోటీసు వచ్చింది"), next: "drawer" }] },
      { id: "payee", title: l("Work out your dates first", "पहले अपनी तारीखें निकालें", "ముందు మీ తేదీలు చూసుకోండి"), body: l("Thirty days to send a written notice after the bank tells you. They then have fifteen days to pay, and a complaint must follow within one month.", "बैंक की सूचना के बाद लिखित नोटिस के लिए तीस दिन। फिर उन्हें भुगतान के लिए पंद्रह दिन, और उसके बाद एक महीने में शिकायत।", "బ్యాంకు చెప్పిన తర్వాత రాతపూర్వక నోటీసుకు ముప్పై రోజులు. తర్వాత చెల్లించడానికి వారికి పదిహేను రోజులు, ఆ తర్వాత ఒక నెలలో ఫిర్యాదు."), cites: ["ni-138-b", "ni-138-c", "ni-142-b"], tools: [{ label: l("Work out the dates", "तारीखें निकालें", "తేదీలు చూడండి"), to: { tool: "router", situation: "cheque" } }, { label: l("Draft the notice", "नोटिस तैयार करें", "నోటీసు తయారు చేయండి"), to: { tool: "draft", template: "cheque_notice" } }], ask: l("What must a section 138 notice contain, and how do I prove it was delivered?", "धारा 138 के नोटिस में क्या होना चाहिए, और तामील कैसे सिद्ध करूँ?", "సెక్షన్ 138 నోటీసులో ఏం ఉండాలి, అందినట్లు ఎలా రుజువు చేయాలి?") },
      { id: "drawer", title: l("Note the date you received it", "मिलने की तारीख नोट करें", "అందిన తేదీ గుర్తుంచుకోండి"), body: l("The section gives fifteen days from receipt of the notice to pay. Get legal help early.", "धारा नोटिस मिलने से भुगतान के लिए पंद्रह दिन देती है। जल्दी क़ानूनी मदद लें।", "నోటీసు అందినప్పటి నుండి చెల్లించడానికి సెక్షన్ పదిహేను రోజులు ఇస్తుంది. త్వరగా న్యాయ సహాయం తీసుకోండి."), cites: ["ni-138-c"], tools: [TOOL.notice, TOOL.matter, TOOL.legalAid], ask: l("What are the defences to a section 138 complaint, and what happens if I pay within fifteen days?", "धारा 138 की शिकायत में बचाव क्या हैं, और पंद्रह दिन में भुगतान करने पर क्या होता है?", "సెక్షన్ 138 ఫిర్యాదులో రక్షణలు ఏమిటి, పదిహేను రోజుల్లో చెల్లిస్తే ఏం జరుగుతుంది?") },
    ],
  },
  {
    id: "cyber-fraud",
    title: l("I was cheated online", "मुझे ऑनलाइन ठगा गया", "నన్ను ఆన్‌లైన్‌లో మోసం చేశారు"),
    blurb: l("Report it and keep the proof", "सूचना दें और सबूत रखें", "తెలియజేయండి, రుజువు ఉంచుకోండి"),
    start: "pressure",
    steps: [
      { id: "pressure", title: l("Is someone pressing you to pay right now?", "क्या कोई अभी आप पर भुगतान का दबाव डाल रहा है?", "ఇప్పుడు ఎవరైనా చెల్లించమని ఒత్తిడి చేస్తున్నారా?"), options: [{ label: l("Yes, they say I am under arrest or in trouble", "हाँ, कहते हैं कि मैं गिरफ़्तार हूँ या मुसीबत में हूँ", "అవును, నేను అరెస్టులో ఉన్నానని లేదా ఇబ్బందిలో ఉన్నానని అంటున్నారు"), next: "digital" }, { label: l("No, the money or data is already gone", "नहीं, पैसा या डेटा जा चुका", "లేదు, డబ్బు లేదా డేటా ఇప్పటికే పోయింది"), next: "report" }] },
      { id: "digital", title: l("Stop and check with a person", "रुकें और किसी व्यक्ति से जाँचें", "ఆగి ఒక వ్యక్తితో తనిఖీ చేయండి"), body: l("The BNSS describes arrest as touching or confining a person, unless they submit to custody. We found no procedure called a “digital arrest” in our sources. Speak to someone you trust, police on 112, or legal aid on 15100 before sending money or codes.", "BNSS गिरफ़्तारी को व्यक्ति को छूना या रोकना बताती है, जब तक वह स्वयं को न सौंपे। हमारे स्रोतों में “डिजिटल अरेस्ट” नाम की प्रक्रिया नहीं मिली। पैसे या कोड भेजने से पहले किसी भरोसेमंद व्यक्ति, पुलिस (112) या विधिक सहायता (15100) से बात करें।", "BNSS ప్రకారం అరెస్టు అంటే వ్యక్తిని తాకడం లేదా నిర్బంధించడం, వారు లొంగిపోతే తప్ప. “డిజిటల్ అరెస్ట్” అనే ప్రక్రియ మా మూలాల్లో లేదు. డబ్బు లేదా కోడ్‌లు పంపే ముందు నమ్మకమైన వ్యక్తి, పోలీసులు (112) లేదా న్యాయ సహాయం (15100)తో మాట్లాడండి."), cites: ["bnss-43-1-m", "helpline-112", "nalsa-15100"], emergency: true, tools: [{ label: l("Read about being stopped or questioned", "रोकने या पूछताछ के बारे में पढ़ें", "ఆపడం లేదా ప్రశ్నించడం గురించి చదవండి"), to: { tool: "rights", topic: "stop" } }, TOOL.notice], ask: l("Can police arrest someone over a video call, and how is a genuine summons served?", "क्या पुलिस वीडियो कॉल पर गिरफ़्तार कर सकती है, और असली समन कैसे तामील होता है?", "పోలీసులు వీడియో కాల్‌లో అరెస్టు చేయగలరా, నిజమైన సమన్లు ఎలా అందజేస్తారు?") },
      { id: "report", title: l("Report it, and keep everything", "सूचना दें, और सब कुछ रखें", "తెలియజేయండి, అన్నీ ఉంచుకోండి"), body: l("You can give information to police electronically, wherever it happened, and sign within three days. There is a national reporting portal at cybercrime.gov.in. Keep screenshots, transaction numbers and messages.", "आप घटना कहीं भी हो, पुलिस को इलेक्ट्रॉनिक सूचना दे सकते हैं और तीन दिन में हस्ताक्षर कर सकते हैं। राष्ट्रीय पोर्टल cybercrime.gov.in है। स्क्रीनशॉट, लेनदेन संख्या और संदेश रखें।", "ఎక్కడ జరిగినా పోలీసులకు ఎలక్ట్రానిక్‌గా తెలియజేసి మూడు రోజుల్లో సంతకం చేయవచ్చు. జాతీయ పోర్టల్ cybercrime.gov.in. స్క్రీన్‌షాట్‌లు, లావాదేవీ నంబర్లు, సందేశాలు ఉంచుకోండి."), cites: ["bnss-173-1", "bnss-173-1-ii", "portal-cyber", "it-66d", "bns-319"], tools: [{ label: l("Where to report", "कहाँ सूचना दें", "ఎక్కడ తెలియజేయాలి"), to: { tool: "router", situation: "cyber" } }, { label: l("Draft the complaint", "शिकायत तैयार करें", "ఫిర్యాదు తయారు చేయండి"), to: { tool: "draft", template: "police_complaint" } }], ask: l("What should I include when reporting an online financial fraud to police?", "ऑनलाइन वित्तीय धोखाधड़ी की सूचना पुलिस को देते समय क्या लिखूँ?", "ఆన్‌లైన్ ఆర్థిక మోసం గురించి పోలీసులకు తెలియజేసేటప్పుడు ఏం చేర్చాలి?") },
    ],
  },
  {
    id: "domestic-violence",
    title: l("Violence at home", "घर पर हिंसा", "ఇంట్లో హింస"),
    blurb: l("Safety first, then the options", "पहले सुरक्षा, फिर विकल्प", "ముందు భద్రత, తర్వాత మార్గాలు"),
    start: "safe",
    steps: [
      { id: "safe", title: l("Are you safe right now?", "क्या आप अभी सुरक्षित हैं?", "మీరు ఇప్పుడు సురక్షితంగా ఉన్నారా?"), body: l("If this is on a shared phone, you can leave this page at any time.", "यदि यह साझा फ़ोन है, तो आप कभी भी यह पृष्ठ छोड़ सकती हैं।", "ఇది పంచుకునే ఫోన్ అయితే, ఎప్పుడైనా ఈ పేజీ వదిలేయవచ్చు."), options: [{ label: l("No, I am in danger", "नहीं, मैं ख़तरे में हूँ", "లేదు, నేను ప్రమాదంలో ఉన్నాను"), next: "danger" }, { label: l("Yes, for now", "हाँ, अभी के लिए", "అవును, ప్రస్తుతానికి"), next: "options" }] },
      { id: "danger", title: l("Call 112 now", "अभी 112 पर कॉल करें", "ఇప్పుడే 112కు కాల్ చేయండి"), body: l("112 is the emergency number for police, fire and ambulance. When you can, call 15100 for free legal help.", "112 पुलिस, दमकल और एम्बुलेंस का आपातकालीन नंबर है। जब हो सके, निःशुल्क क़ानूनी मदद के लिए 15100 पर कॉल करें।", "112 పోలీసు, అగ్నిమాపక, అంబులెన్స్ అత్యవసర నంబర్. వీలైనప్పుడు ఉచిత న్యాయ సహాయం కోసం 15100కు కాల్ చేయండి."), cites: ["helpline-112", "nalsa-15100"], emergency: true, tools: [TOOL.legalAid] },
      { id: "options", title: l("What the law offers", "क़ानून क्या देता है", "చట్టం ఏం ఇస్తుంది"), body: l("Anyone can tell a Protection Officer. A Magistrate can make protection, residence, money, custody and compensation orders. You have a right to free legal services, and police must tell you this.", "कोई भी संरक्षण अधिकारी को बता सकता है। मजिस्ट्रेट संरक्षण, निवास, धन, अभिरक्षा और क्षतिपूर्ति आदेश दे सकता है। आपको निःशुल्क विधिक सेवा का अधिकार है, और पुलिस को यह बताना होगा।", "ఎవరైనా రక్షణ అధికారికి చెప్పవచ్చు. మేజిస్ట్రేట్ రక్షణ, నివాసం, డబ్బు, సంరక్షణ, పరిహారం ఉత్తర్వులు ఇవ్వవచ్చు. ఉచిత న్యాయ సేవల హక్కు మీకు ఉంది, పోలీసులు ఇది చెప్పాలి."), cites: ["dv-4", "dv-12-1", "dv-18", "dv-19", "dv-20", "dv-21", "dv-22", "dv-5-d"], tools: [{ label: l("Where to apply", "कहाँ आवेदन करें", "ఎక్కడ దరఖాస్తు చేయాలి"), to: { tool: "router", situation: "domestic-violence" } }, TOOL.legalAid], ask: l("How do I apply for a protection order under the Domestic Violence Act, and who can help me fill it in?", "घरेलू हिंसा अधिनियम में संरक्षण आदेश के लिए कैसे आवेदन करूँ, और कौन मदद कर सकता है?", "గృహ హింస చట్టం కింద రక్షణ ఉత్తర్వుకు ఎలా దరఖాస్తు చేయాలి, ఎవరు సహాయం చేయగలరు?") },
    ],
  },
  {
    id: "tenant",
    title: l("A problem with my landlord or tenant", "मकान मालिक या किरायेदार से समस्या", "ఇంటి యజమాని లేదా అద్దెదారుతో సమస్య"),
    blurb: l("It depends on your state's law", "यह आपके राज्य के कानून पर निर्भर है", "ఇది మీ రాష్ట్ర చట్టంపై ఆధారపడుతుంది"),
    start: "paper",
    steps: [
      { id: "paper", title: l("Have you received a notice to leave?", "क्या जगह छोड़ने का नोटिस मिला है?", "ఖాళీ చేయమని నోటీసు వచ్చిందా?"), options: [{ label: l("Yes", "हाँ", "అవును"), next: "noticed" }, { label: l("No, it is something else", "नहीं, कुछ और है", "లేదు, వేరే విషయం"), next: "other" }] },
      { id: "noticed", title: l("Read the notice first", "पहले नोटिस पढ़ें", "ముందు నోటీసు చదవండి"), body: l("The default rule is fifteen days' notice for a monthly lease, but a contract or local law can change it, and your state's rent law may govern. We do not hold every state's law.", "सामान्य नियम मासिक पट्टे के लिए पंद्रह दिन का नोटिस है, पर अनुबंध या स्थानीय कानून इसे बदल सकते हैं, और राज्य का किराया कानून लागू हो सकता है। हर राज्य का कानून हमारे पास नहीं है।", "సాధారణ నియమం నెలవారీ లీజుకు పదిహేను రోజుల నోటీసు, కానీ ఒప్పందం లేదా స్థానిక చట్టం మార్చవచ్చు, రాష్ట్ర అద్దె చట్టం వర్తించవచ్చు. ప్రతి రాష్ట్ర చట్టం మా వద్ద లేదు."), cites: ["tpa-106", "tpa-106-b"], tools: [TOOL.notice, TOOL.legalAid, TOOL.matter], ask: l("What notice must a landlord give to end a tenancy in my state, and what does my rent agreement need to say?", "मेरे राज्य में किरायेदारी समाप्त करने के लिए मकान मालिक को कौन सा नोटिस देना होता है, और किराया अनुबंध में क्या होना चाहिए?", "నా రాష్ట్రంలో అద్దె ముగించడానికి యజమాని ఏ నోటీసు ఇవ్వాలి, అద్దె ఒప్పందంలో ఏం ఉండాలి?") },
      { id: "other", title: l("Deposit, rent or repairs", "जमा राशि, किराया या मरम्मत", "డిపాజిట్, అద్దె లేదా మరమ్మతులు"), body: l("These turn on your agreement and your state's law, so we will not name a forum. A written request to the other side is often a useful record.", "ये आपके अनुबंध और राज्य के कानून पर निर्भर हैं, इसलिए हम कोई मंच नहीं बताएँगे। दूसरे पक्ष को लिखित अनुरोध अक्सर उपयोगी रिकॉर्ड होता है।", "ఇవి మీ ఒప్పందం, రాష్ట్ర చట్టంపై ఆధారపడతాయి, కాబట్టి వేదికను చెప్పము. ఇతర పక్షానికి రాతపూర్వక అభ్యర్థన తరచూ ఉపయోగకరమైన రికార్డు."), cites: ["tpa-106"], tools: [{ label: l("Draft a letter", "पत्र तैयार करें", "లేఖ తయారు చేయండి"), to: { tool: "draft", template: "legal_notice" } }, { label: l("See what we can show", "देखें हम क्या दिखा सकते हैं", "మేము చూపగలిగేది చూడండి"), to: { tool: "router", situation: "tenant" } }, TOOL.legalAid], ask: l("What are a tenant's rights about the security deposit and repairs in my state?", "मेरे राज्य में जमा राशि और मरम्मत के बारे में किरायेदार के क्या अधिकार हैं?", "నా రాష్ట్రంలో డిపాజిట్, మరమ్మతుల గురించి అద్దెదారు హక్కులు ఏమిటి?") },
    ],
  },
  {
    id: "consumer-defect",
    title: l("I paid for something faulty", "मैंने ख़राब चीज़ के लिए पैसे दिए", "లోపభూయిష్ట దానికి డబ్బు చెల్లించాను"),
    blurb: l("Consumer Commission route", "उपभोक्ता आयोग का रास्ता", "వినియోగదారుల కమిషన్ మార్గం"),
    start: "use",
    steps: [
      { id: "use", title: l("Was it for your own use?", "क्या यह आपके अपने उपयोग के लिए था?", "ఇది మీ స్వంత ఉపయోగానికా?"), options: [{ label: l("Yes", "हाँ", "అవును"), next: "route" }, { label: l("No, for resale or business", "नहीं, पुनर्विक्रय या व्यवसाय के लिए", "లేదు, తిరిగి అమ్మకం లేదా వ్యాపారం కోసం"), next: "business" }] },
      { id: "route", title: l("You can look at a consumer complaint", "आप उपभोक्ता शिकायत देख सकते हैं", "మీరు వినియోగదారు ఫిర్యాదు చూడవచ్చు"), body: l("A complaint goes to the District Commission, within two years of the cause of action. You may file electronically.", "शिकायत ज़िला आयोग में, वाद-कारण से दो वर्ष में होती है। आप इलेक्ट्रॉनिक रूप से दाखिल कर सकते हैं।", "ఫిర్యాదు జిల్లా కమిషన్‌కు, వాద కారణం నుండి రెండేళ్లలో. ఎలక్ట్రానిక్‌గా దాఖలు చేయవచ్చు."), cites: ["cpa-69-1", "cpa-34-2", "cpa-35-1", "cpa-2-10", "cpa-2-11"], tools: [{ label: l("Work out the date", "तारीख निकालें", "తేదీ చూడండి"), to: { tool: "router", situation: "consumer" } }, { label: l("Draft the complaint", "शिकायत तैयार करें", "ఫిర్యాదు తయారు చేయండి"), to: { tool: "draft", template: "consumer" } }], ask: l("What counts as a defect or a deficiency in service under the Consumer Protection Act, 2019?", "उपभोक्ता संरक्षण अधिनियम, 2019 में दोष या सेवा में कमी क्या है?", "వినియోగదారుల రక్షణ చట్టం, 2019 కింద లోపం లేదా సేవలో లోటు అంటే ఏమిటి?") },
      { id: "business", title: l("This needs a person", "इसके लिए किसी व्यक्ति की ज़रूरत है", "దీనికి ఒక వ్యక్తి కావాలి"), body: l("The Act's definition of consumer leaves out purchases for resale or a commercial purpose, with an exception we cannot apply for you.", "अधिनियम की उपभोक्ता परिभाषा में पुनर्विक्रय या व्यावसायिक ख़रीद शामिल नहीं, एक अपवाद के साथ जिसे हम लागू नहीं कर सकते।", "చట్టంలోని వినియోగదారు నిర్వచనం తిరిగి అమ్మకం లేదా వాణిజ్య కొనుగోళ్లను వదిలేస్తుంది, ఒక మినహాయింపుతో, దాన్ని మేము వర్తింపజేయలేము."), cites: ["cpa-2-7"], tools: [TOOL.legalAid] },
    ],
  },
  {
    id: "workplace-harassment",
    title: l("Harassment at work", "काम पर उत्पीड़न", "పని చోట వేధింపులు"),
    blurb: l("Three months matters", "तीन महीने अहम हैं", "మూడు నెలలు ముఖ్యం"),
    start: "kind",
    steps: [
      { id: "kind", title: l("Is it sexual harassment of a woman at work?", "क्या यह काम पर किसी महिला का यौन उत्पीड़न है?", "ఇది పని చోట మహిళపై లైంగిక వేధింపా?"), body: l("That includes unwelcome contact or advances, a demand for sexual favours, sexually coloured remarks, or showing pornography.", "इसमें अवांछित स्पर्श या प्रस्ताव, यौन अनुग्रह की माँग, यौन टिप्पणियाँ, या अश्लील सामग्री दिखाना शामिल है।", "ఇందులో అవాంఛిత స్పర్శ లేదా ప్రతిపాదనలు, లైంగిక అనుగ్రహం డిమాండ్, లైంగిక వ్యాఖ్యలు, అశ్లీలత చూపడం ఉన్నాయి."), cites: ["posh-2-n"], options: [{ label: l("Yes", "हाँ", "అవును"), next: "route" }, { label: l("No, or I am not sure", "नहीं, या मुझे पता नहीं", "లేదు, లేదా తెలియదు"), next: "other" }] },
      { id: "route", title: l("The complaint route", "शिकायत का रास्ता", "ఫిర్యాదు మార్గం"), body: l("A written complaint goes to the Internal Committee, or the Local Committee where there is none, within three months of the incident or the last incident. The Committee can extend that by up to three months.", "लिखित शिकायत आंतरिक समिति में, या वह न हो तो स्थानीय समिति में, घटना या आख़िरी घटना के तीन महीने में होती है। समिति इसे अधिकतम तीन महीने बढ़ा सकती है।", "రాతపూర్వక ఫిర్యాదు అంతర్గత కమిటీకి, లేకపోతే స్థానిక కమిటీకి, సంఘటన లేదా చివరి సంఘటన నుండి మూడు నెలల్లో. కమిటీ మూడు నెలల వరకు పొడిగించవచ్చు."), cites: ["posh-9-1", "posh-9-p", "posh-4", "posh-6"], tools: [{ label: l("Work out the date", "तारीख निकालें", "తేదీ చూడండి"), to: { tool: "router", situation: "workplace" } }, TOOL.matter, TOOL.legalAid], ask: l("What happens after I file a complaint with the Internal Committee, and what can it do during the inquiry?", "आंतरिक समिति में शिकायत के बाद क्या होता है, और जाँच के दौरान वह क्या कर सकती है?", "అంతర్గత కమిటీకి ఫిర్యాదు చేసిన తర్వాత ఏం జరుగుతుంది, విచారణ సమయంలో ఏం చేయగలదు?") },
      { id: "other", title: l("Please speak to someone", "कृपया किसी से बात करें", "దయచేసి ఎవరితోనైనా మాట్లాడండి"), body: l("Other workplace problems depend on employment law we cannot route you through here. Industrial workmen are among those covered by legal aid.", "काम की अन्य समस्याएँ उस श्रम कानून पर निर्भर हैं जिसके लिए हम यहाँ रास्ता नहीं बता सकते। औद्योगिक कामगार विधिक सहायता के दायरे में हैं।", "ఇతర పని సమస్యలు ఇక్కడ మేము మార్గం చూపలేని కార్మిక చట్టంపై ఆధారపడతాయి. పారిశ్రామిక కార్మికులు న్యాయ సహాయం పరిధిలో ఉన్నారు."), cites: ["lsa-12-f"], tools: [TOOL.legalAid], ask: l("What legal protections apply to workplace harassment that is not sexual in nature?", "जो कार्यस्थल उत्पीड़न यौन प्रकृति का नहीं है, उस पर कौन सी क़ानूनी सुरक्षा लागू होती है?", "లైంగికం కాని పని చోటి వేధింపులకు ఏ చట్టపరమైన రక్షణలు వర్తిస్తాయి?") },
    ],
  },
];

export function findStep(journey: Journey, id: string): JourneyStep | undefined {
  return journey.steps.find(step => step.id === id);
}
