# Running Corpusil on Windows

Corpusil runs as **one server** (a Mac that holds the legal corpus, the databases and the
language model) and **desktop apps** that connect to it. Friends on Windows install only the
app. They do not need Docker, Ollama, Python or the corpus.

```
 Windows laptop  ──  Corpusil app  ──(Tailscale, private HTTPS)──►  Host Mac: API, corpus, model
```

Part 1 is for the person running the server. Part 2 is for everyone using the Windows app.

---

## Part 1: the host Mac (once, then before each session)

### Once

1. **Install the project** as in [`docs/QUICKSTART_LOCAL.md`](docs/QUICKSTART_LOCAL.md): Docker
   Desktop, Ollama with the model `qwen3-14b-16k`, the corpus, and `.env` from
   `./scripts/init_local_env.sh`.
2. **Install Tailscale** from <https://tailscale.com/download> and sign in.
3. In the Tailscale admin console (<https://login.tailscale.com/admin/dns>), turn on
   **MagicDNS** and **HTTPS Certificates**.
4. **Invite each friend** from the admin console (Users → Invite users). The free plan allows
   up to six people.
5. **Accounts for friends:**
   - A citizen account: they can create it themselves in the app with **Create one**.
   - A police or advocate account: sign in as an administrator, open **Admin → Users**, and use
     **Provision a professional account**. Give each person their own account and password,
     privately.

### Before each session

1. Plug the Mac into power and turn off Low Power Mode (System Settings → Battery). In Low Power
   Mode answers take about twice as long.
2. Open **Docker Desktop**, **Ollama** and **Tailscale**.
3. In Terminal, from the project folder:
   ```bash
   ./scripts/start_private_demo_host.sh
   ```
   It starts everything, waits until the models are loaded, and prints a line like:
   ```
   Desktop backend URL: https://your-mac.your-tailnet.ts.net
   ```
4. Send that address to your friends. Keep the Mac awake, plugged in and online while they use
   it. Answers are written one at a time, so if three people ask at once the last one waits a
   little longer.

---

## Part 2: Windows (each friend)

Requirements: Windows 10 or 11, 64-bit, an internet connection.

### 1. Join the private network

1. Accept the Tailscale invitation email from the host.
2. Install Tailscale for Windows from <https://tailscale.com/download/windows> and sign in with
   the account the invitation was sent to.
3. The Tailscale icon in the taskbar should show **Connected**.

### 2. Install Corpusil

1. Open <https://github.com/DhruvReddyS/LEGAL_RAG/releases/latest>.
2. Under **Assets**, download **`Corpusil-<version>-Windows-Setup.exe`**.
3. Run it. Because the installer is not code-signed, Windows SmartScreen may say
   "Windows protected your PC". Choose **More info → Run anyway**. GitHub lists a
   SHA-256 checksum beside each file if you want to confirm the download.
4. Finish the installer and open **Corpusil** from the Start menu.

### 3. Connect to the host

1. On first launch the app opens **Connect to your Corpusil server**. If it does not, open it
   from the status chip at the top of the window.
2. In **Backend base URL**, paste the address the host sent you, for example
   `https://your-mac.your-tailnet.ts.net`. It must start with `https://` and have nothing after
   the name.
3. Press **Test connection**. When it reports the server as reachable, press
   **Save & reconnect**.
4. Sign in with your account, or choose **Create one** for a citizen account.

That is all. Questions, cases and files stay on the host Mac.

---

## macOS users

Same steps, with the **`.dmg`** from the release page: **`Mac-Apple-Silicon`** for Apple-chip Macs,
**`Mac-Intel`** for Intel Macs. The first time, macOS may refuse to open an app from an unidentified developer:
open **System Settings → Privacy & Security** and press **Open Anyway**.

---

## If something goes wrong

| What you see | What to do |
|---|---|
| **Test connection** fails | Check Tailscale shows *Connected* on both machines, and the host's Terminal still shows the script running. Paste the address again, starting with `https://`. |
| "Remote backends must use HTTPS" | The address must start with `https://`, not `http://`. |
| The app opens to a blank window (older Windows 10) | Install Microsoft Edge WebView2 Runtime from <https://developer.microsoft.com/microsoft-edge/webview2/>, then reopen Corpusil. |
| Sign-in fails | Ask the host to check your account under Admin → Users. A reset password must be changed at first sign-in. |
| An answer takes over two minutes | The host Mac may be busy, on battery or in Low Power Mode. Short questions are answered in about 40 seconds; **Fast evidence** mode returns sources in about a second. |
| It worked yesterday, not today | The host must run `./scripts/start_private_demo_host.sh` again after a restart. |

Corpusil gives legal information, not legal advice. Check the current official text before
relying on an answer.
