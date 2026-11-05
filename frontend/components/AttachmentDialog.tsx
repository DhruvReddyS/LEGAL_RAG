"use client";
import { ArrowUpRight, FileText, Image as ImageIcon, LockKeyhole, ScanLine, X } from "lucide-react";
import { createPortal } from "react-dom";
import { useEffect } from "react";
import { useDialogFocus } from "./useDialogFocus";
import UploadPrivacy from "./UploadPrivacy";
import { useCitizenLang } from "./citizen/useCitizenLang";

export default function AttachmentDialog({ open, onClose, onChoose, citizen = false }: { open: boolean; onClose: () => void; onChoose: () => void; citizen?: boolean }) {
  const { t } = useCitizenLang(citizen);
  const ref = useDialogFocus(open, onClose);
  useEffect(() => { if (!open) return; const previous = document.body.style.overflow; document.body.style.overflow = "hidden"; return () => { document.body.style.overflow = previous; }; }, [open]);
  if (!open) return null;
  return createPortal(<div className="modal-backdrop upload-backdrop" onMouseDown={onClose}><div ref={ref} className="attachment-dialog" role="dialog" aria-modal="true" aria-labelledby="attachment-title" aria-describedby="attachment-description" onMouseDown={event => event.stopPropagation()}>
    <button className="icon-button attachment-close" aria-label={t("attachClose")} onClick={onClose}><X size={19}/></button>
    <div className="upload-illustration" aria-hidden="true"><div className="illustration-orbit"/><div className="illustration-photo"><ImageIcon size={29} strokeWidth={1.25}/><span/></div><div className="illustration-document"><FileText size={23} strokeWidth={1.25}/><i/><i/><i/><span>Document</span></div><div className="illustration-seal"><ScanLine size={22} strokeWidth={1.4}/></div></div>
    <h2 id="attachment-title">{t("attachTitle")}</h2><p id="attachment-description" className="attachment-intro">{t("attachIntro")}</p>
    <div className="attachment-promises"><div><ScanLine size={18}/><p><strong>{t("attachReadTitle")}</strong><span>{t("attachReadDetail")}</span></p></div><div><LockKeyhole size={18}/><p><strong>{t("attachKeptTitle")}</strong><span>{t("attachKeptDetail")}</span></p></div></div>
    <div className="attachment-retention">{t("attachRetention")}</div>
    <details className="attachment-details"><summary>{t("attachHow")}</summary><UploadPrivacy citizen={citizen}/></details>
    <button className="attachment-continue" onClick={onChoose}>{t("attachContinue")}<ArrowUpRight size={17}/></button><p className="attachment-formats">{t("attachFormats")}</p>
  </div></div>, document.body);
}
