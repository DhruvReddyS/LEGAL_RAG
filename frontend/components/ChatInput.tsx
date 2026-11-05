"use client";
import { ArrowUp, ChevronDown, FileText, Image as ImageIcon, Mic, Paperclip, Square, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { extractCitizenDocument } from "@/lib/api";
import { saveDraft } from "@/lib/citizen-chat";
import type { CitizenDocument, RequestedResponseMode } from "@/lib/types";
import AttachmentDialog from "./AttachmentDialog";
import RedactionDialog from "./citizen/RedactionDialog";
import { useCitizenLang } from "./citizen/useCitizenLang";

type Recognition = { lang: string; continuous: boolean; interimResults: boolean; start: () => void; stop: () => void; abort: () => void; onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onerror: ((event: { error: string }) => void) | null; onend: (() => void) | null };
type SpeechWindow = Window & { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
interface ChatInputProps { scopeLockedReason?: string | null; onSend: (message: string, documents?: CitizenDocument[]) => void; onStop?: () => void; disabled?: boolean; loading?: boolean; placeholder?: string; mode?: RequestedResponseMode; onModeChange?: (mode: RequestedResponseMode) => void;   /** Matters this professional owns. Empty for a citizen, who never has one. */
  cases?: { id: string; title: string; status: string }[];
  /** The matter the question may also read. Null means public law only. */
  caseId?: string | null;
  onCaseChange?: (caseId: string | null) => void;
  /** Citizens check extracted text and mask personal details before it joins the question. */
  redactBeforeAttach?: boolean;
  /** Text to restore after having to sign in again. */
  initialDraft?: string;
}

export default function ChatInput({ scopeLockedReason = null, onSend, onStop, disabled = false, loading = false, placeholder, mode = "auto", onModeChange, cases = [], caseId = null, onCaseChange, redactBeforeAttach = false, initialDraft = "" }: ChatInputProps) {
  // Only a citizen's composer has this flag, and only a citizen's chat is translated.
  const { t } = useCitizenLang(redactBeforeAttach);
  const [value, setValueState] = useState(initialDraft);
  const setValue = (next: string) => { setValueState(next); saveDraft(window.sessionStorage, next); };
  const [pendingDocument, setPendingDocument] = useState<CitizenDocument | null>(null);
  // A fresh composer has no draft, so an old one cannot resurface after the next sign-in.
  useEffect(() => { saveDraft(window.sessionStorage, initialDraft); }, [initialDraft]);
  const [documents, setDocuments] = useState<CitizenDocument[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState("");
  const [privacy, setPrivacy] = useState(false);
  const [voiceInfo, setVoiceInfo] = useState(false);
  const [recording, setRecording] = useState(false);
  const [voiceSupported, setVoiceSupported] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const recognition = useRef<Recognition | null>(null);
  const mounted = useRef(true);
  const busy = disabled || loading || extracting;
  useEffect(() => { mounted.current = true; const host = window as SpeechWindow; setVoiceSupported(Boolean(host.SpeechRecognition || host.webkitSpeechRecognition)); return () => { mounted.current = false; if (recognition.current) { recognition.current.onresult = recognition.current.onend = recognition.current.onerror = null; recognition.current.abort(); } }; }, []);
  useEffect(() => { if (input.current) { input.current.style.height = "auto"; input.current.style.height = Math.min(input.current.scrollHeight, 200) + "px"; } }, [value]);
  const send = () => { if ((!value.trim() && !documents.length) || busy || recording) return; onSend(value.trim() || "Please explain the legal issues in my attached document and the source-supported next steps.", documents); setValue(""); setDocuments([]); setError(""); };
  const startVoice = () => {
    const host = window as SpeechWindow;
    const Constructor = host.SpeechRecognition || host.webkitSpeechRecognition;
    if (!Constructor) return;
    const session = new Constructor(); recognition.current = session;
    session.lang = "en-IN"; session.continuous = true; session.interimResults = true;
    const prefix = value.trim();
    session.onresult = event => { const text = Array.from(event.results).map(result => result[0]?.transcript || "").join(" "); setValue([prefix, text].filter(Boolean).join(" ")); };
    session.onend = () => setRecording(false);
    session.onerror = event => { setError(t("voiceStopped")); setRecording(false); };
    try { session.start(); setRecording(true); setVoiceInfo(false); setError(""); } catch { setError(t("micUnavailable")); }
  };
  return <div className="composer-wrap"><div className="composer">
    {documents.length > 0 && <div className="attachment-row">{documents.map((doc, index) => <span className="attachment-chip" key={doc.id}>{doc.media_type === "application/pdf" ? <FileText size={15}/> : <ImageIcon size={15}/>}<span title={doc.filename}>D{index + 1} · {doc.filename}</span><button disabled={busy} aria-label={`Remove ${doc.filename}`} onClick={() => setDocuments(current => current.filter(item => item.id !== doc.id))}><X size={14}/></button></span>)}</div>}
    <div className="composer-input-row"><button className="icon-button" disabled={busy || recording || documents.length >= 3} aria-label={t("attachLabel")} onClick={() => setPrivacy(current => !current)}><Paperclip size={19}/></button><textarea ref={input} value={value} maxLength={4000} onChange={event => setValue(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send(); } }} disabled={busy} rows={1} placeholder={placeholder ?? t("composerFollowUp")} aria-label={t("questionLabel")}/><button className={`icon-button mic-button ${recording ? "is-recording" : ""}`} disabled={busy || !voiceSupported} title={voiceSupported ? t("voiceHint") : t("voiceUnavailable")} aria-label={recording ? t("voiceStop") : t("voiceStart")} aria-pressed={recording} onClick={() => { if (recording) recognition.current?.stop(); else setVoiceInfo(current => !current); }}>{recording ? <Square size={16}/> : <Mic size={19}/>}</button>{loading && onStop ? <button onClick={onStop} aria-label={t("stopResponse")} title={t("stopResponse")} className="send-button"><Square size={14} fill="currentColor"/></button> : <button onClick={send} disabled={busy || recording || (!value.trim() && !documents.length)} aria-label={t("sendQuestion")} className="send-button"><ArrowUp size={19}/></button>}</div>
    <div className="composer-toolbar"><label className="mode-picker"><select aria-label={t("modeLabel")} value={documents.length ? "deep" : mode} disabled={busy || Boolean(documents.length)} onChange={event => onModeChange?.(event.target.value as RequestedResponseMode)}><option value="auto">{t("modeAuto")}</option><option value="fast">{t("modeFast")}</option><option value="deep">{t("modeDeep")}</option></select><ChevronDown size={13}/></label>{cases.length > 0 && (
      <label className="mode-picker" title={scopeLockedReason ?? "Whether this question may also read one case's own files"}>
        <select
          aria-label="Knowledge scope"
          value={caseId ?? ""}
          disabled={busy || Boolean(scopeLockedReason)}
          title={scopeLockedReason ?? undefined}
          onChange={event => onCaseChange?.(event.target.value || null)}
        >
          <option value="">The law only — no case files</option>
          {/* A closed case is not offered for new work, but a conversation
              already inside one keeps showing where it belongs. */}
          {cases.filter(item => item.status === "open" || item.id === caseId).map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
        </select>
        <ChevronDown size={13}/>
      </label>
    )}<span>{extracting ? t("statusExtracting") : recording ? t("statusRecording") : documents.length ? t("statusDocsDeep") : caseId ? "Reading the law and this case's files" : t("statusDefault")}</span></div>
    <input ref={fileInput} type="file" accept="application/pdf,image/png,image/jpeg,image/webp" className="sr-only" tabIndex={-1} aria-label={t("chooseDocument")} onChange={async event => {
      const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
      if (file.size > 10 * 1024 * 1024) { setError(t("fileTooBig")); return; }
      setExtracting(true); setError("");
      try { const document = await extractCitizenDocument(file); if (mounted.current) { if (redactBeforeAttach) setPendingDocument(document); else setDocuments(current => [...current, document]); if (document.truncated) setError(t("truncatedDocument")); } }
      catch (cause) { if (mounted.current) setError(cause instanceof Error ? cause.message : t("extractionFailed")); }
      finally { if (mounted.current) setExtracting(false); }
    }}/>
  </div>
  <RedactionDialog document={pendingDocument} onCancel={() => setPendingDocument(null)} onConfirm={masked => { setDocuments(current => [...current, masked]); setPendingDocument(null); }}/>
  <AttachmentDialog citizen={redactBeforeAttach} open={privacy} onClose={() => setPrivacy(false)} onChoose={() => { setPrivacy(false); fileInput.current?.click(); }}/>
  {voiceInfo && <section className="intake-disclosure" aria-label={t("voicePrivacyLabel")}><p>{t("voicePrivacy")}</p><button className="button-secondary" onClick={startVoice}>{t("allowVoice")}</button><button className="answer-text-action" onClick={() => setVoiceInfo(false)}>{t("cancel")}</button></section>}
  {error && <p className="composer-status" role="status">{error}</p>}
  </div>;
}
