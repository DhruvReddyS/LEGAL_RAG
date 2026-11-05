"use client";

import { MessageSquarePlus } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { ProLink } from "./context";

/**
 * A conversation and its neighbours, for one scope. The law-only chats and each case's
 * chats are separate lists on separate screens, so a question cannot land in the wrong one.
 */
export default function ProChatPane({ scopeCaseId, scopeTitle, activeCaseId, busy, empty, rows, onNew, onLoadMore, composer, conversation, suggestions, onSuggest }: {
  scopeCaseId: string | null;
  scopeTitle?: string;
  /** Which scope the conversation in memory belongs to. */
  activeCaseId: string | null;
  busy: boolean;
  empty: boolean;
  rows: ReactNode[];
  onNew: () => void;
  onLoadMore?: () => void;
  composer: ReactNode;
  conversation: ReactNode;
  suggestions: { title: string; text: string }[];
  onSuggest: (text: string) => void;
}) {
  // Open beside the conversation on a wide screen. On a phone it would push the question box down.
  const [listOpen, setListOpen] = useState(true);
  useEffect(() => { if (window.matchMedia("(max-width: 1023px)").matches) setListOpen(false); }, []);
  const elsewhere = activeCaseId !== scopeCaseId;
  const listTitle = scopeCaseId ? "Chats about this case" : "Law-only chats";
  const list = (
    <>
      {rows.length ? <div className="pro-chat-rows">{rows}</div> : <p className="pro-quiet">No chat here yet.</p>}
      {onLoadMore && <button type="button" className="pro-inline" onClick={onLoadMore}>Load older chats</button>}
    </>
  );
  return (
    <div className="pro-chat" data-chat-scope={scopeCaseId ? "case" : "law"}>
      <aside className="pro-chat-side" aria-label={listTitle}>
        <button type="button" className="pro-button pro-chat-new" disabled={busy} onClick={onNew}><MessageSquarePlus size={15} aria-hidden="true" />New chat</button>
        <details className="pro-chat-list" open={listOpen} onToggle={(event) => setListOpen(event.currentTarget.open)}>
          <summary>{listTitle} <b>{rows.length}</b></summary>
          {list}
        </details>
      </aside>
      <section className={`pro-chat-main ${empty ? "" : "has-conversation"}`}>
        {elsewhere ? (
          busy ? (
            <p className="pro-notice" role="status">
              An answer from another chat is still being prepared.{" "}
              <ProLink to={activeCaseId ? { section: "case", caseId: activeCaseId, tab: "ask" } : { section: "research" }} className="pro-text-link">Open that chat</ProLink>
            </p>
          ) : null
        ) : empty ? (
          <div className="pro-chat-welcome">
            <h2>{scopeCaseId ? `Ask about ${scopeTitle ?? "this case"}` : "What would you like to research?"}</h2>
            <p>{scopeCaseId ? "Reads the law and the files in this case, and no other case." : "Answers cite the source, and say so when the sources do not settle it."}</p>
            {composer}
            <div className="prompt-shortcuts">
              {suggestions.map((suggestion) => <button key={suggestion.title} type="button" disabled={busy} onClick={() => onSuggest(suggestion.text)}>{suggestion.title}</button>)}
            </div>
          </div>
        ) : conversation}
      </section>
    </div>
  );
}
