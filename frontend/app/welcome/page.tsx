import type { Metadata } from "next";
import { ArrowRight, BriefcaseBusiness, ShieldCheck, Shield, UserRound } from "lucide-react";
import Link from "next/link";
import PublicShell from "@/components/platform/PublicShell";
import { APP_HREF, CORPUS_FACTS as facts, REQUIREMENTS as needs, SITE_ROUTES } from "@/lib/site";

export const metadata: Metadata = {
  title: "Indian law, answered from the source",
  description:
    "Corpusil answers questions about Indian law from official documents, shows the passage behind each statement, and says so when it cannot answer. It runs on your own machine.",
};

const BNSS = "The Bharatiya Nagarik Suraksha Sanhita, 2023";

/** Panels below reuse the app's own answer styles, so they are the real thing at rest. */
function SectionHead({ eyebrow, title, lede }: { eyebrow: string; title: string; lede?: string }) {
  return <header className="land-head"><p>{eyebrow}</p><h2>{title}</h2>{lede && <span>{lede}</span>}</header>;
}

export default function WelcomePage() {
  const central = (facts.central / facts.documents) * 100;
  const andhra = (facts.andhraPradesh / facts.documents) * 100;
  const telangana = (facts.telangana / facts.documents) * 100;

  return (
    <PublicShell tone="cover">
      <section className="cover">
        <div className="cover-inner">
          <div className="cover-text">
            <p className="cover-kicker">Legal research for India. Runs on your own machine.</p>
            <h1>Indian law, answered from the source. <em>Or not answered.</em></h1>
            <p className="cover-lede">
              Corpusil reads a governed collection of official Indian legal documents and answers your question with
              the passages it relied on. When those passages cannot support an answer, it says so, and points you to a
              person who can help.
            </p>
            <div className="cover-actions">
              <Link href={APP_HREF} className="cover-primary">Open the app<ArrowRight size={16} aria-hidden="true" /></Link>
              <Link href={SITE_ROUTES.install} className="cover-secondary">Install Corpusil</Link>
            </div>
            <p className="cover-note">Legal information, not advice.</p>
          </div>

          <figure className="specimen" aria-label="A specimen answer">
            <p className="user-message specimen-question">Can I report an offence by message, and will I get a copy?</p>
            <div className="answer-verdict specimen-verdict">
              <ShieldCheck size={18} aria-hidden="true" />
              <div><strong>Verified against sources</strong><span>Each statement was checked against the passage it cites.</span></div>
              <span className="specimen-grade">High confidence</span>
            </div>
            <div className="specimen-answer">
              <p>
                Information about a cognizable offence may be given to an officer in charge of a police station orally
                or by electronic communication, wherever the offence was committed
                <a href="#specimen-source" className="source-chip inline-source" aria-label="Source 1">1</a>. If you send it
                electronically, it is taken on record once you sign it within three days
                <a href="#specimen-source" className="source-chip inline-source" aria-label="Source 1">1</a>. A copy of what was
                recorded must be given to you at once, free of cost
                <a href="#specimen-source" className="source-chip inline-source" aria-label="Source 1">1</a>.
              </p>
            </div>
            <div className="fast-card specimen-source" id="specimen-source">
              <div className="fast-card-head">
                <span className="fast-card-number" aria-hidden="true">1</span>
                <div className="fast-card-title"><span className="source-title-main"><b>Section 173</b> · {BNSS}</span><small className="source-title-detail">Gazette pages 52 and 53</small></div>
                <span className="answer-badge is-ok">In force</span>
              </div>
              <blockquote className="fast-excerpt">
                Every information relating to the commission of a cognizable offence, irrespective of the area where
                the offence is committed, may be given orally or by electronic communication to an officer in charge of
                a police station&hellip;
              </blockquote>
              <p className="specimen-currency">It replaced section 154 of the Code of Criminal Procedure, 1973, on 1 July 2024.</p>
            </div>
            <figcaption>Specimen, set out as the app sets out an answer. Checked by hand against the Gazette copy.</figcaption>
          </figure>
        </div>
      </section>

      <section className="land-section" id="trust" aria-labelledby="trust-title">
        <header className="land-head"><p>Why you can check it</p><h2 id="trust-title">Built to be checked, not believed.</h2></header>
        <div className="pillars">
          <article className="pillar">
            <div className="pillar-panel" aria-hidden="true">
              <div className="mock-line"><span>A copy of what was recorded must be given to you at once, free of cost</span><span className="source-chip inline-source">1</span></div>
              <div className="mock-check is-pass"><ShieldCheck size={14} />Supported by source 1</div>
              <div className="mock-line is-struck"><span>A claim the passage did not support</span></div>
              <div className="mock-check is-drop">Removed before publishing</div>
            </div>
            <h3>Every claim is checked against its source</h3>
            <p>A language model writes only from the passages found. Each claim is then tested against the passage it cites. Anything it could not tie to one is removed, not softened.</p>
          </article>
          <article className="pillar">
            <div className="pillar-panel" aria-hidden="true">
              <p className="pillar-ask">Will I win my case?</p>
              <p className="pillar-refuse">This service will not estimate whether a case is won, lost, or what sentence might follow.</p>
              <p className="pillar-ask">A question the corpus holds no law on</p>
              <p className="pillar-refuse">I could not find enough reliable support in the indexed legal corpus for this answer.</p>
            </div>
            <h3>It refuses when it is unsure</h3>
            <p>Both lines above are the system&rsquo;s own wording. When the corpus cannot support an answer it abstains rather than guessing, and gives the legal aid helpline and how to reach an advocate.</p>
          </article>
          <article className="pillar">
            <div className="pillar-panel" aria-hidden="true">
              <div className="mock-source">
                <span className="source-title-main"><b>Section 154</b> · Code of Criminal Procedure, 1973</span>
                <span className="answer-badge is-bad">No longer in force</span>
              </div>
              <div className="mock-arrow"><ArrowRight size={14} />Replaced on 1 July 2024 by</div>
              <div className="mock-source">
                <span className="source-title-main"><b>Section 173</b> · Bharatiya Nagarik Suraksha Sanhita, 2023</span>
                <span className="answer-badge is-ok">In force</span>
              </div>
            </div>
            <h3>It tells you when the law has changed</h3>
            <p>Repealed, superseded and uncommenced law is labelled wherever it appears, and the replacement is named, because the 2023 Sanhitas renumbered the provisions most people still cite from memory.</p>
          </article>
        </div>
        <p className="land-caution">
          <strong>A model is checking a model.</strong> This catches a great deal, and it can still misread a passage.
          The grade describes how well the sources support an answer, not whether the answer is right. The source is on
          the page so that you can check.
        </p>
      </section>

      <section className="land-section is-tinted" id="who" aria-labelledby="who-title">
        <header className="land-head"><p>Who it is for</p><h2 id="who-title">One corpus, three ways in.</h2></header>
        <div className="people">
          <article className="person">
            <div className="person-head"><UserRound size={18} strokeWidth={1.7} aria-hidden="true" /><h3>A citizen</h3></div>
            <p>Ask in plain words or by voice, in a screen that also reads Hindi and Telugu. Attach a notice or an agreement and ask about it. Read the passage behind each statement in the answer.</p>
            <div className="person-panel" aria-hidden="true">
              <div className="mock-composer">Describe your legal question in your own words&hellip;</div>
              <div className="mock-tags"><span>Know your rights</span><span>Explain a notice</span><span>Free legal aid</span></div>
            </div>
          </article>
          <article className="person">
            <div className="person-head"><Shield size={18} strokeWidth={1.7} aria-hidden="true" /><h3>A police officer</h3></div>
            <p>A case register with evidence held apart per case. FIR facts and drafting. Nine statutory investigation deadlines under the BNSS, and a compliance record that separates &ldquo;not done&rdquo; from &ldquo;not recorded&rdquo;.</p>
            <div className="person-panel" aria-hidden="true">
              <div className="mock-row"><span>Production before the Magistrate</span><span className="answer-badge is-bad">Overdue</span></div>
              <div className="mock-row"><span>Final report</span><span className="answer-badge is-warn">Due soon</span></div>
              <div className="mock-row"><span>Case diary</span><span className="answer-badge is-plain">Not recorded</span></div>
            </div>
          </article>
          <article className="person">
            <div className="person-head"><BriefcaseBusiness size={18} strokeWidth={1.7} aria-hidden="true" /><h3>An advocate</h3></div>
            <p>A private corpus per matter. Defence analysis that includes the arguments against you. A citation check that flags repealed provisions and what replaced them.</p>
            <div className="person-panel" aria-hidden="true">
              <div className="mock-row"><span>Your draft cites CrPC s.154</span><span className="answer-badge is-bad">Repealed</span></div>
              <div className="mock-row"><span>Now BNSS s.173</span><span className="answer-badge is-ok">In force</span></div>
              <div className="mock-row"><span>Arguments against you</span><span className="answer-badge is-plain">Included</span></div>
            </div>
          </article>
        </div>
        <p className="land-footnote">
          An administrator looks after accounts for officers and advocates, one-time password resets, corpus intake with
          validation, and an audit log, with no general search into private case material. One person&rsquo;s case
          material cannot be reached from another person&rsquo;s question: that separation is enforced in the search itself
          and is tested adversarially.
        </p>
      </section>

      <section className="land-section" id="answer" aria-labelledby="answer-title">
        <header className="land-head"><p>How an answer is made</p><h2 id="answer-title">Four steps, and an exit.</h2></header>
        <ol className="flow">
          <li><strong>Find</strong><span>Search the corpus by meaning and by exact wording, and rank what comes back.</span></li>
          <li><strong>Draft</strong><span>A language model writes only from those passages, marking its source for each claim.</span></li>
          <li><strong>Check</strong><span>Each claim is tested against the passage it cites. Claims that fail are dropped.</span></li>
          <li><strong>Publish or decline</strong><span>What survives is published with a grade. If too little survives, it declines.</span></li>
        </ol>
        <p className="land-para">
          That takes time. A quick search returns passages in under a second, labelled as unverified. A full review takes
          a minute or more on the {needs.memoryGb} GB machine it was measured on, and the app shows you the sources it has
          found while you wait.
        </p>
      </section>

      <section className="land-section is-tinted" id="coverage" aria-labelledby="coverage-title">
        <header className="land-head"><p>What it covers, and what it does not</p><h2 id="coverage-title">Counted, not estimated.</h2><span>Counted from the corpus manifest on {facts.countedOn}. An installation shows its own live count.</span></header>
        <div className="coverage">
          <div>
            <dl className="figures">
              <div><dt>Official documents</dt><dd>{facts.documents.toLocaleString("en-IN")}</dd></div>
              <div><dt>Pages, about</dt><dd>{Math.round(facts.pages / 1000)},000</dd></div>
              <div><dt>Acts</dt><dd>{facts.acts}</dd></div>
              <div><dt>Rules</dt><dd>{facts.rules}</dd></div>
            </dl>
            <div className="coverage-bar" role="img" aria-label={`${facts.central} Central, ${facts.andhraPradesh} Andhra Pradesh, ${facts.telangana} Telangana`}>
              <span style={{ width: `${central}%` }} className="is-central" />
              <span style={{ width: `${andhra}%` }} className="is-andhra" />
              <span style={{ width: `${telangana}%` }} className="is-telangana" />
            </div>
            <table className="coverage-table">
              <caption className="sr-only">Documents by jurisdiction</caption>
              <tbody>
                <tr><th scope="row"><i className="is-central" />Central</th><td>{facts.central.toLocaleString("en-IN")}</td></tr>
                <tr><th scope="row"><i className="is-andhra" />Andhra Pradesh</th><td>{facts.andhraPradesh}</td></tr>
                <tr><th scope="row"><i className="is-telangana" />Telangana (some)</th><td>{facts.telangana}</td></tr>
              </tbody>
            </table>
          </div>
          <ul className="limits">
            <li><strong>Other States are not covered.</strong> For State law outside Andhra Pradesh and part of Telangana, it will abstain or answer only from Central law.</li>
            <li><strong>It is not a case-law database.</strong> It holds {facts.judgments} judgments: {facts.supremeCourtJudgments} of the Supreme Court and {facts.andhraHighCourtJudgments} of the Andhra Pradesh High Court. Absence of a judgment here says nothing about the law.</li>
            <li><strong>It answers in English,</strong> and nearly every document is in English.</li>
            <li><strong>It can be out of date.</strong> It knows what its corpus holds. Check the current official text before relying on anything in a live matter.</li>
          </ul>
        </div>
      </section>

      <section className="land-section" id="machine" aria-labelledby="machine-title">
        <div className="land-split">
          <div>
            <header className="land-head"><p>Where it runs</p><h2 id="machine-title">On your hardware.</h2></header>
            <p className="land-para">
              You install it. The language model runs on your machine through Ollama, so your questions and case files are
              not sent to an outside AI service, and there is no account with us to create. That is a serious machine, and
              it is the honest price of not sending legal questions to someone else&rsquo;s server. A small team can run one
              installation and connect to it from their own devices.
            </p>
            <ul className="needs">
              <li><strong>{needs.memoryGb} GB</strong><span>of memory. The model alone holds about {needs.modelResidentGb} GB.</span></li>
              <li><strong>{needs.modelDownloadGb} GB</strong><span>model download, before the corpus.</span></li>
              <li><strong>{needs.corpusAllGb} GB</strong><span>for the full corpus with its indexes. A pack can be smaller.</span></li>
            </ul>
            <p className="land-para"><Link className="land-link" href={SITE_ROUTES.install}>Requirements and install steps</Link></p>
          </div>
          <div id="limits">
            <header className="land-head"><p>What it is not</p><h2>Stated plainly.</h2></header>
            <ul className="limits">
              <li>It is not legal advice, and it does not know your full circumstances.</li>
              <li>It does not predict outcomes or tell anyone they will win.</li>
              <li>It files nothing, and it does not connect to any court system.</li>
              <li>It does not recommend or advertise lawyers.</li>
              <li>It does not replace an advocate. For your own matter, free legal aid may be open to you: call <a href="tel:15100">15100</a> or ask at your district court.</li>
            </ul>
            <p className="land-links">
              <Link className="land-link" href={SITE_ROUTES.privacy}>Privacy notice</Link>
              <Link className="land-link" href={SITE_ROUTES.terms}>Terms of use</Link>
              <Link className="land-link" href={SITE_ROUTES.help}>Help, by role</Link>
            </p>
          </div>
        </div>
      </section>

      <section className="closing">
        <h2>Read one answer. Then check its source.</h2>
        <div className="cover-actions">
          <Link href={APP_HREF} className="cover-primary">Open the app<ArrowRight size={16} aria-hidden="true" /></Link>
          <Link href={SITE_ROUTES.install} className="cover-secondary">Install Corpusil</Link>
        </div>
      </section>
    </PublicShell>
  );
}
