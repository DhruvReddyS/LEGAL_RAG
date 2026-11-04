import type { Metadata } from "next";
import Link from "next/link";
import PublicShell, { DocumentPage } from "@/components/platform/PublicShell";
import { GrievanceOfficer, RetentionStatement } from "@/components/platform/PrivacyLive";
import {
  KNOWN_EXCEPTIONS,
  PERSONAL_DATA_ITEMS,
  PRIVACY_NOTICE_VERSION,
  PURPOSES,
  WHAT_DOES_NOT_HAPPEN,
} from "@/lib/privacy-text";
import { APP_HREF, SITE_ROUTES } from "@/lib/site";

export const metadata: Metadata = {
  title: "Privacy notice",
  description: "What personal data Corpusil holds, why, how long, and how to export it, correct it, erase it or complain.",
};

export default function PrivacyPage() {
  return (
    <PublicShell>
      <DocumentPage
        eyebrow={`Notice version ${PRIVACY_NOTICE_VERSION}`}
        title="Privacy notice"
        lede="Corpusil is installed and run by whoever operates your installation. It keeps your data on that machine, and that operator is the one answerable for it. This notice says what is held, why, and what you can do about it."
      >
        <h2>Who is responsible</h2>
        <GrievanceOfficer />

        <h2>The personal data held</h2>
        <dl className="doc-items">
          {PERSONAL_DATA_ITEMS.map(([item, detail]) => (
            <div key={item}><dt>{item}</dt><dd>{detail}</dd></div>
          ))}
        </dl>

        <h2>What it is used for</h2>
        <ul>{PURPOSES.map(line => <li key={line}>{line}</li>)}</ul>

        <h2>What does not happen</h2>
        <ul>{WHAT_DOES_NOT_HAPPEN.map(line => <li key={line}>{line}</li>)}</ul>

        <h2>Two exceptions to know about</h2>
        <ul>{KNOWN_EXCEPTIONS.map(line => <li key={line}>{line}</li>)}</ul>

        <h2>How long it is kept</h2>
        <RetentionStatement />
        <p>
          Case records stay until you or an administrator erase the account. A record of security events is kept after
          erasure with the name, address and any question text removed: what happened and when, not who.
        </p>
        <p>
          Backups are the operator&rsquo;s responsibility. If your installation is backed up, erased data leaves those
          backups only as they age out. Ask the operator how long that takes.
        </p>

        <h2>What you can do, and how</h2>
        <p>Each of these is in the app under <strong>Settings, then Account and privacy</strong>. None of them needs anyone&rsquo;s permission.</p>
        <dl className="doc-items">
          <div><dt>See your data</dt><dd>Download everything held about you as one file. Your password hash and authenticator secret are left out, since they exist only to verify you.</dd></div>
          <div><dt>Correct it</dt><dd>Change your name and email address.</dd></div>
          <div><dt>Withdraw consent</dt><dd>One action, on the same screen. The app then stops working for your account until you accept again or erase it.</dd></div>
          <div><dt>Erase it</dt><dd>Your account, conversations, case records and uploaded files are removed from the database, the search index and file storage, including earlier versions of files. You get a receipt number that names nobody. Police and advocate accounts should read the warning shown there first, since it also removes case records.</dd></div>
          <div><dt>If you cannot sign in</dt><dd>Ask an administrator of your installation, or the grievance officer above. They can reset your password or erase your account without being able to read it.</dd></div>
          <div><dt>Nominate someone</dt><dd>The app has no screen for this yet. Write to the grievance officer above.</dd></div>
        </dl>

        <h2>Complaints</h2>
        <p>
          Raise it first with the grievance officer named above. The Rules require a grievance system to answer within a
          period the fiduciary publishes, of not more than ninety days. If you are not satisfied, you may complain to the
          Data Protection Board of India.
        </p>

        <h2>The law this is written against</h2>
        <p>
          This notice follows rule 3 of the Digital Personal Data Protection Rules, 2025 (G.S.R. 846(E), 13 November
          2025): it stands on its own, itemises the data and the purposes, and says how to withdraw consent, exercise
          rights and complain to the Board. Under G.S.R. 843(E) of the same date, most of the duties in the Digital
          Personal Data Protection Act, 2023, and rules 3 and 5 to 16, commence eighteen months after publication. This
          product is built to that standard already. It is not a statement that any given installation complies with
          the law: that depends on how its operator runs it.
        </p>
        <p className="doc-muted">
          Accounts here are for adults. Corpusil does not check age and does not obtain a parent&rsquo;s consent, so a child
          should not register without an adult. If the notice changes in substance, everyone is asked to accept the new
          version the next time they open the app.
        </p>
        <p className="doc-links">
          <Link href={SITE_ROUTES.terms}>Terms of use</Link>
          <Link href={APP_HREF}>Open the app</Link>
        </p>
      </DocumentPage>
    </PublicShell>
  );
}
