import type { Metadata } from "next";
import Link from "next/link";
import PublicShell, { DocumentPage } from "@/components/platform/PublicShell";
import { APP_HREF, SITE_ROUTES } from "@/lib/site";

export const metadata: Metadata = {
  title: "Help",
  description: "How to use Corpusil, for citizens, police officers, advocates and administrators.",
};

const CONTENTS = [
  ["reading", "Reading an answer"],
  ["citizen", "For citizens"],
  ["police", "For police officers"],
  ["advocate", "For advocates"],
  ["admin", "For administrators"],
  ["history", "Finding past conversations"],
  ["account", "Your account and data"],
  ["accessibility", "Text size and slow connections"],
  ["offline", "Offline use"],
] as const;

export default function HelpPage() {
  return (
    <PublicShell>
      <DocumentPage
        eyebrow="Help"
        title="How to use Corpusil"
        lede="Start with reading an answer, since that applies to everyone. Then go to your role."
      >
        <nav className="doc-contents" aria-label="On this page">
          <ol>{CONTENTS.map(([id, title]) => <li key={id}><a href={`#${id}`}>{title}</a></li>)}</ol>
        </nav>

        <h2 id="reading">Reading an answer</h2>
        <p>Every answer has the same parts. Learn these once.</p>
        <dl className="doc-items">
          <div><dt>Numbered sources</dt><dd>Press a number in the text, or under the answer, to read the passage it relied on, with its document and page. Read it. This is the point of the product.</dd></div>
          <div><dt>The grade</dt><dd><strong>High</strong> or <strong>Moderate confidence</strong> describes how well the retrieved sources support the answer. <strong>Limited evidence</strong> means they did not support much. <strong>Relevance preview</strong> means passages were found and the claims were not verified. None of these is your chance of winning a case.</dd></div>
          <div><dt>&ldquo;Is this still the law?&rdquo;</dt><dd>Says when a source has been repealed or renumbered, and what replaced it. The Bharatiya Nagarik Suraksha Sanhita and the other 2023 Sanhitas replaced provisions many people still cite.</dd></div>
          <div><dt>Limits and uncertainties</dt><dd>What the sources leave open. It applies to your question, so read it before you rely on the rest.</dd></div>
          <div><dt>When it declines</dt><dd>It could not find enough support, so it does not guess. It shows how to reach legal aid or an advocate. Try rewording with the specific Act or section, or take the question to a person.</dd></div>
        </dl>
        <p><strong>Fast or Deep?</strong> Fast returns passages in moments, unverified. Deep drafts and checks an answer, and takes a minute or more. You can see its progress and the sources it has found while you wait, and you can reload the page without losing it. Auto chooses for you.</p>
        <p><strong>Keeping an answer.</strong> Under each answer, the document button prints it or saves it as Markdown or HTML, with its sources attached.</p>

        <h2 id="citizen">For citizens</h2>
        <ul>
          <li>Ask in your own words: what happened, where you are in the process, and what you need to decide. You can also speak your question, then check the words before sending.</li>
          <li>Leave out what you do not need: names, phone numbers, account numbers.</li>
          <li>To understand a notice or an agreement, attach it with the paperclip and ask about one thing at a time. The text is used for that question and is not stored as a file.</li>
          <li>It will not tell you whether you will win, or what to decide. It will explain the law and procedure, so you can take that to a lawyer.</li>
          <li>If you are in danger, call <a href="tel:112">112</a>. For free legal help, call the National Legal Services Authority on <a href="tel:15100">15100</a>.</li>
        </ul>

        <h2 id="police">For police officers</h2>
        <p>Your account is created by your administrator, who gives you a temporary password. You will be asked to change it. Turn on two-step sign-in straight away.</p>
        <ul>
          <li><strong>Investigations.</strong> Each case holds its own evidence, and only you can reach it. Upload documents, and they are indexed for that case alone.</li>
          <li><strong>Asking within a case.</strong> Pick the case beside the question box. The answer then reads the law and that case&rsquo;s files. Start a new chat to change case, since a chat keeps the scope it began with.</li>
          <li><strong>FIR drafting.</strong> Enter or extract the facts and generate a draft to check. You sign it, not the system.</li>
          <li><strong>Deadlines.</strong> Record the dates you have. It works out the BNSS periods from them and says &ldquo;cannot be determined&rdquo; where a date is missing. That is not a pass.</li>
          <li><strong>Compliance.</strong> Each duty is done, not done, or not recorded, and these are different things.</li>
        </ul>

        <h2 id="advocate">For advocates</h2>
        <p>Your account is created by an administrator. Turn on two-step sign-in straight away: this holds client material.</p>
        <ul>
          <li><strong>Your cases.</strong> Each matter has its own private files. Searching a matter reads its files and the law, and nothing from another matter unless you ask across your own matters.</li>
          <li><strong>Defence analysis.</strong> It sets out points on both sides, including those against you. Check each against its authority before you use it.</li>
          <li><strong>Citation check.</strong> Paste a draft to flag repealed provisions and what replaced them.</li>
          <li><strong>Judgments.</strong> The corpus holds few, so an empty result says little about the law. Use a reporter for precedent research. This is a limit, not a hidden feature.</li>
        </ul>

        <h2 id="admin">For administrators</h2>
        <ul>
          <li><strong>The first administrator</strong> is created on the server with <code>scripts/create_admin_account.py</code>.</li>
          <li><strong>Accounts.</strong> Create police and advocate accounts in Administration. They must change the password you set the first time they sign in.</li>
          <li><strong>Password resets.</strong> In Settings, under Account and privacy, then Administration: enter the address and issue a one-time code. It is shown once, and it expires. Hand it over in person or on a channel you trust. If someone has also lost their authenticator and recovery codes, tick the option to clear it. You never see the new password.</li>
          <li><strong>Erasure requests.</strong> For someone who cannot sign in, erase from the same screen. It removes their data without showing you any of it.</li>
          <li><strong>Retention.</strong> Set <code>CHAT_RETENTION_DAYS</code> and run the pass from that screen, or daily with <code>scripts/apply_retention.py</code>. It has no effect until something runs it.</li>
          <li><strong>Corpus.</strong> Stage, validate, then publish a source. You cannot search private case material from Administration, by design.</li>
          <li><strong>Grievance contact.</strong> Set it in the environment. See <Link href={SITE_ROUTES.install}>Install</Link>.</li>
        </ul>

        <h2 id="history">Finding past conversations</h2>
        <ul>
          <li>Press <strong>Search chats</strong> in the sidebar to search titles and message text. Your search is not stored.</li>
          <li><strong>Pin</strong> up to five conversations. Pins follow you to your other devices.</li>
          <li>Give conversations a <strong>matter</strong> name to group them, then filter by it. Case chats are also grouped under their case.</li>
          <li>Rename or delete from the three-dot menu. Deleting removes the conversation and the records it left behind, for good.</li>
        </ul>

        <h2 id="account">Your account and data</h2>
        <p>All of this is in <strong>Settings, then Account and privacy</strong>.</p>
        <ul>
          <li><strong>Forgotten password.</strong> On the sign-in screen choose &ldquo;Forgot your password?&rdquo;. Ask your administrator for a one-time code, and enter it there with a new password. If you run this installation yourself, create a second administrator on the server and use that account.</li>
          <li><strong>Two-step sign-in.</strong> Add the key to an authenticator app, confirm a code, and save your recovery codes somewhere safe. Each one works once. If you lose both, an administrator can clear it.</li>
          <li><strong>Devices.</strong> See where you are signed in and sign any of them out. It takes effect immediately.</li>
          <li><strong>Your data.</strong> Download everything, correct your details, withdraw consent, or erase your account. See the <Link href={SITE_ROUTES.privacy}>privacy notice</Link>.</li>
        </ul>

        <h2 id="accessibility">Text size and slow connections</h2>
        <ul>
          <li><strong>Text size.</strong> Settings, then Account and privacy, then Reading. Standard, Large or Larger, on this device.</li>
          <li><strong>Low-bandwidth mode.</strong> The same screen. It drops decoration and background checks, and loads fewer conversations at a time. It starts on if your browser asks to save data.</li>
          <li><strong>Keyboard.</strong> Everything can be reached with Tab. Escape closes dialogs and menus.</li>
          <li><strong>Motion.</strong> Animation stops if your system asks for reduced motion. There is also a setting for it in Settings.</li>
        </ul>

        <h2 id="offline">Offline use</h2>
        <p>
          Corpusil answers without a network once the server, the model and a corpus are on your machine. The usual way to
          get a corpus onto a machine with no connection is an <Link href={`${SITE_ROUTES.install}#corpus`}>offline corpus pack</Link>:
          built on a connected machine, carried across, verified against its checksums, and restored. The desktop app can
          point at that server on the same machine.
        </p>
        <p>
          A pack is one snapshot. It does not update itself, and nothing tells you when the law moves on, so keep its date in
          mind. Citation links to official sources and browser voice input need a connection.
        </p>
        <p className="doc-links"><Link href={APP_HREF}>Open the app</Link></p>
      </DocumentPage>
    </PublicShell>
  );
}
