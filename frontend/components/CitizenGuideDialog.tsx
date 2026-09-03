"use client";
import { ArrowLeft, ArrowRight, BookOpenText, Check, FileText, MessageSquareText, Paperclip, Scale, ShieldCheck, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useDialogFocus } from "./useDialogFocus";

const slides = [
  { key: "rights", kicker: "Know your rights", title: "Turn a confusing situation into a clear question.", description: "Tell Corpus what happened, where you are in the process and what you need to decide. Leave out names, ID numbers and details that do not affect the legal issue.", prompt: "What are my rights if police call me for questioning, and what details should I record?", Icon: ShieldCheck },
  { key: "incident", kicker: "Report an incident", title: "Build a useful record before details disappear.", description: "Start with the event, time and place. Then add what you saw, what you still have, and whether anyone has already been informed.", prompt: "What should I preserve and include when reporting a mobile-phone snatching to police?", Icon: MessageSquareText },
  { key: "contract", kicker: "Understand a document", title: "Read the clause. Then check the law.", description: "Attach a readable agreement or notice and ask about one decision at a time. Your document is factual context—legal sources remain visibly separate.", prompt: "Help me review a rental agreement for termination, deposit and notice clauses, using current legal sources.", Icon: BookOpenText },
] as const;

export default function CitizenGuideDialog({ open, initialSlide, onClose, onStart }: { open: boolean; initialSlide: number; onClose: () => void; onStart: (prompt: string) => void }) {
  const [index, setIndex] = useState(initialSlide);
  const ref = useDialogFocus(open, onClose);
  useEffect(() => { if (open) setIndex(initialSlide); }, [open, initialSlide]);
  useEffect(() => { if (!open) return; const key = (event: KeyboardEvent) => { if (event.key === "ArrowRight") setIndex(value => Math.min(slides.length - 1, value + 1)); if (event.key === "ArrowLeft") setIndex(value => Math.max(0, value - 1)); }; window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key); }, [open]);
  useEffect(() => { if (!open) return; const previous = document.body.style.overflow; document.body.style.overflow = "hidden"; return () => { document.body.style.overflow = previous; }; }, [open]);
  if (!open) return null;
  const slide = slides[index];
  return createPortal(<div className="modal-backdrop guide-backdrop" onMouseDown={onClose}><div ref={ref} className="citizen-guide-dialog" role="dialog" aria-modal="true" aria-labelledby="citizen-guide-title" onMouseDown={event => event.stopPropagation()}>
    <button className="icon-button guide-close" aria-label="Close guide" onClick={onClose}><X size={18}/></button>
    <div className="guide-stage" data-slide={slide.key} aria-hidden="true">
      <div className="guide-stage-orb"><slide.Icon size={30} strokeWidth={1.3}/></div>
      {slide.key === "rights" && <div className="mini-conversation"><span>Can they ask me to come in?</span><div><i/><i/><i className="short"/></div><b><Scale size={12}/>2 legal sources</b></div>}
      {slide.key === "incident" && <div className="mini-timeline"><span><Check size={12}/>What happened</span><i/><span><Check size={12}/>What you kept</span><i/><span><FileText size={12}/>How to report</span></div>}
      {slide.key === "contract" && <div className="mini-document"><div><FileText size={23}/><i/><i/><i/></div><span><Sparkles size={13}/>Clause found</span><b><Paperclip size={13}/>Your file · D1</b></div>}
    </div>
    <p className="guide-kicker">{slide.kicker}</p><h2 id="citizen-guide-title">{slide.title}</h2><p className="guide-description">{slide.description}</p>
    <div className="guide-prompt"><div><span>A useful way to start</span><p>“{slide.prompt}”</p></div><button onClick={() => onStart(slide.prompt)}>Ask this<ArrowRight size={14}/></button></div>
    <div className="guide-footer"><div className="guide-dots" aria-label={`Guide ${index + 1} of ${slides.length}`}>{slides.map((item, itemIndex) => <button key={item.key} aria-label={`Show ${item.kicker}`} aria-current={itemIndex === index} onClick={() => setIndex(itemIndex)}/>)}</div><div className="guide-navigation"><button aria-label="Previous guide" disabled={index === 0} onClick={() => setIndex(value => value - 1)}><ArrowLeft size={17}/></button>{index < slides.length - 1 ? <button onClick={() => setIndex(value => value + 1)}>Next<ArrowRight size={16}/></button> : <button onClick={() => onStart(slide.prompt)}>Use this prompt<ArrowRight size={16}/></button>}</div></div>
  </div></div>, document.body);
}
