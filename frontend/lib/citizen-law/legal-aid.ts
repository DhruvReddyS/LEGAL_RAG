/**
 * C-09: who may qualify for free legal services, from Legal Services
 * Authorities Act 1987 s.12 and s.13. Income is deliberately not computed: the
 * Act's figure is a floor that each State raises by its own rules, and the
 * corpus does not hold those rules. Helpline source: NALSA DAWN Scheme 2025.
 */
import { l, type L } from "./law";

export type AidCategory = { id: string; clause: string; label: L; cite: string };

export const AID_CATEGORIES: AidCategory[] = [
  { id: "sc-st", clause: "s.12(a)", cite: "lsa-12-a", label: l("A member of a Scheduled Caste or Scheduled Tribe", "अनुसूचित जाति या जनजाति के सदस्य", "షెడ్యూల్డ్ కులం లేదా తెగ సభ్యులు") },
  { id: "trafficking", clause: "s.12(b)", cite: "lsa-12-b", label: l("A victim of human trafficking or forced labour (begar)", "मानव तस्करी या बेगार के पीड़ित", "మానవ అక్రమ రవాణా లేదా వెట్టి చాకిరి బాధితులు") },
  { id: "woman-child", clause: "s.12(c)", cite: "lsa-12-c", label: l("A woman or a child", "महिला या बच्चा", "మహిళ లేదా పిల్లలు") },
  { id: "disability", clause: "s.12(d)", cite: "lsa-12-d", label: l("A person with a disability", "दिव्यांग व्यक्ति", "వైకల్యం ఉన్న వ్యక్తి") },
  { id: "disaster", clause: "s.12(e)", cite: "lsa-12-e", label: l("Facing undeserved want, such as a mass disaster, ethnic violence, caste atrocity, flood, drought, earthquake or industrial disaster", "अनुचित अभाव में, जैसे सामूहिक आपदा, जातीय हिंसा, जाति अत्याचार, बाढ़, सूखा, भूकंप या औद्योगिक आपदा", "అనర్హ కష్టంలో, ఉదా. సామూహిక విపత్తు, జాతి హింస, కుల దౌర్జన్యం, వరద, కరువు, భూకంపం లేదా పారిశ్రామిక విపత్తు") },
  { id: "workman", clause: "s.12(f)", cite: "lsa-12-f", label: l("An industrial workman", "औद्योगिक कामगार", "పారిశ్రామిక కార్మికుడు") },
  { id: "custody", clause: "s.12(g)", cite: "lsa-12-g", label: l("In custody, including a protective home, juvenile home or psychiatric hospital", "हिरासत में, जिसमें संरक्षण गृह, किशोर गृह या मनोरोग अस्पताल शामिल", "నిర్బంధంలో, రక్షణ గృహం, బాల గృహం లేదా మానసిక ఆసుపత్రితో సహా") },
  { id: "income", clause: "s.12(h)", cite: "lsa-12-h", label: l("On a low income, below the limit your State has set", "कम आय, आपके राज्य की तय सीमा से नीचे", "తక్కువ ఆదాయం, మీ రాష్ట్రం నిర్ణయించిన పరిమితి కంటే తక్కువ") },
];

export type AidResult =
  | { status: "none_selected" }
  | { status: "income_only"; cites: string[] }
  | { status: "may_qualify"; clauses: AidCategory[]; cites: string[] };

/** "May qualify", never "entitled": s.13(1) leaves the prima facie decision to the Authority. */
export function checkLegalAid(selected: string[]): AidResult {
  const chosen = AID_CATEGORIES.filter(category => selected.includes(category.id));
  if (!chosen.length) return { status: "none_selected" };
  if (chosen.length === 1 && chosen[0].id === "income") {
    return { status: "income_only", cites: ["lsa-12-h", "lsa-13-2", "lsa-13-1"] };
  }
  return { status: "may_qualify", clauses: chosen, cites: ["lsa-12", ...chosen.map(item => item.cite), "lsa-13-1"] };
}

