"use client";
import { ArrowUpRight, FileText, Image as ImageIcon, LockKeyhole, ScanLine, X } from "lucide-react";
import { createPortal } from "react-dom";
import { useEffect } from "react";
import { useDialogFocus } from "./useDialogFocus";
import UploadPrivacy from "./UploadPrivacy";

export default function AttachmentDialog({ open, onClose, onChoose }: { open: boolean; onClose: () => void; onChoose: () => void }) {
  const ref = useDialogFocus(open, onClose);
  useEffect(() => { if (!open) return; const previous = document.body.style.overflow; document.body.style.overflow = "hidden"; return () => { document.body.style.overflow = previous; }; }, [open]);
  if (!open) return null;
  return createPortal(<div className="modal-backdrop upload-backdrop" onMouseDown={onClose}><div ref={ref} className="attachment-dialog" role="dialog" aria-modal="true" aria-labelledby="attachment-title" aria-describedby="attachment-description" onMouseDown={event => event.stopPropagation()}>
    <button className="icon-button attachment-close" aria-label="Close upload dialog" onClick={onClose}><X size={19}/></button>
    <div className="upload-illustration" aria-hidden="true"><div className="illustration-orbit"/><div className="illustration-photo"><ImageIcon size={29} strokeWidth={1.25}/><span/></div><div className="illustration-document"><FileText size={23} strokeWidth={1.25}/><i/><i/><i/><span>Document</span></div><div className="illustration-seal"><ScanLine size={22} strokeWidth={1.4}/></div></div>
    <h2 id="attachment-title">A little context goes a long way.</h2><p id="attachment-description" className="attachment-intro">Add a notice, agreement or screenshot.<br/>We’ll read the text alongside your question.</p>
    <div className="attachment-promises"><div><ScanLine size={18}/><p><strong>Read, not added to the corpus</strong><span>Selected excerpts help with this question only.</span></p></div><div><LockKeyhole size={18}/><p><strong>Your original isn’t kept</strong><span>Files are discarded after extraction. Remove extracted text from the chat whenever you need.</span></p></div></div>
    <div className="attachment-retention">Chat replies and processing records may retain details from your file. Server-side deletion requires your workspace administrator.</div>
    <details className="attachment-details"><summary>How your file is handled</summary><UploadPrivacy/></details>
    <button className="attachment-continue" onClick={onChoose}>I understand, choose file<ArrowUpRight size={17}/></button><p className="attachment-formats">PDF, PNG, JPG or WebP · 10 MiB per file<br/>Up to 3 files · 20 pages per PDF · English OCR</p>
  </div></div>, document.body);
}
