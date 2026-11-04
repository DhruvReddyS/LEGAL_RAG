/**
 * C-07: interface strings and a small language store with no provider, so a
 * mount point stays one line. Law is never translated here: quoted provisions
 * come from provisions.json, in their original words, and are rendered lang="en".
 */
import { l, LANGS, type L, type Lang } from "./citizen-law/law";

export const LANG_LABELS: Record<Lang, string> = { en: "English", hi: "हिन्दी", te: "తెలుగు" };

export const UI = {
  // Shell
  toolsTitle: l("Help for your situation", "आपकी स्थिति के लिए मदद", "మీ పరిస్థితికి సహాయం"),
  toolsIntro: l("Tools that work from the law itself. They explain, cite and point you to the right door. They do not decide your case.", "ये उपकरण सीधे क़ानून पर आधारित हैं। ये समझाते हैं, स्रोत बताते हैं और सही रास्ता दिखाते हैं। ये आपके मामले का फ़ैसला नहीं करते।", "ఈ సాధనాలు నేరుగా చట్టం ఆధారంగా పనిచేస్తాయి. వివరిస్తాయి, మూలాలు చూపిస్తాయి, సరైన దారి చూపిస్తాయి. మీ కేసును నిర్ణయించవు."),
  back: l("All tools", "सभी उपकरण", "అన్ని సాధనాలు"),
  language: l("Language", "भाषा", "భాష"),
  chatStaysEnglish: l("Chat answers stay in English for now, so that each claim can be checked against its source.", "चैट के उत्तर अभी अंग्रेज़ी में ही हैं, ताकि हर दावा उसके स्रोत से जाँचा जा सके।", "ప్రతి వాదనను మూలంతో సరిచూడగలిగేలా చాట్ సమాధానాలు ప్రస్తుతం ఇంగ్లీషులోనే ఉంటాయి."),
  informationNotAdvice: l("Legal information, not legal advice. For help from a person, call NALSA on 15100.", "यह क़ानूनी जानकारी है, सलाह नहीं। किसी व्यक्ति की मदद के लिए NALSA 15100 पर कॉल करें।", "ఇది న్యాయ సమాచారం, సలహా కాదు. ఒక వ్యక్తి సహాయం కోసం NALSA 15100కు కాల్ చేయండి."),
  talkToPerson: l("Talk to a person", "किसी व्यक्ति से बात करें", "ఒక వ్యక్తితో మాట్లాడండి"),
  call15100: l("Call NALSA 15100", "NALSA 15100 पर कॉल करें", "NALSA 15100కు కాల్ చేయండి"),
  checkLegalAid: l("Check legal aid", "विधिक सहायता देखें", "న్యాయ సహాయం చూడండి"),
  askThis: l("Ask this in chat", "यह चैट में पूछें", "దీన్ని చాట్‌లో అడగండి"),
  goodQuestion: l("A good question to ask", "पूछने लायक़ अच्छा प्रश्न", "అడగదగిన మంచి ప్రశ్న"),
  source: l("Source", "स्रोत", "మూలం"),
  sources: l("The law behind this", "इसके पीछे का क़ानून", "దీని వెనుక చట్టం"),
  inOriginal: l("Quoted in its original words", "मूल शब्दों में उद्धृत", "అసలు మాటల్లో ఉల్లేఖించబడింది"),
  page: l("page", "पृष्ठ", "పేజీ"),
  openOfficial: l("Open the official text", "आधिकारिक पाठ खोलें", "అధికారిక పాఠం తెరవండి"),
  startOver: l("Start again", "फिर से शुरू करें", "మళ్లీ మొదలుపెట్టండి"),
  stepBack: l("Back", "पीछे", "వెనుకకు"),
  yes: l("Yes", "हाँ", "అవును"),
  no: l("No", "नहीं", "లేదు"),
  notSure: l("Not sure", "पता नहीं", "తెలియదు"),
  loading: l("Loading…", "लोड हो रहा है…", "లోడ్ అవుతోంది…"),
  save: l("Save", "सहेजें", "సేవ్ చేయండి"),
  cancel: l("Cancel", "रद्द करें", "రద్దు చేయండి"),
  remove: l("Remove", "हटाएँ", "తీసివేయండి"),
  addToMatter: l("Add to My matter", "मेरा मामला में जोड़ें", "నా విషయంలో చేర్చండి"),

  // Tool names
  toolJourneys: l("What is happening?", "क्या हो रहा है?", "ఏం జరుగుతోంది?"),
  toolJourneysBlurb: l("Answer a few questions and get to the right tool or question", "कुछ प्रश्नों के उत्तर दें और सही उपकरण या प्रश्न तक पहुँचें", "కొన్ని ప్రశ్నలకు జవాబిచ్చి సరైన సాధనం లేదా ప్రశ్నకు చేరండి"),
  toolRights: l("Know your rights", "अपने अधिकार जानें", "మీ హక్కులు తెలుసుకోండి"),
  toolRightsBlurb: l("Arrest, police stops, summons, search. Printable, and works offline", "गिरफ़्तारी, पुलिस का रोकना, समन, तलाशी। प्रिंट करें, ऑफ़लाइन भी", "అరెస్టు, పోలీసులు ఆపడం, సమన్లు, సోదా. ప్రింట్ చేయవచ్చు, ఆఫ్‌లైన్‌లోనూ"),
  toolRouter: l("Where to go, by when", "कहाँ जाएँ, कब तक", "ఎక్కడికి వెళ్లాలి, ఎప్పటిలోగా"),
  toolRouterBlurb: l("The forum, the time limit and the cost, with the provision behind each", "मंच, समय-सीमा और ख़र्च, हर एक के पीछे के प्रावधान सहित", "వేదిక, గడువు, ఖర్చు, ప్రతి దాని వెనుక నిబంధనతో"),
  toolNotice: l("Explain a notice", "नोटिस समझाएँ", "నోటీసు వివరించండి"),
  toolNoticeBlurb: l("What it demands, the deadline and the risk, from a notice or summons", "नोटिस या समन से: क्या माँगा गया, समय-सीमा और जोखिम", "నోటీసు లేదా సమన్ల నుండి: ఏం కోరుతోంది, గడువు, ప్రమాదం"),
  toolDraft: l("Draft a document", "दस्तावेज़ तैयार करें", "పత్రం తయారు చేయండి"),
  toolDraftBlurb: l("Complaint, RTI, consumer complaint, legal notice. Stays on your device", "शिकायत, RTI, उपभोक्ता शिकायत, क़ानूनी नोटिस। आपके डिवाइस पर ही", "ఫిర్యాదు, RTI, వినియోగదారు ఫిర్యాదు, లీగల్ నోటీసు. మీ పరికరంలోనే"),
  toolLegalAid: l("Free legal aid", "निःशुल्क विधिक सहायता", "ఉచిత న్యాయ సహాయం"),
  toolLegalAidBlurb: l("Who may qualify, and how to reach a person", "कौन पात्र हो सकता है, और व्यक्ति तक कैसे पहुँचें", "ఎవరు అర్హులు కావచ్చు, ఒక వ్యక్తిని ఎలా చేరాలి"),
  toolMatter: l("My matter", "मेरा मामला", "నా విషయం"),
  toolMatterBlurb: l("Your own dates and reminders", "आपकी अपनी तारीखें और अनुस्मारक", "మీ తేదీలు, రిమైండర్లు"),

  // Rights
  rightsLead: l("Each point is in plain words, with the law it rests on underneath. Print it or save a copy for your phone.", "हर बिंदु में सरल शब्द, और नीचे वह क़ानून जिस पर वह आधारित है। इसे प्रिंट करें या फ़ोन के लिए प्रति सहेजें।", "ప్రతి అంశంలో సరళమైన మాటలు, కింద దానికి ఆధారమైన చట్టం. ప్రింట్ చేయండి లేదా ఫోన్ కోసం ప్రతి సేవ్ చేయండి."),
  print: l("Print", "प्रिंट करें", "ప్రింట్ చేయండి"),
  saveCopy: l("Save a copy", "प्रति सहेजें", "ప్రతి సేవ్ చేయండి"),
  offlineReady: l("This page is saved on this device and opens without internet.", "यह पृष्ठ इस डिवाइस पर सहेजा गया है और इंटरनेट के बिना खुलता है।", "ఈ పేజీ ఈ పరికరంలో సేవ్ అయింది, ఇంటర్నెట్ లేకుండా తెరుచుకుంటుంది."),
  numbersTitle: l("Numbers to keep", "संभालकर रखने वाले नंबर", "ఉంచుకోవలసిన నంబర్లు"),
  rightsPublicTitle: l("Your rights with the police and courts", "पुलिस और अदालत के साथ आपके अधिकार", "పోలీసులు, కోర్టులతో మీ హక్కులు"),
  signIn: l("Sign in to Corpusil", "Corpusil में साइन इन करें", "Corpusilలో సైన్ ఇన్ చేయండి"),
  rightsLastChecked: l("Checked against the BNSS 2023 and the Constitution of India held in our corpus. Later amendments may apply.", "हमारे संग्रह में मौजूद BNSS 2023 और भारत के संविधान से जाँचा गया। बाद के संशोधन लागू हो सकते हैं।", "మా సేకరణలోని BNSS 2023, భారత రాజ్యాంగంతో సరిచూశాం. తర్వాతి సవరణలు వర్తించవచ్చు."),

  // Journeys
  journeysLead: l("Pick the closest one. You can stop at any point.", "सबसे निकट वाला चुनें। आप कभी भी रुक सकते हैं।", "దగ్గరగా ఉన్నది ఎంచుకోండి. ఎప్పుడైనా ఆపవచ్చు."),

  // Router
  routerLead: l("We only show a date when we can cite the provision. If you are not sure of something, we stop and send you to a person, because a wrong limitation date can lose a case.", "हम तारीख तभी दिखाते हैं जब प्रावधान बता सकें। किसी बात पर संदेह हो तो हम रुककर आपको किसी व्यक्ति के पास भेजते हैं, क्योंकि ग़लत समय-सीमा से मामला हाथ से जा सकता है।", "నిబంధన చూపగలిగితేనే తేదీ చూపిస్తాం. ఏదైనా సందేహం ఉంటే ఆగి ఒక వ్యక్తి వద్దకు పంపుతాం, ఎందుకంటే తప్పు గడువు కేసును పోగొట్టవచ్చు."),
  routerPick: l("What is your situation?", "आपकी स्थिति क्या है?", "మీ పరిస్థితి ఏమిటి?"),
  routerOther: l("Something else, or a case already in court", "कुछ और, या अदालत में पहले से चल रहा मामला", "మరేదైనా, లేదా ఇప్పటికే కోర్టులో ఉన్న కేసు"),
  whereToGo: l("Where to go", "कहाँ जाएँ", "ఎక్కడికి వెళ్లాలి"),
  byWhen: l("By when", "कब तक", "ఎప్పటిలోగా"),
  whatItCosts: l("What it costs", "ख़र्च", "ఖర్చు"),
  alsoKnow: l("Also worth knowing", "यह भी जानें", "ఇది కూడా తెలుసుకోండి"),
  enterDate: l("Enter the date to work this out", "गणना के लिए तारीख दर्ज करें", "లెక్కించడానికి తేదీ నమోదు చేయండి"),
  lastDay: l("Last day, by plain counting", "आख़िरी दिन, सीधी गिनती से", "చివరి రోజు, సాధారణ లెక్కతో"),
  datePassed: l("This date has passed. Speak to a person now: there may still be options.", "यह तारीख बीत चुकी है। अभी किसी व्यक्ति से बात करें: अब भी रास्ते हो सकते हैं।", "ఈ తేదీ దాటింది. ఇప్పుడే ఒక వ్యక్తితో మాట్లాడండి: ఇంకా మార్గాలు ఉండవచ్చు."),
  countingNote: l("This is a plain count from your date, and it does not apply any exclusion the law may allow. Do not leave it to the last day. Check it with legal aid or a lawyer.", "यह आपकी तारीख से सीधी गिनती है, और क़ानून की किसी छूट को नहीं जोड़ती। आख़िरी दिन तक न छोड़ें। विधिक सहायता या वकील से जाँच लें।", "ఇది మీ తేదీ నుండి సాధారణ లెక్క, చట్టం అనుమతించే మినహాయింపులు కలపలేదు. చివరి రోజు వరకు ఆగవద్దు. న్యాయ సహాయం లేదా న్యాయవాదితో సరిచూసుకోండి."),
  weStopHere: l("We stop here", "हम यहाँ रुकते हैं", "మేము ఇక్కడ ఆగుతాం"),
  noDateFromUs: l("No date from us", "हमारी ओर से कोई तारीख नहीं", "మా నుండి తేదీ లేదు"),

  // Notice
  noticeLead: l("Paste the text, or upload a photo or PDF. You check and mask personal details first, and only the masked text goes on to be explained.", "पाठ चिपकाएँ, या फ़ोटो या PDF अपलोड करें। पहले आप निजी विवरण जाँचकर छिपाते हैं, और केवल छिपा हुआ पाठ समझाने के लिए जाता है।", "పాఠం అతికించండి, లేదా ఫోటో లేదా PDF అప్‌లోడ్ చేయండి. ముందుగా మీరు వ్యక్తిగత వివరాలు చూసి దాచుతారు, దాచిన పాఠం మాత్రమే వివరణకు వెళ్తుంది."),
  noticePastePlaceholder: l("Paste the notice or summons here…", "नोटिस या समन यहाँ चिपकाएँ…", "నోటీసు లేదా సమన్లు ఇక్కడ అతికించండి…"),
  noticeTextLabel: l("Text of the notice", "नोटिस का पाठ", "నోటీసు పాఠం"),
  uploadFile: l("Upload a PDF or photo", "PDF या फ़ोटो अपलोड करें", "PDF లేదా ఫోటో అప్‌లోడ్ చేయండి"),
  reading: l("Reading the file…", "फ़ाइल पढ़ी जा रही है…", "ఫైల్ చదువుతోంది…"),
  uploadPrivacy: l("A file goes to this server only to read its text, and the original is discarded. A pasted notice is checked on this device first.", "फ़ाइल केवल पाठ पढ़ने के लिए इस सर्वर पर जाती है, और मूल हटा दी जाती है। चिपकाया गया नोटिस पहले इसी डिवाइस पर जाँचा जाता है।", "ఫైల్ పాఠం చదవడానికి మాత్రమే ఈ సర్వర్‌కు వెళ్తుంది, అసలు తొలగించబడుతుంది. అతికించిన నోటీసు ముందుగా ఈ పరికరంలోనే తనిఖీ అవుతుంది."),
  reviewDetails: l("Check personal details", "निजी विवरण जाँचें", "వ్యక్తిగత వివరాలు చూడండి"),
  explainThis: l("Explain this notice", "यह नोटिस समझाएँ", "ఈ నోటీసు వివరించండి"),
  explaining: l("Reading the notice…", "नोटिस पढ़ा जा रहा है…", "నోటీసు చదువుతోంది…"),
  whatThisIs: l("What this is", "यह क्या है", "ఇది ఏమిటి"),
  whatItDemands: l("What it demands, in its own words", "यह क्या माँगता है, उसी के शब्दों में", "ఇది ఏం కోరుతోంది, దాని మాటల్లోనే"),
  noDemands: l("We could not pick out a clear demand. Read the original closely.", "हम स्पष्ट माँग नहीं पहचान सके। मूल को ध्यान से पढ़ें।", "స్పష్టమైన డిమాండ్ గుర్తించలేకపోయాం. అసలును జాగ్రత్తగా చదవండి."),
  theDeadline: l("The deadline", "समय-सीमा", "గడువు"),
  lawSays: l("What the law says", "क़ानून क्या कहता है", "చట్టం ఏం చెబుతోంది"),
  noticeSays: l("What the notice says", "नोटिस क्या कहता है", "నోటీసు ఏం చెబుతోంది"),
  noDeadlineFound: l("We found no day count in this notice. Check the original.", "इस नोटिस में दिनों की गिनती नहीं मिली। मूल जाँचें।", "ఈ నోటీసులో రోజుల లెక్క కనిపించలేదు. అసలు చూడండి."),
  receivedOn: l("The date you received it", "आपको मिलने की तारीख", "మీకు అందిన తేదీ"),
  dueIf: l("Counting from the day you received it, that would be", "आपको मिलने के दिन से गिनने पर यह होगा", "మీకు అందిన రోజు నుండి లెక్కిస్తే ఇది"),
  checkFromDate: l("The notice may count from a different date. Check its wording.", "नोटिस किसी और तारीख से गिन सकता है। उसके शब्द जाँचें।", "నోటీసు వేరే తేదీ నుండి లెక్కించవచ్చు. దాని మాటలు చూడండి."),
  datesInIt: l("Dates in it", "इसमें तारीखें", "ఇందులో తేదీలు"),
  amountsInIt: l("Amounts in it", "इसमें राशियाँ", "ఇందులో మొత్తాలు"),
  theRisk: l("The risk", "जोखिम", "ప్రమాదం"),
  sectionsItCites: l("Sections it cites", "इसमें उद्धृत धाराएँ", "ఇందులో ఉదహరించిన సెక్షన్లు"),
  replacedLabel: l("Replaced on", "बदला गया", "మార్చబడింది"),
  nowIs: l("now", "अब", "ఇప్పుడు"),
  noSuccessor: l("The new code did not carry this forward. Ask a lawyer.", "नई संहिता में यह नहीं रखा गया। वकील से पूछें।", "కొత్త కోడ్‌లో ఇది కొనసాగలేదు. న్యాయవాదిని అడగండి."),
  noMappingKnown: l("We have no mapping for this section. Check it.", "इस धारा का हमारे पास मानचित्रण नहीं। इसे जाँचें।", "ఈ సెక్షన్‌కు మా వద్ద మ్యాపింగ్ లేదు. సరిచూడండి."),
  elementsChanged: l("The offence's elements changed", "अपराध के तत्व बदले", "నేర అంశాలు మారాయి"),
  notChecked: l("We have not checked this one", "हमने इसे नहीं जाँचा", "దీన్ని మేము తనిఖీ చేయలేదు"),
  plainWords: l("Rewrite it in plain words", "इसे सरल शब्दों में लिखें", "సరళమైన మాటల్లో రాయండి"),
  plainWordsHint: l("A language model restates the notice. It can take a few minutes. We keep it only if it stays inside the notice.", "भाषा मॉडल नोटिस को दोबारा कहता है। कुछ मिनट लग सकते हैं। हम इसे तभी रखते हैं जब यह नोटिस के भीतर रहे।", "భాషా నమూనా నోటీసును తిరిగి చెబుతుంది. కొన్ని నిమిషాలు పట్టవచ్చు. నోటీసు పరిధిలో ఉంటేనే ఉంచుతాం."),
  plainWorking: l("Rewriting…", "लिखा जा रहा है…", "రాస్తోంది…"),
  plainLabel: l("Machine-written. Check it against the notice.", "मशीन से लिखा गया। नोटिस से जाँचें।", "యంత్రం రాసింది. నోటీసుతో సరిచూడండి."),
  plainUnavailable: l("The plain-language model is not available right now. The reading above does not depend on it.", "सरल भाषा मॉडल अभी उपलब्ध नहीं। ऊपर की जानकारी उस पर निर्भर नहीं है।", "సరళ భాషా నమూనా ఇప్పుడు అందుబాటులో లేదు. పై వివరణ దానిపై ఆధారపడదు."),
  plainRejected: l("The rewrite strayed from the notice, so we discarded it.", "पुनर्लेखन नोटिस से भटक गया, इसलिए हमने उसे हटा दिया।", "తిరిగి రాసినది నోటీసు నుండి పక్కకు వెళ్లింది, కాబట్టి తొలగించాం."),
  explainAnother: l("Explain another", "दूसरा समझाएँ", "మరొకటి వివరించండి"),
  somethingWrong: l("That did not work. Check your connection and try again.", "यह नहीं हुआ। कनेक्शन जाँचकर फिर कोशिश करें।", "ఇది పని చేయలేదు. కనెక్షన్ చూసి మళ్లీ ప్రయత్నించండి."),
  fileTooBig: l("Choose a file smaller than 10 MiB.", "10 MiB से छोटी फ़ाइल चुनें।", "10 MiB కంటే చిన్న ఫైల్ ఎంచుకోండి."),

  // Redaction
  redactionTitle: l("Remove personal details first", "पहले निजी विवरण हटाएँ", "ముందు వ్యక్తిగత వివరాలు తీసివేయండి"),
  redactionLead: l("Highlighted details will be replaced before anything is sent. Click one to keep it. To mask anything else, select the words and press “Mask selected text”. This runs on your device.", "हाइलाइट किए गए विवरण भेजने से पहले बदल दिए जाएँगे। रखने के लिए उस पर क्लिक करें। कुछ और छिपाने के लिए शब्द चुनकर “चुना पाठ छिपाएँ” दबाएँ। यह आपके डिवाइस पर चलता है।", "హైలైట్ చేసిన వివరాలు పంపే ముందు మార్చబడతాయి. ఉంచాలంటే దానిపై క్లిక్ చేయండి. ఇంకేదైనా దాచాలంటే పదాలు ఎంచుకుని “ఎంచుకున్న పాఠం దాచండి” నొక్కండి. ఇది మీ పరికరంలో నడుస్తుంది."),
  redactionNone: l("We found nothing to mask, but we can miss things. Read it through, and select anything private.", "हमें छिपाने लायक़ कुछ नहीं मिला, पर हमसे छूट सकता है। पढ़ लें, और कुछ निजी हो तो चुनें।", "దాచవలసినది ఏదీ కనిపించలేదు, కానీ మేము తప్పిపోవచ్చు. చదివి చూడండి, ప్రైవేట్ ఉంటే ఎంచుకోండి."),
  maskSelected: l("Mask selected text", "चुना पाठ छिपाएँ", "ఎంచుకున్న పాఠం దాచండి"),
  selectFirst: l("Select some words in the text first.", "पहले पाठ में कुछ शब्द चुनें।", "ముందు పాఠంలో కొన్ని పదాలు ఎంచుకోండి."),
  masked: l("Masked", "छिपा हुआ", "దాచబడింది"),
  kept: l("Kept", "रखा हुआ", "ఉంచబడింది"),
  undoManual: l("Clear my selections", "मेरे चयन हटाएँ", "నా ఎంపికలు తీసివేయండి"),
  useMasked: l("Use the masked text", "छिपा हुआ पाठ उपयोग करें", "దాచిన పాఠం ఉపయోగించండి"),
  skipFile: l("Do not use this file", "यह फ़ाइल उपयोग न करें", "ఈ ఫైల్ ఉపయోగించవద్దు"),
  kind_aadhaar: l("Aadhaar", "आधार", "ఆధార్"),
  kind_pan: l("PAN", "पैन", "పాన్"),
  kind_phone: l("Phone", "फ़ोन", "ఫోన్"),
  kind_email: l("Email", "ईमेल", "ఈమెయిల్"),
  kind_account: l("Account", "खाता", "ఖాతా"),
  kind_address: l("Address", "पता", "చిరునామా"),

  // Drafts
  draftLead: l("Fill in what you know. Nothing here is sent to our server. Anything left empty stays a visible blank in the draft.", "जो पता है भरें। यहाँ का कुछ भी हमारे सर्वर पर नहीं जाता। ख़ाली छोड़ा गया ड्राफ़्ट में दिखाई देने वाला रिक्त स्थान रहेगा।", "తెలిసినది నింపండి. ఇక్కడిది ఏదీ మా సర్వర్‌కు వెళ్లదు. ఖాళీగా వదిలినది డ్రాఫ్ట్‌లో కనిపించే ఖాళీగా ఉంటుంది."),
  draftPick: l("What do you need to write?", "आपको क्या लिखना है?", "మీరు ఏం రాయాలి?"),
  draftPreview: l("Your draft", "आपका ड्राफ़्ट", "మీ డ్రాఫ్ట్"),
  draftEnglishNote: l("The draft is in English because that is what goes to the office. The RTI Act also allows Hindi or the official language of the area.", "ड्राफ़्ट अंग्रेज़ी में है क्योंकि वही दफ़्तर जाता है। RTI अधिनियम हिंदी या क्षेत्र की राजभाषा की भी अनुमति देता है।", "డ్రాఫ్ట్ ఇంగ్లీషులో ఉంది, అదే కార్యాలయానికి వెళ్తుంది. RTI చట్టం హిందీ లేదా ప్రాంత అధికార భాషకు కూడా అనుమతిస్తుంది."),
  copy: l("Copy", "कॉपी करें", "కాపీ చేయండి"),
  copied: l("Copied", "कॉपी हो गया", "కాపీ అయింది"),
  download: l("Download", "डाउनलोड करें", "డౌన్‌లోడ్ చేయండి"),
  blanksLeft: l("Still blank", "अभी रिक्त", "ఇంకా ఖాళీ"),
  allFilled: l("All fields filled. Read it through before you use it.", "सभी भरे गए। उपयोग से पहले पढ़ लें।", "అన్నీ నింపారు. ఉపయోగించే ముందు చదవండి."),
  draftNotFiled: l("This is a draft. We do not file anything for you.", "यह ड्राफ़्ट है। हम आपके लिए कुछ दाखिल नहीं करते।", "ఇది డ్రాఫ్ట్. మేము మీ కోసం ఏదీ దాఖలు చేయము."),

  // Legal aid
  aidLead: l("Section 12 of the Legal Services Authorities Act lists who may get free legal services. Tick anything that fits you or the person you are helping.", "विधिक सेवा प्राधिकरण अधिनियम की धारा 12 बताती है कि निःशुल्क विधिक सेवा किसे मिल सकती है। जो आप या जिसकी मदद कर रहे हैं उस पर लागू हो, उसे चुनें।", "న్యాయ సేవల ప్రాధికార సంస్థల చట్టం సెక్షన్ 12 ఉచిత న్యాయ సేవలు ఎవరికి అందవచ్చో చెబుతుంది. మీకు లేదా మీరు సహాయం చేస్తున్న వ్యక్తికి వర్తించేవి ఎంచుకోండి."),
  aidHowToReach: l("How to reach them", "उन तक कैसे पहुँचें", "వారిని ఎలా చేరాలి"),
  aidMatches: l("What you ticked", "आपने क्या चुना", "మీరు ఎంచుకున్నవి"),

  // Matter
  matterLead: l("Your own list of dates. Only you can see it. A date here is what you recorded, so check it against the paper it came from.", "आपकी अपनी तारीखों की सूची। इसे केवल आप देख सकते हैं। यहाँ की तारीख वही है जो आपने लिखी, इसलिए मूल काग़ज़ से जाँचें।", "మీ తేదీల జాబితా. మీరు మాత్రమే చూడగలరు. ఇక్కడి తేదీ మీరు రాసినదే, కాబట్టి అసలు కాగితంతో సరిచూడండి."),
  matterEmpty: l("Nothing yet. Add a hearing, a reply date or a limitation date.", "अभी कुछ नहीं। सुनवाई, उत्तर या समय-सीमा की तारीख जोड़ें।", "ఇంకా ఏమీ లేదు. విచారణ, జవాబు లేదా గడువు తేదీ చేర్చండి."),
  matterNewTitle: l("What is this date for?", "यह तारीख किसलिए है?", "ఈ తేదీ దేనికి?"),
  matterDue: l("Date", "तारीख", "తేదీ"),
  matterRemind: l("Remind me this many days before", "इतने दिन पहले याद दिलाएँ", "ఇన్ని రోజుల ముందు గుర్తు చేయండి"),
  matterNotes: l("Notes (optional)", "टिप्पणी (वैकल्पिक)", "గమనికలు (ఐచ్ఛికం)"),
  matterAdd: l("Add date", "तारीख जोड़ें", "తేదీ చేర్చండి"),
  matterDone: l("Done", "हो गया", "పూర్తయింది"),
  matterMarkDone: l("Mark done", "पूरा करें", "పూర్తయినట్లు గుర్తించండి"),
  matterUndo: l("Not done", "पूरा नहीं", "పూర్తి కాలేదు"),
  matterToday: l("Today", "आज", "ఈరోజు"),
  matterCalendar: l("Add to calendar", "कैलेंडर में जोड़ें", "క్యాలెండర్‌లో చేర్చండి"),
  matterBasis: l("Basis", "आधार", "ఆధారం"),
  matterCalendarHint: l("Reminders show here when you open Corpusil. For a phone alert, add the date to your calendar.", "अनुस्मारक Corpusil खोलने पर यहाँ दिखते हैं। फ़ोन पर सूचना के लिए तारीख कैलेंडर में जोड़ें।", "Corpusil తెరిచినప్పుడు రిమైండర్లు ఇక్కడ కనిపిస్తాయి. ఫోన్ అలర్ట్ కోసం తేదీని క్యాలెండర్‌లో చేర్చండి."),
  attentionTitle: l("Coming up", "आने वाली तारीखें", "రాబోయే తేదీలు"),
  couldNotLoad: l("Your dates could not be loaded. Check your connection.", "आपकी तारीखें लोड नहीं हुईं। कनेक्शन जाँचें।", "మీ తేదీలు లోడ్ కాలేదు. కనెక్షన్ చూడండి."),
  needTitleDate: l("Give the date a name and choose a day.", "तारीख को नाम दें और दिन चुनें।", "తేదీకి పేరు ఇచ్చి రోజు ఎంచుకోండి."),

  // Chat
  safetyLabel: l("Safety guidance", "सुरक्षा मार्गदर्शन", "భద్రతా మార్గదర్శకం"),
  safetyHelp: l("This reply comes from a safety check, not from a search of legal sources.", "यह उत्तर सुरक्षा जाँच से है, क़ानूनी स्रोतों की खोज से नहीं।", "ఈ సమాధానం భద్రతా తనిఖీ నుండి వచ్చింది, న్యాయ మూలాల శోధన నుండి కాదు."),
  refusalLabel: l("A question for a person", "यह प्रश्न किसी व्यक्ति के लिए", "ఈ ప్రశ్న ఒక వ్యక్తి కోసం"),
  refusalHelp: l("This is a decision about your own case, so it needs a lawyer who knows the file. The reply did not come from a search of legal sources.", "यह आपके अपने मामले का निर्णय है, इसलिए इसके लिए फ़ाइल जानने वाला वकील चाहिए। उत्तर क़ानूनी स्रोतों की खोज से नहीं आया।", "ఇది మీ కేసు నిర్ణయం, దీనికి ఫైల్ తెలిసిన న్యాయవాది కావాలి. సమాధానం న్యాయ మూలాల శోధన నుండి రాలేదు."),
  humanNudge: l("We could not support a full answer from our sources. A person can look at your situation.", "हमारे स्रोतों से पूरा उत्तर नहीं बन सका। कोई व्यक्ति आपकी स्थिति देख सकता है।", "మా మూలాల నుండి పూర్తి సమాధానం ఇవ్వలేకపోయాం. ఒక వ్యక్తి మీ పరిస్థితి చూడగలరు."),
  sessionExpired: l("Your session ended. Sign in again to carry on. What you were typing is saved.", "आपका सत्र समाप्त हो गया। जारी रखने के लिए फिर साइन इन करें। जो आप लिख रहे थे वह सहेजा गया है।", "మీ సెషన్ ముగిసింది. కొనసాగడానికి మళ్లీ సైన్ ఇన్ చేయండి. మీరు రాస్తున్నది సేవ్ అయింది."),
  retrying: l("Connection interrupted. Retrying", "कनेक्शन टूटा। फिर कोशिश हो रही है", "కనెక్షన్ తెగింది. మళ్లీ ప్రయత్నిస్తోంది"),
  loadMore: l("Load older chats", "पुरानी चैट लोड करें", "పాత చాట్‌లు లోడ్ చేయండి"),
  welcomeHeading: l("Let’s make sense of the law.", "आइए क़ानून को समझें।", "చట్టాన్ని అర్థం చేసుకుందాం."),
  welcomeLead: l("Ask in your own words. We’ll start from there.", "अपने शब्दों में पूछें। हम वहीं से शुरू करेंगे।", "మీ మాటల్లో అడగండి. అక్కడి నుండి మొదలుపెడతాం."),
  openTools: l("Or start from your situation", "या अपनी स्थिति से शुरू करें", "లేదా మీ పరిస్థితి నుండి మొదలుపెట్టండి"),
  beforeRely: l("Before you rely on this", "इस पर भरोसा करने से पहले", "దీనిపై ఆధారపడే ముందు"),
  backToChat: l("Back to chat", "चैट पर वापस", "చాట్‌కు తిరిగి"),
  newChat: l("New chat", "नई चैट", "కొత్త చాట్"),
  gettingStarted: l("Getting started", "शुरुआत", "ప్రారంభం"),
  settings: l("Settings", "सेटिंग", "సెట్టింగ్‌లు"),
  recentChats: l("Recent chats", "हाल की चैट", "ఇటీవలి చాట్‌లు"),
} satisfies Record<string, L>;

export type UiKey = keyof typeof UI;

export function t(key: UiKey, lang: Lang): string {
  return UI[key][lang];
}

/** A calendar date in words, so 03/02/2026 can never be read the wrong way round. */
export function formatDate(iso: string, lang: Lang): string {
  const date = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(`${lang}-IN`, { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(date);
}

export const LANG_STORAGE_KEY = "corpusil-language";

export function parseLang(value: unknown): Lang {
  return typeof value === "string" && (LANGS as string[]).includes(value) ? (value as Lang) : "en";
}

let current: Lang | null = null;
const listeners = new Set<() => void>();

export function getLang(): Lang {
  if (current) return current;
  if (typeof window === "undefined") return "en";
  try {
    current = parseLang(window.localStorage.getItem(LANG_STORAGE_KEY));
  } catch {
    current = "en";
  }
  return current;
}

export function setLang(lang: Lang): void {
  current = lang;
  try { window.localStorage.setItem(LANG_STORAGE_KEY, lang); } catch { /* storage disabled */ }
  listeners.forEach(listener => listener());
}

export function subscribeLang(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
