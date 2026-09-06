"use client";
import { ArrowUp, ChevronDown, FileText, Image as ImageIcon, Mic, Paperclip, Square, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { extractCitizenDocument } from "@/lib/api";
import type { CitizenDocument, RequestedResponseMode } from "@/lib/types";
import AttachmentDialog from "./AttachmentDialog";

type Recognition = { lang: string; continuous: boolean; interimResults: boolean; start: () => void; stop: () => void; abort: () => void; onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onerror: ((event: { error: string }) => void) | null; onend: (() => void) | null };
type SpeechWindow = Window & { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
interface ChatInputProps { onSend: (message: string, documents?: CitizenDocument[]) => void; onStop?: () => void; disabled?: boolean; loading?: boolean; placeholder?: string; mode?: RequestedResponseMode; onModeChange?: (mode: RequestedResponseMode) => void;   /** Matters this professional owns. Empty for a citizen, who never has one. */
  cases?: { id: string; title: string }[];
  /** The matter the question may also read. Null means public law only. */
  caseId?: string | null;
  onCaseChange?: (caseId: string | null) => void;
}

export default function ChatInput({ onSend, onStop, disabled = false, loading = false, placeholder = "Ask a follow-up…", mode = "auto", onModeChange, cases = [], caseId = null, onCaseChange }: ChatInputProps) {
  const [value, setValue] = useState("");
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
    session.onerror = event => { setError(`Voice input stopped (${event.error}). You can still type your question.`); setRecording(false); };
    try { session.start(); setRecording(true); setVoiceInfo(false); setError(""); } catch { setError("Microphone unavailable. Please type your question."); }
  };
  return <div className="composer-wrap"><div className="composer">
    {documents.length > 0 && <div className="attachment-row">{documents.map((doc, index) => <span className="attachment-chip" key={doc.id}>{doc.media_type === "application/pdf" ? <FileText size={15}/> : <ImageIcon size={15}/>}<span title={doc.filename}>D{index + 1} · {doc.filename}</span><button disabled={busy} aria-label={`Remove ${doc.filename}`} onClick={() => setDocuments(current => current.filter(item => item.id !== doc.id))}><X size={14}/></button></span>)}</div>}
    <div className="composer-input-row"><button className="icon-button" disabled={busy || recording || documents.length >= 3} aria-label="Attach a document or image" onClick={() => setPrivacy(current => !current)}><Paperclip size={19}/></button><textarea ref={input} value={value} maxLength={4000} onChange={event => setValue(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send(); } }} disabled={busy} rows={1} placeholder={placeholder} aria-label="Legal research question"/><button className={`icon-button mic-button ${recording ? "is-recording" : ""}`} disabled={busy || !voiceSupported} title={voiceSupported ? "Dictate in English; review before sending" : "Voice input unavailable in this browser"} aria-label={recording ? "Stop recording" : "Start voice input"} aria-pressed={recording} onClick={() => { if (recording) recognition.current?.stop(); else setVoiceInfo(current => !current); }}>{recording ? <Square size={16}/> : <Mic size={19}/>}</button>{loading && onStop ? <button onClick={onStop} aria-label="Stop response" title="Stop response" className="send-button"><Square size={14} fill="currentColor"/></button> : <button onClick={send} disabled={busy || recording || (!value.trim() && !documents.length)} aria-label="Send question" className="send-button"><ArrowUp size={19}/></button>}</div>
    <div className="composer-toolbar"><label className="mode-picker"><select aria-label="Response mode" value={documents.length ? "deep" : mode} disabled={busy || Boolean(documents.length)} onChange={event => onModeChange?.(event.target.value as RequestedResponseMode)}><option value="auto">Auto</option><option value="fast">Fast evidence</option><option value="deep">Deep review</option></select><ChevronDown size={13}/></label>{cases.length > 0 && (
      <label className="mode-picker" title="Whether this question may read a matter's private evidence">
        <select
          aria-label="Knowledge scope"
          value={caseId ?? ""}
          disabled={busy}
          onChange={event => onCaseChange?.(event.target.value || null)}
        >
          <option value="">The law only — no case files</option>
          {cases.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
        </select>
        <ChevronDown size={13}/>
      </label>
    )}<span>{extracting ? "Extracting document text…" : recording ? "Recording · stop to review" : documents.length ? "Documents use Deep review" : caseId ? "Reading the law and this case's files" : "PDFs & images · voice where supported"}</span></div>
    <input ref={fileInput} type="file" accept="application/pdf,image/png,image/jpeg,image/webp" className="sr-only" tabIndex={-1} aria-label="Choose document" onChange={async event => {
      const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
      if (file.size > 10 * 1024 * 1024) { setError("Choose a file smaller than 10 MiB."); return; }
      setExtracting(true); setError("");
      try { const document = await extractCitizenDocument(file); if (mounted.current) { setDocuments(current => [...current, document]); if (document.truncated) setError("Only the first 12,000 characters were extracted. Use a shorter document for complete review."); } }
      catch (cause) { if (mounted.current) setError(cause instanceof Error ? cause.message : "Extraction failed. Try another file."); }
      finally { if (mounted.current) setExtracting(false); }
    }}/>
  </div>
  <AttachmentDialog open={privacy} onClose={() => setPrivacy(false)} onChoose={() => { setPrivacy(false); fileInput.current?.click(); }}/>
  {voiceInfo && <section className="intake-disclosure" aria-label="Voice privacy"><p>Your browser’s speech-recognition service may send audio to its provider. English (India) is enabled; Hindi and regional-language recognition are not validated. Review and edit the transcript before sending. Corpus does not upload or store your audio.</p><button className="button-secondary" onClick={startVoice}>Allow voice input</button><button className="answer-text-action" onClick={() => setVoiceInfo(false)}>Cancel</button></section>}
  {error && <p className="composer-status" role="status">{error}</p>}
  </div>;
}
