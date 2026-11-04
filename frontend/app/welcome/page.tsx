import type { Metadata } from "next";
import Link from "next/link";
import PublicShell from "@/components/platform/PublicShell";
import { APP_HREF, CORPUS_FACTS as facts, REQUIREMENTS as needs, SITE_ROUTES } from "@/lib/site";

export const metadata: Metadata = {
  title: "Indian law, answered from the source",
  description:
    "Corpusil answers questions about Indian law from official documents, shows the passage behind each statement, and says so when it cannot answer. It runs on your own machine.",
};

const SECTIONS = [
  ["what", "What it does"],
  ["refusal", "What it does when it cannot answer"],
  ["who", "Who it is for"],
  ["answer", "How an answer is made"],
  ["coverage", "What it covers, and what it does not"],
  ["machine", "Where it runs"],
  ["limits", "What it is not"],
] as const;

function Clause({ note, id, number, title, children }: { note: string; id: string; number: number; title: string; children: React.ReactNode }) {
  return (
    <section className="act-section" id={id} aria-labelledby={`${id}-title`}>
      <p className="act-note">{note}</p>
      <div className="act-body">
        <h2 id={`${id}-title`}><span className="act-number">{number}.</span> {title}</h2>
        {children}
      </div>
    </section>
  );
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
              <Link href={SITE_ROUTES.install} className="cover-primary">Install Corpusil</Link>
              <Link href={APP_HREF} className="cover-secondary">Open the app</Link>
            </div>
          </div>

          <figure className="specimen" aria-label="A specimen answer">
            <figcaption>Specimen, set out as the app sets out an answer. Checked by hand against the Gazette copy.</figcaption>
            <p className="specimen-question">Can I report an offence by message, and will I get a copy?</p>
            <div className="specimen-answer">
              <p>
                Information about a cognizable offence may be given to an officer in charge of a police station orally
                or by electronic communication, wherever the offence was committed
                <a href="#specimen-source" className="specimen-mark" aria-label="Source 1">1</a>. If you send it
                electronically, it is taken on record once you sign it within three days
                <a href="#specimen-source" className="specimen-mark" aria-label="Source 1">1</a>. A copy of what was
                recorded must be given to you at once, free of cost
                <a href="#specimen-source" className="specimen-mark" aria-label="Source 1">1</a>.
              </p>
            </div>
            <details className="specimen-source" id="specimen-source" open>
              <summary>
                <span className="specimen-mark" aria-hidden="true">1</span>
                The Bharatiya Nagarik Suraksha Sanhita, 2023, s.173. Gazette pages 52 and 53.
              </summary>
              <blockquote>
                Every information relating to the commission of a cognizable offence, irrespective of the area where
                the offence is committed, may be given orally or by electronic communication to an officer in charge of
                a police station&hellip;
              </blockquote>
            </details>
            <p className="specimen-currency">
              <strong>Is this still the law?</strong> In force. It replaced section 154 of the Code of Criminal
              Procedure, 1973, on 1 July 2024.
            </p>
          </figure>
        </div>
      </section>

      <nav className="arrangement" aria-labelledby="arrangement-title">
        <h2 id="arrangement-title">Arrangement of sections</h2>
        <ol>
          {SECTIONS.map(([id, title]) => <li key={id}><a href={`#${id}`}>{title}</a></li>)}
        </ol>
      </nav>

      <div className="act">
        <Clause id="what" number={1} title="What it does" note="Answers, with their sources.">
          <p className="act-lead">
            You ask a question about Indian law in your own words. Corpusil finds the relevant passages in{" "}
            {facts.documents.toLocaleString("en-IN")} official documents, drafts an answer from those passages, checks
            each claim against them, and shows you the text it relied on.
          </p>
          <p>
            The law you read is held beside what it replaced. If a source has been repealed or superseded, the answer
            labels it and names the replacement, because the 2023 Sanhitas renumbered the provisions most people still
            cite from memory.
          </p>
        </Clause>

        <Clause id="refusal" number={2} title="What it does when it cannot answer" note="Declining is the product.">
          <p className="act-lead">
            Most tools are judged on the answer. This one is built around what happens when there is no good answer to
            give.
          </p>
          <figure className="refusal">
            <p className="refusal-question">Will I win my case?</p>
            <p className="refusal-answer">This service will not estimate whether a case is won, lost, or what sentence might follow.</p>
            <p className="refusal-question">A question the corpus holds no law on</p>
            <p className="refusal-answer">I could not find enough reliable support in the indexed legal corpus for this answer.</p>
            <figcaption>Both lines are the system&rsquo;s own wording. Below them, the app gives the legal aid helpline and how to reach an advocate.</figcaption>
          </figure>
          <ol className="clauses">
            <li>Every published statement cites a passage the system actually retrieved. Anything it could not tie to one is removed, not softened.</li>
            <li>Repealed, superseded and uncommenced law is labelled as such, wherever it appears.</li>
            <li>When the corpus cannot support an answer, it abstains rather than guessing.</li>
            <li>One person&rsquo;s case material cannot be reached from another person&rsquo;s question. That separation is enforced in the search itself and is tested adversarially.</li>
          </ol>
        </Clause>

        <Clause id="who" number={3} title="Who it is for" note="Four people, four jobs.">
          <dl className="roles">
            <div>
              <dt>A citizen</dt>
              <dd>Ask in plain words or by voice. Attach a notice or an agreement and ask about it. Read the passage behind each statement in the answer.</dd>
            </div>
            <div>
              <dt>A police officer</dt>
              <dd>A case register with evidence held apart per case. FIR facts and drafting. Nine statutory investigation deadlines under the BNSS, and a compliance record that separates &ldquo;not done&rdquo; from &ldquo;not recorded&rdquo;.</dd>
            </div>
            <div>
              <dt>An advocate</dt>
              <dd>A private corpus per matter. Defence analysis that includes the arguments against you. A citation check that flags repealed provisions and what replaced them.</dd>
            </div>
            <div>
              <dt>An administrator</dt>
              <dd>Accounts for officers and advocates, one-time password resets, corpus intake with validation, and an audit log. No general search into private case material.</dd>
            </div>
          </dl>
        </Clause>

        <Clause id="answer" number={4} title="How an answer is made" note="Four steps, and an exit.">
          <ol className="steps">
            <li><strong>Find.</strong> Search the corpus by meaning and by exact wording, and rank what comes back.</li>
            <li><strong>Draft.</strong> A language model writes only from those passages, marking its source for each claim.</li>
            <li><strong>Check.</strong> Each claim is tested against the passage it cites. Claims that fail are dropped.</li>
            <li><strong>Publish or decline.</strong> What survives is published with a grade. If too little survives, it declines.</li>
          </ol>
          <p>
            That takes time. A quick search returns passages in under a second, labelled as unverified. A full review
            takes a minute or more on the {needs.memoryGb} GB machine it was measured on, and the app shows you the sources
            it has found while you wait.
          </p>
          <p className="act-caution">
            <strong>A model is checking a model.</strong> This catches a great deal, and it can still misread a passage.
            The grade describes how well the sources support an answer, not whether the answer is right. The source is
            on the page so that you can check.
          </p>
        </Clause>

        <Clause id="coverage" number={5} title="What it covers, and what it does not" note="Counted, not estimated.">
          <p className="act-lead">
            {facts.documents.toLocaleString("en-IN")} official documents and about {Math.round(facts.pages / 1000)},000
            pages, counted from the corpus manifest on {facts.countedOn}. An installation shows its own live count.
          </p>
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
          <ol className="clauses">
            <li><strong>Other States are not covered.</strong> For State law outside Andhra Pradesh and part of Telangana, it will abstain or answer only from Central law.</li>
            <li><strong>It is not a case-law database.</strong> It holds {facts.judgments} judgments: {facts.supremeCourtJudgments} of the Supreme Court and {facts.andhraHighCourtJudgments} of the Andhra Pradesh High Court. Absence of a judgment here says nothing about the law.</li>
            <li><strong>It answers in English,</strong> and nearly every document is in English.</li>
            <li><strong>It can be out of date.</strong> It knows what its corpus holds. Check the current official text before relying on anything in a live matter.</li>
          </ol>
        </Clause>

        <Clause id="machine" number={6} title="Where it runs" note="On your hardware.">
          <p className="act-lead">
            You install it. The language model runs on your machine through Ollama, so your questions and case files are
            not sent to an outside AI service, and there is no account with us to create.
          </p>
          <ul className="needs">
            <li><strong>{needs.memoryGb} GB</strong><span>of memory. The model alone holds about {needs.modelResidentGb} GB.</span></li>
            <li><strong>{needs.modelDownloadGb} GB</strong><span>model download, before the corpus.</span></li>
            <li><strong>{needs.corpusAllGb} GB</strong><span>for the full corpus with its indexes. A pack can be smaller.</span></li>
          </ul>
          <p>
            That is a serious machine, and it is the honest price of not sending legal questions to someone else&rsquo;s
            server. A small team can run one installation and connect to it from their own devices.
          </p>
          <p><Link className="act-link" href={SITE_ROUTES.install}>Requirements and install steps</Link></p>
        </Clause>

        <Clause id="limits" number={7} title="What it is not" note="Stated plainly.">
          <ol className="clauses">
            <li>It is not legal advice, and it does not know your full circumstances.</li>
            <li>It does not predict outcomes or tell anyone they will win.</li>
            <li>It files nothing, and it does not connect to any court system.</li>
            <li>It does not recommend or advertise lawyers.</li>
            <li>It does not replace an advocate. For your own matter, free legal aid may be open to you: call <a href="tel:15100">15100</a> or ask at your district court.</li>
          </ol>
          <p className="act-links">
            <Link className="act-link" href={SITE_ROUTES.privacy}>Privacy notice</Link>
            <Link className="act-link" href={SITE_ROUTES.terms}>Terms of use</Link>
            <Link className="act-link" href={SITE_ROUTES.help}>Help, by role</Link>
          </p>
        </Clause>
      </div>

      <section className="closing">
        <h2>Read one answer. Then check its source.</h2>
        <div className="cover-actions">
          <Link href={SITE_ROUTES.install} className="cover-primary">Install Corpusil</Link>
          <Link href={APP_HREF} className="cover-secondary">Open the app</Link>
        </div>
      </section>
    </PublicShell>
  );
}
