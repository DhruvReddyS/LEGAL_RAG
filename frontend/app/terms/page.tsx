import type { Metadata } from "next";
import Link from "next/link";
import PublicShell, { DocumentPage } from "@/components/platform/PublicShell";
import { CORPUS_FACTS as facts, SITE_ROUTES } from "@/lib/site";

export const metadata: Metadata = {
  title: "Terms of use",
  description: "What Corpusil is, what it is not, and what you take on by using it.",
};

export default function TermsPage() {
  return (
    <PublicShell>
      <DocumentPage
        eyebrow="Terms of use"
        title="Terms of use"
        lede="By using Corpusil you accept these terms. The first section matters most."
      >
        <h2>1. This is legal information, not legal advice</h2>
        <p>
          Corpusil finds passages of law and explains them. It does not know your full circumstances and has not read
          your file. Nothing it produces is legal advice, and using it does not create a lawyer and client relationship
          with anyone.
        </p>
        <p>
          Do not make a decision in a live matter on the strength of an answer alone. Read the source, check the current
          official text, and speak to an advocate or a legal services authority. Free legal aid may be open to you: call
          the National Legal Services Authority on <a href="tel:15100">15100</a>.
        </p>

        <h2>2. What it can get wrong</h2>
        <ul>
          <li>A language model drafts the answers and checks them against the sources. It can misread a passage even when the passage is correct.</li>
          <li>The corpus is limited. It holds Central law, Andhra Pradesh law and some Telangana law, and {facts.judgments} judgments. It does not hold every statute, amendment or decision.</li>
          <li>The corpus can be out of date. A label saying a source is current means the corpus records it as current, not that nothing has changed since.</li>
          <li>The grade on an answer describes how well the retrieved sources support it. It is not a measure of whether the answer is right, or of your chances in a case.</li>
        </ul>

        <h2>3. What it does not do</h2>
        <p>
          It does not predict outcomes, represent anyone, file anything, or contact any court, police station or authority.
          It does not recommend or advertise any lawyer: where it points you to help, it points to institutions.
        </p>

        <h2>4. Professional users</h2>
        <p>
          If you are a police officer or an advocate, you remain responsible for your own work. A draft or an analysis
          from Corpusil is a starting point that you must check against the law and your facts before you use it. It does
          not replace your duties under the law or your professional rules. Deadlines it calculates depend on the dates
          you record, and it says so where a date is missing.
        </p>

        <h2>5. Your use</h2>
        <ul>
          <li>Use it lawfully. Do not use it to interfere with evidence, to evade lawful process, or to locate a private person. It declines such requests.</li>
          <li>Keep your sign-in details to yourself. You answer for what is done with your account.</li>
          <li>Upload only material you have the right to use. Professional accounts should follow the rules that apply to case material held outside official systems.</li>
          <li>If you run an installation, you are responsible for it: its security, its backups, naming a grievance officer, and answering requests from the people who use it.</li>
        </ul>

        <h2>6. The software</h2>
        <p>
          Corpusil is provided as it is, without any promise that it is free of errors or fit for a particular purpose, to
          the extent the law allows. Desktop builds are not yet notarised or code-signed by an operating system vendor, and
          the install page says what that means for you.
        </p>

        <h2>7. Changes</h2>
        <p>These terms may change. Using the product after a change means you accept the new terms.</p>

        <p className="doc-links">
          <Link href={SITE_ROUTES.privacy}>Privacy notice</Link>
          <Link href={SITE_ROUTES.help}>Help</Link>
        </p>
      </DocumentPage>
    </PublicShell>
  );
}
