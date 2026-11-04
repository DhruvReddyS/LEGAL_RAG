import type { Metadata } from "next";
import Link from "next/link";
import PublicShell, { DocumentPage } from "@/components/platform/PublicShell";
import ReleaseChecksums from "@/components/platform/ReleaseChecksums";
import { CORPUS_FACTS as facts, REQUIREMENTS as needs, SITE_ROUTES, SOURCE_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Install",
  description: "What Corpusil needs and how to install it on macOS, Windows and Linux, stated honestly.",
};

function Commands({ children }: { children: string }) {
  return <pre className="doc-commands" tabIndex={0}><code>{children}</code></pre>;
}

export default function InstallPage() {
  return (
    <PublicShell>
      <DocumentPage
        eyebrow="Install"
        title="Install Corpusil on your own machine"
        lede="There are two parts: a server that holds the corpus and runs the model, and an app that talks to it. This is a technical install today, and the page says where it is rough."
      >
        <h2>What you need</h2>
        <table className="doc-table">
          <caption className="sr-only">Requirements</caption>
          <tbody>
            <tr><th scope="row">Memory</th><td><strong>{needs.memoryGb} GB</strong> minimum. It was measured on an Apple M5 Pro with 24 GB: serving fits at about 20 to 21 GB, of which the model holds about {needs.modelResidentGb} GB. Less than this will swap badly, or not start the model at all.</td></tr>
            <tr><th scope="row">Model</th><td><code>{needs.modelTag}</code>, about {needs.modelDownloadGb} GB to download, through Ollama.</td></tr>
            <tr><th scope="row">Corpus</th><td>About {needs.corpusAllGb} GB on disk for the full corpus with processed text and indexes, of which {needs.corpusPdfGb} GB is the source PDFs. {facts.documents.toLocaleString("en-IN")} documents as counted on {facts.countedOn}. A clean checkout contains <strong>no corpus</strong>: without one, every question abstains. See <a href="#corpus">Getting a corpus</a>.</td></tr>
            <tr><th scope="row">Software</th><td>Docker (Docker Desktop on macOS), Ollama, Node.js for the web interface, and Python for the administrator setup.</td></tr>
            <tr><th scope="row">Speed</th><td>A full review takes a minute or more on the machine above. Inside Docker, retrieval runs on the CPU and is slower. Serving and building a corpus at the same time does not fit in 24 GB.</td></tr>
            <tr><th scope="row">Network</th><td>Needed to install and to download the model. Not needed to answer questions once everything is in place.</td></tr>
          </tbody>
        </table>

        <h2>The server</h2>
        <p>Run this on the machine with the memory. Everything binds to this machine only, unless you choose otherwise.</p>
        <Commands>{`git clone ${SOURCE_URL}.git
cd LEGAL_RAG
./scripts/init_local_env.sh        # creates .env with generated secrets
ollama serve &
ollama pull ${needs.modelTag}
./scripts/start_local.sh 3000      # the first run builds images and downloads the embedding model`}</Commands>
        <p>
          The first start can pass its time limit while the embedding model downloads. If it does, run the same command
          again. Then create your administrator, who can issue accounts and password resets:
        </p>
        <Commands>{`PYTHONPATH=backend python scripts/create_admin_account.py --name "Your Name" --email you@example.com`}</Commands>
        <p>Open <code>http://localhost:3000</code>. Citizens can register there. Police and advocate accounts are created by the administrator.</p>
        <p>
          Before anyone else uses it, set who answers for the installation in <code>.env</code>:{" "}
          <code>DATA_FIDUCIARY_NAME</code>, <code>GRIEVANCE_OFFICER_NAME</code> and <code>GRIEVANCE_OFFICER_EMAIL</code>.
          The <Link href={SITE_ROUTES.privacy}>privacy notice</Link> shows these, and says plainly when they are not set.
        </p>

        <h2 id="corpus">Getting a corpus</h2>
        <p>Either build one, which takes hours and all the machine&rsquo;s memory, or restore a pack someone built for you.</p>
        <h3>Using an offline pack</h3>
        <p>
          A pack holds the public corpus only: the search index, the metadata and, unless it was built without them, the
          source PDFs. It holds no accounts, conversations, case files or secrets, and it does not include the language
          model, which you pull with Ollama. Check it, then restore it:
        </p>
        <Commands>{`python scripts/build_offline_corpus_pack.py verify corpusil-global-corpus-….tar
python scripts/build_offline_corpus_pack.py restore corpusil-global-corpus-….tar \\
  --qdrant-url http://127.0.0.1:6333 --legal-kb-root data/legal_kb`}</Commands>
        <p>
          Restore refuses to overwrite an existing collection, and refuses a pack whose checksums do not match. Set{" "}
          <code>QDRANT_GLOBAL_COLLECTION</code> in <code>.env</code> to the name it prints, and restart. To make a pack from a
          working installation:
        </p>
        <Commands>{`python scripts/build_offline_corpus_pack.py build --collection <collection> --output-dir dist/offline`}</Commands>
        <p className="doc-muted">Once restored, questions are answered without any network. What still needs one: opening a citation&rsquo;s official source link, and browser voice input.</p>

        <h2>The desktop app</h2>
        <p>
          The desktop app is a window onto a server. It does not contain the server, the corpus or the model. On first
          launch it opens a setup screen where you enter the server&rsquo;s address, which can be this machine or a private
          host. Local addresses may use <code>http</code>; a remote one must use <code>https</code>.
        </p>
        <ReleaseChecksums />

        <h3>macOS</h3>
        <p>
          Builds are not notarised by Apple, so macOS will warn you. Verify the checksum, then use{" "}
          <strong>System Settings, Privacy &amp; Security, Open Anyway</strong>. Hosting the server is the best-tested path here:
          the measurements on this page come from Apple Silicon.
        </p>
        <h3>Windows</h3>
        <p>
          Builds are not Authenticode-signed, so SmartScreen will warn you. Verify the checksum, then choose{" "}
          <strong>More info, Run anyway</strong>. The app works against a server elsewhere. <strong>The server start scripts
          are Bash and are not supported on Windows.</strong> Use a separate Mac or Linux host. Running them under WSL2 has not
          been tested.
        </p>
        <h3>Linux</h3>
        <p>
          AppImage and deb builds are produced by the release pipeline. The server runs on Docker Engine, where the backend
          container needs a route to Ollama on the host: if <code>/health/ready</code> stays unavailable, add{" "}
          <code>extra_hosts: [&quot;host.docker.internal:host-gateway&quot;]</code> to the backend service. A GPU helps; on CPU alone a
          full review will take considerably longer than the figures above.
        </p>

        <h2>Sharing one server</h2>
        <p>
          A small team can run one server and connect from their own devices over a private network such as Tailscale, using{" "}
          <code>scripts/start_private_demo_host.sh</code>. It refuses to start with placeholder secrets. It is not hardened for
          the open internet, and should not be exposed there.
        </p>

        <h2>If something goes wrong</h2>
        <ul>
          <li><strong>Every question abstains.</strong> There is no corpus yet, or <code>QDRANT_GLOBAL_COLLECTION</code> names the wrong one.</li>
          <li><strong>&ldquo;Refusing to start&rdquo;.</strong> A secret in <code>.env</code> is still a placeholder. Run <code>./scripts/init_local_env.sh</code> on a fresh checkout.</li>
          <li><strong>Forgotten password.</strong> An administrator issues a one-time code. See <Link href={`${SITE_ROUTES.help}#account`}>Help</Link>.</li>
        </ul>
      </DocumentPage>
    </PublicShell>
  );
}
