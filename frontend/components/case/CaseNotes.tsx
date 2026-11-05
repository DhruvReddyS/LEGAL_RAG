"use client";

import { Check, Loader2, Pencil, Trash2, X } from "lucide-react";
import { useEffect, useId, useState, type FormEvent } from "react";
import { ApiError } from "@/lib/api";
import { createCaseNote, deleteCaseNote, editCaseNote, listCaseNotes, MAX_NOTE_CHARS, type CaseNote } from "@/lib/case-notes";

const WHEN = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });

function failure(error: unknown): string {
  return error instanceof ApiError ? error.message : "That could not be done. Check the connection and try again.";
}

/** A private list of notes on one case, readable only by the person who owns it. */
export default function CaseNotes({ caseId }: { caseId: string }) {
  const [notes, setNotes] = useState<CaseNote[] | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [edited, setEdited] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const fieldId = useId();

  useEffect(() => {
    const controller = new AbortController();
    setNotes(null);
    setError("");
    listCaseNotes(caseId, controller.signal)
      .then((response) => setNotes(response.notes))
      .catch((cause) => { if (!controller.signal.aborted) { setNotes([]); setError(failure(cause)); } });
    return () => controller.abort();
  }, [caseId]);

  const act = async (work: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try { await work(); }
    catch (cause) { setError(failure(cause)); }
    finally { setBusy(false); }
  };

  const add = (event: FormEvent) => {
    event.preventDefault();
    const body = draft.trim();
    if (!body) return;
    void act(async () => {
      const created = await createCaseNote(caseId, body);
      setNotes((current) => [created, ...(current ?? [])]);
      setDraft("");
    });
  };

  const save = (noteId: string) => {
    const body = edited.trim();
    if (!body) return;
    void act(async () => {
      const saved = await editCaseNote(caseId, noteId, body);
      setNotes((current) => (current ?? []).map((note) => (note.id === noteId ? saved : note)));
      setEditing(null);
    });
  };

  const remove = (noteId: string) => {
    void act(async () => {
      await deleteCaseNote(caseId, noteId);
      setNotes((current) => (current ?? []).filter((note) => note.id !== noteId));
      setConfirming(null);
    });
  };

  return (
    <section className="case-block case-notes">
      <div className="case-block-head">
        <div>
          <h4>Your notes</h4>
          <p>Private to you as the owner of this case. Nobody else can read them, including administrators.</p>
        </div>
      </div>
      <form onSubmit={add} className="case-notes-form">
        <label htmlFor={fieldId}>New note</label>
        <textarea id={fieldId} className="field" rows={3} maxLength={MAX_NOTE_CHARS} value={draft} onChange={(event) => setDraft(event.target.value)} />
        <button type="submit" className="button-secondary" disabled={busy || !draft.trim()}>
          {busy ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : null}Add note
        </button>
      </form>
      {error && <p className="case-notes-error" role="alert">{error}</p>}
      {notes === null ? (
        <p className="case-empty">Reading your notes…</p>
      ) : notes.length === 0 ? (
        !error && <p className="case-empty">No notes on this case yet.</p>
      ) : (
        <ul className="case-notes-list">
          {notes.map((note) => (
            <li key={note.id}>
              {editing === note.id ? (
                <form onSubmit={(event) => { event.preventDefault(); save(note.id); }}>
                  <textarea aria-label="Edit note" className="field" rows={4} maxLength={MAX_NOTE_CHARS} value={edited} onChange={(event) => setEdited(event.target.value)} autoFocus />
                  <div className="case-notes-actions">
                    <button type="submit" disabled={busy || !edited.trim()}><Check size={13} aria-hidden="true" />Save</button>
                    <button type="button" onClick={() => setEditing(null)}><X size={13} aria-hidden="true" />Cancel</button>
                  </div>
                </form>
              ) : (
                <>
                  <p className="case-notes-body">{note.body}</p>
                  <div className="case-notes-actions">
                    <small>
                      {WHEN.format(new Date(note.created_at))}
                      {note.updated_at !== note.created_at ? ", edited" : ""}
                    </small>
                    {confirming === note.id ? (
                      <>
                        <span>Delete this note?</span>
                        <button type="button" className="is-danger" disabled={busy} onClick={() => remove(note.id)}>Delete</button>
                        <button type="button" onClick={() => setConfirming(null)}>Keep</button>
                      </>
                    ) : (
                      <>
                        <button type="button" onClick={() => { setEditing(note.id); setEdited(note.body); setConfirming(null); }}><Pencil size={13} aria-hidden="true" />Edit</button>
                        <button type="button" onClick={() => { setConfirming(note.id); setEditing(null); }}><Trash2 size={13} aria-hidden="true" />Delete</button>
                      </>
                    )}
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