export const AID_TEXT = {
  noneSelected: l("None of these may fit, or you may not be sure. Ask anyway: 15100 is free to call and a person can look at your situation.", "शायद इनमें से कोई लागू न हो, या आप निश्चित न हों। फिर भी पूछें: 15100 पर एक व्यक्ति आपकी स्थिति देख सकता है।", "వీటిలో ఏదీ సరిపోకపోవచ్చు, లేదా మీకు స్పష్టత లేకపోవచ్చు. అయినా అడగండి: 15100లో ఒక వ్యక్తి మీ పరిస్థితి చూడగలరు."),
  mayQualify: l("You may qualify for free legal services, if you have to file or defend a case. The Authority must also be satisfied that you have a prima facie case, so this is not a promise.", "यदि आपको मामला दायर करना या उसका बचाव करना है तो आप निःशुल्क विधिक सेवा के पात्र हो सकते हैं। प्राधिकरण को यह भी संतुष्ट होना होगा कि आपका मामला प्रथम दृष्टया बनता है, इसलिए यह वादा नहीं है।", "మీరు కేసు వేయాల్సి లేదా వాదించాల్సి ఉంటే ఉచిత న్యాయ సేవలకు అర్హులు కావచ్చు. మీ కేసు ప్రాథమికంగా ఉందని ప్రాధికార సంస్థ కూడా సంతృప్తి చెందాలి, కాబట్టి ఇది హామీ కాదు."),
  incomeOnly: l("The Act's figure is a base that each State may raise, and we do not hold your State's current limit, so we will not tell you whether your income qualifies. The District Legal Services Authority can. An affidavit about your income may be regarded as enough, unless the Authority has reason to disbelieve it.", "अधिनियम का आँकड़ा आधार है जिसे हर राज्य बढ़ा सकता है, और आपके राज्य की वर्तमान सीमा हमारे पास नहीं है, इसलिए हम नहीं बताएँगे कि आपकी आय पात्र है या नहीं। ज़िला विधिक सेवा प्राधिकरण बता सकता है। आय का शपथपत्र पर्याप्त माना जा सकता है, जब तक प्राधिकरण के पास अविश्वास का कारण न हो।", "చట్టంలోని సంఖ్య ఆధారం మాత్రమే, ప్రతి రాష్ట్రం పెంచవచ్చు, మీ రాష్ట్ర ప్రస్తుత పరిమితి మా వద్ద లేదు, కాబట్టి మీ ఆదాయం అర్హమో మేము చెప్పము. జిల్లా న్యాయ సేవల ప్రాధికార సంస్థ చెప్పగలదు. ఆదాయంపై అఫిడవిట్ సరిపోతుందని భావించవచ్చు, సంస్థకు నమ్మకపోవడానికి కారణం ఉంటే తప్ప."),
  reach: l("Call the NALSA helpline on 15100, or go to the District Legal Services Authority (DLSA) office in your district. NALSA's website is nalsa.gov.in.", "NALSA हेल्पलाइन 15100 पर कॉल करें, या अपने ज़िले के ज़िला विधिक सेवा प्राधिकरण (DLSA) कार्यालय जाएँ। NALSA की वेबसाइट nalsa.gov.in है।", "NALSA హెల్ప్‌లైన్ 15100కు కాల్ చేయండి, లేదా మీ జిల్లా న్యాయ సేవల ప్రాధికార సంస్థ (DLSA) కార్యాలయానికి వెళ్లండి. NALSA వెబ్‌సైట్ nalsa.gov.in."),
  take: l("Take any notice, summons or papers you have, and a note of the dates.", "जो भी नोटिस, समन या काग़ज़ हों और तारीखों का नोट साथ ले जाएँ।", "మీ వద్ద ఉన్న నోటీసు, సమన్లు లేదా కాగితాలు, తేదీల వివరాలు తీసుకెళ్లండి."),
};
