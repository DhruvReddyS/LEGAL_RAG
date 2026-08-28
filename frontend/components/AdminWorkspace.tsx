"use client";

import { Activity, BadgeCheck, Database, FileCheck2, FileUp, Loader2, LockKeyhole, Shield, ShieldOff, UserPlus, UsersRound } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  ApiError, createAdminUser, getAdminOverview, listAdminUsers, listAuditEvents,
  listCorpusIntakes, publishCorpusIntake, stageCorpusIntake, updateAdminUser,
  validateCorpusIntake,
} from "@/lib/api";
import type { AdminManagedUser, AdminOverview, AuditEvent, CorpusIntake } from "@/lib/types";

const emptyOverview: AdminOverview = { users_total: 0, police_active: 0, advocates_active: 0, staged_intakes: 0, validated_intakes: 0, published_intakes: 0, audit_events: 0 };

function formatBytes(value: number) {
  return value < 1024 * 1024 ? `${Math.round(value / 1024)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export default function AdminWorkspace() {
  const [overview, setOverview] = useState(emptyOverview);
  const [users, setUsers] = useState<AdminManagedUser[]>([]);
  const [intakes, setIntakes] = useState<CorpusIntake[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    const [summary, accounts, corpus, audit] = await Promise.all([
      getAdminOverview(), listAdminUsers(), listCorpusIntakes(), listAuditEvents(),
    ]);
    setOverview(summary); setUsers(accounts.users); setIntakes(corpus.intakes); setEvents(audit.events);
  }, []);

  useEffect(() => { refresh().catch((error) => setNotice(error instanceof ApiError ? error.message : "Unable to load administration data")); }, [refresh]);

  const createAccount = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy("account"); setNotice("");
    const form = new FormData(event.currentTarget);
    try {
      await createAdminUser({ name: String(form.get("name")), email: String(form.get("email")), password: String(form.get("password")), role: String(form.get("role")) as "police" | "advocate" });
      event.currentTarget.reset(); setNotice("Professional account created and audit logged."); await refresh();
    } catch (error) { setNotice(error instanceof ApiError ? error.message : "Account creation failed"); }
    finally { setBusy(null); }
  };

  const toggleAccount = async (account: AdminManagedUser) => {
    setBusy(account.id); setNotice("");
    try { await updateAdminUser(account.id, { is_active: !account.is_active }); setNotice(`${account.name} is now ${account.is_active ? "suspended" : "active"}.`); await refresh(); }
    catch (error) { setNotice(error instanceof ApiError ? error.message : "Account update failed"); }
    finally { setBusy(null); }
  };

  const stageDocument = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy("corpus"); setNotice("");
    const form = new FormData(event.currentTarget); const file = form.get("file");
    if (!(file instanceof File) || !file.size) { setNotice("Choose a PDF to stage."); setBusy(null); return; }
    try {
      await stageCorpusIntake({ file, title: String(form.get("title")), sourceType: String(form.get("sourceType")), jurisdiction: String(form.get("jurisdiction")), authority: String(form.get("authority") ?? ""), sourceUrl: String(form.get("sourceUrl")) });
      event.currentTarget.reset(); setNotice("Document staged. Run validation before publishing."); await refresh();
    } catch (error) { setNotice(error instanceof ApiError ? error.message : "Corpus intake failed"); }
    finally { setBusy(null); }
  };

  const advanceIntake = async (intake: CorpusIntake) => {
    setBusy(intake.id); setNotice("");
    try {
      if (intake.status === "staged" || intake.status === "rejected") { const result = await validateCorpusIntake(intake.id); setNotice(result.status === "validated" ? "Quality validation passed. The source is ready for publication." : "The source failed extraction quality checks."); }
      else if (intake.status === "validated") { const result = await publishCorpusIntake(intake.id); setNotice(`Published ${result.indexed_chunks} verified extended-corpus passages.`); }
      await refresh();
    } catch (error) { setNotice(error instanceof ApiError ? error.message : "Corpus operation failed"); }
    finally { setBusy(null); }
  };

  const cards = [
    ["Active police", overview.police_active, Shield], ["Active advocates", overview.advocates_active, BadgeCheck],
    ["Pending validation", overview.staged_intakes, FileCheck2], ["Published additions", overview.published_intakes, Database],
  ] as const;

  return <section className="mx-auto max-w-[1240px] px-5 py-7 md:px-8 md:py-9">
    <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end"><div><p className="eyebrow">Governance control plane</p><h2 className="mt-2 text-3xl font-semibold tracking-[-.035em]">Administration workspace</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-[#667085]">Provision professional access, govern corpus expansion and inspect the operational evidence trail.</p></div><div className="inline-flex items-center gap-2 rounded-full border border-[#d7eadf] bg-[#f1faf5] px-3 py-2 text-xs font-medium text-[#16734a]"><LockKeyhole size={14}/>Administrative RBAC enforced</div></div>
    <div className="mt-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{cards.map(([label,value,Icon]) => <div key={label} className="panel flex items-center gap-4 p-5"><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#eef6f7] text-[#167184]"><Icon size={19}/></span><div><p className="text-2xl font-semibold">{value}</p><p className="text-xs text-[#667085]">{label}</p></div></div>)}</div>
    {notice && <div role="status" className="mt-5 rounded-xl border border-[#c9dfe2] bg-[#f3fafb] px-4 py-3 text-sm text-[#315f67]">{notice}</div>}

    <div className="mt-7 grid gap-6 xl:grid-cols-[.9fr_1.4fr]">
      <div className="panel p-5"><div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#edf4ff] text-[#245b9e]"><UserPlus size={18}/></span><div><h3 className="text-sm font-semibold">Provision professional account</h3><p className="text-xs text-[#667085]">Police and advocate access only</p></div></div><form className="mt-5 space-y-3" onSubmit={createAccount}><input required name="name" minLength={2} placeholder="Full professional name" className="field"/><input required name="email" type="email" placeholder="Work email" className="field"/><div className="grid gap-3 sm:grid-cols-2"><select name="role" className="field"><option value="police">Police</option><option value="advocate">Advocate</option></select><input required name="password" type="password" minLength={12} placeholder="Temporary password" className="field"/></div><button disabled={busy === "account"} className="button-primary w-full">{busy === "account" ? <Loader2 size={16} className="animate-spin"/> : <UserPlus size={16}/>} Create controlled account</button></form></div>
      <div className="panel overflow-hidden"><div className="flex items-center justify-between border-b border-[#eaecf0] px-5 py-4"><div><h3 className="text-sm font-semibold">Professional directory</h3><p className="mt-1 text-xs text-[#667085]">{users.length} governed accounts</p></div><UsersRound size={18} className="text-[#167184]"/></div><div className="divide-y divide-[#eaecf0]">{users.length ? users.map((account) => <div key={account.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center"><span className={`h-2.5 w-2.5 rounded-full ${account.is_active ? "bg-[#23a36d]" : "bg-[#c4c9d0]"}`}/><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{account.name}</p><p className="truncate text-xs text-[#667085]">{account.email} · <span className="capitalize">{account.role}</span> · {account.case_count} cases</p></div><button onClick={() => toggleAccount(account)} disabled={busy === account.id} className="button-secondary text-xs">{busy === account.id ? <Loader2 size={14} className="animate-spin"/> : account.is_active ? <ShieldOff size={14}/> : <Shield size={14}/>} {account.is_active ? "Suspend" : "Activate"}</button></div>) : <p className="px-5 py-10 text-center text-sm text-[#98a2b3]">No professional accounts yet</p>}</div></div>
    </div>

    <div className="mt-6 grid gap-6 xl:grid-cols-[.9fr_1.4fr]">
      <div className="panel p-5"><div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#faf3e9] text-[#76512f]"><FileUp size={18}/></span><div><h3 className="text-sm font-semibold">Global corpus intake</h3><p className="text-xs text-[#667085]">Stage official PDF · 30 MiB maximum</p></div></div><form className="mt-5 space-y-3" onSubmit={stageDocument}><input required name="title" placeholder="Official source title" className="field"/><div className="grid gap-3 sm:grid-cols-2"><select name="sourceType" className="field"><option value="act">Act / statute</option><option value="judgment">Judgment</option><option value="notification">Notification</option></select><input required name="jurisdiction" defaultValue="India" placeholder="Jurisdiction" className="field"/></div><input name="authority" placeholder="Court / issuing authority" className="field"/><input required name="sourceUrl" type="url" placeholder="https://official-source.gov/..." className="field"/><label className="flex min-h-28 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-[#a9cbd0] bg-[#f7fbfb] text-center"><FileUp size={20} className="text-[#167184]"/><span className="mt-2 text-sm font-medium">Choose official PDF</span><span className="text-xs text-[#98a2b3]">Checksum and PDF signature verified</span><input required name="file" type="file" accept="application/pdf" className="hidden"/></label><button disabled={busy === "corpus"} className="button-primary w-full">{busy === "corpus" ? <Loader2 size={16} className="animate-spin"/> : <FileUp size={16}/>} Stage for validation</button></form></div>
      <div className="panel overflow-hidden"><div className="flex items-center justify-between border-b border-[#eaecf0] px-5 py-4"><div><h3 className="text-sm font-semibold">Corpus governance queue</h3><p className="mt-1 text-xs text-[#667085]">Gold remains immutable; approved additions publish to the verified extended tier</p></div><Database size={18} className="text-[#167184]"/></div><div className="divide-y divide-[#eaecf0]">{intakes.length ? intakes.map((intake) => <div key={intake.id} className="px-5 py-4"><div className="flex flex-col gap-3 sm:flex-row sm:items-center"><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><p className="truncate text-sm font-medium">{intake.title}</p><span className={`rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase ${intake.status === "published" ? "bg-[#eaf8f1] text-[#16734a]" : intake.status === "rejected" ? "bg-[#fff0f0] text-[#b42318]" : "bg-[#fff7e6] text-[#8a5a12]"}`}>{intake.status}</span></div><p className="mt-1 truncate text-xs text-[#667085]">{intake.filename} · {formatBytes(intake.file_size)} · {intake.source_type}</p></div>{intake.status !== "published" && <button onClick={() => advanceIntake(intake)} disabled={busy === intake.id} className="button-secondary text-xs">{busy === intake.id ? <Loader2 size={14} className="animate-spin"/> : <FileCheck2 size={14}/>} {intake.status === "validated" ? "Publish extended" : "Run validation"}</button>}</div>{Boolean(intake.validation_summary.pages) && <p className="mt-2 text-[11px] text-[#98a2b3]">{String(intake.validation_summary.pages)} pages · {String(intake.validation_summary.extracted_characters ?? 0)} extracted characters · {String(intake.validation_summary.ocr_pages ?? 0)} OCR pages</p>}</div>) : <p className="px-5 py-10 text-center text-sm text-[#98a2b3]">No corpus additions staged</p>}</div></div>
    </div>

    <div className="panel mt-6 overflow-hidden"><div className="flex items-center justify-between border-b border-[#eaecf0] px-5 py-4"><div><h3 className="text-sm font-semibold">Recent audit activity</h3><p className="mt-1 text-xs text-[#667085]">Append-only operational evidence trail</p></div><Activity size={18} className="text-[#167184]"/></div><div className="divide-y divide-[#eaecf0]">{events.slice(0, 12).map((event) => <div key={event.id} className="grid gap-1 px-5 py-3 text-xs sm:grid-cols-[1fr_1fr_auto]"><span className="font-medium text-[#344054]">{event.action}</span><span className="text-[#667085]">{event.actor_name ?? "System"} · {event.resource_type}</span><time className="text-[#98a2b3]">{new Date(event.timestamp).toLocaleString()}</time></div>)}</div></div>
  </section>;
}
