"use client";

import { ArrowUp, BrainCircuit, Loader2, Paperclip, Route, ShieldCheck, Zap } from "lucide-react";
import { useCallback, useRef, useEffect } from "react";
import type { RequestedResponseMode } from "@/lib/types";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  loading?: boolean;
  placeholder?: string;
  mode?: RequestedResponseMode;
  onModeChange?: (mode: RequestedResponseMode) => void;
}

export default function ChatInput({
  onSend,
  disabled = false,
  loading = false,
  placeholder = "Ask about Indian law, acts, judgments…",
  mode = "auto",
  onModeChange,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [adjustHeight]);

  const handleSubmit = () => {
    const value = textareaRef.current?.value.trim();
    if (!value || disabled || loading) return;
    onSend(value);
    if (textareaRef.current) {
      textareaRef.current.value = "";
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="mx-auto w-full px-0 pb-4 pt-1">
      {onModeChange && <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><div className="inline-flex rounded-xl border border-[#e4e7ec] bg-[#f8fafc] p-1"><button type="button" onClick={() => onModeChange("auto")} className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${mode === "auto" ? "bg-[#0b1729] text-white shadow-sm" : "text-[#667085]"}`}><Route size={13} />Auto</button><button type="button" onClick={() => onModeChange("fast")} className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${mode === "fast" ? "bg-white text-[#167184] shadow-sm" : "text-[#667085]"}`}><Zap size={13} />Fast evidence</button><button type="button" onClick={() => onModeChange("deep")} className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${mode === "deep" ? "bg-[#0b1729] text-white shadow-sm" : "text-[#667085]"}`}><BrainCircuit size={13} />Deep review</button></div><p className="text-[11px] text-[#98a2b3]">{mode === "auto" ? "Automatically selects the fastest safe workflow" : mode === "fast" ? "Target: complete evidence brief within 5 seconds" : "Multi-agent reasoning, verification and bounded retry"}</p></div>}
      <div className="relative flex items-end rounded-2xl border border-[#d0d5dd] bg-white shadow-[0_3px_12px_rgba(16,24,40,0.06)] transition focus-within:border-[#167184] focus-within:ring-4 focus-within:ring-[#167184]/10">
        <button type="button" disabled className="m-2.5 mr-0 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[#98a2b3]" title="Document attachment is available in case workspaces">
          <Paperclip size={17} />
        </button>
        <textarea
          ref={textareaRef}
          rows={1}
          disabled={disabled || loading}
          placeholder={placeholder}
          onInput={adjustHeight}
          onKeyDown={handleKeyDown}
          aria-label="Legal research question"
          className="max-h-[200px] min-h-[60px] flex-1 resize-none bg-transparent px-3 py-[19px] text-sm text-[#101828] placeholder-[#98a2b3] outline-none disabled:opacity-50"
        />
        <button
          onClick={handleSubmit}
          disabled={disabled || loading}
          className="m-2.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#0b1729] text-white transition hover:bg-[#172941] disabled:cursor-not-allowed disabled:opacity-30"
          title="Send"
        >
          {loading ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <ArrowUp size={16} />
          )}
        </button>
      </div>
      <div className="mt-2 flex items-center justify-center gap-1.5 text-[11px] text-[#98a2b3]"><ShieldCheck size={12} /> Answers are limited to retrieved verified corpus evidence</div>
    </div>
  );
}
