"use client";

import { Plus, UsersRound } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { errorText, ErrorNote, Field } from "@/components/police/shared";
import { createUnit, listUnits, removeUnitMember, setUnitMember } from "@/lib/api-police";
import type { PoliceUnit } from "@/lib/types-police";

function UnitCard({ unit, onChanged }: { unit: PoliceUnit; onChanged: (next: PoliceUnit) => void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"member" | "supervisor">("member");
  const [error, setError] = useState("");
  const add = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try { onChanged(await setUnitMember(unit.id, email.trim(), role)); setEmail(""); }
    catch (cause) { setError(errorText(cause)); }
  };
  const remove = async (userId: string) => {
    setError("");
    try { onChanged(await removeUnitMember(unit.id, userId)); }
    catch (cause) { setError(errorText(cause)); }
  };
  return (
    <li className="police-card">
      <div className="police-card-head"><h4>{unit.name}</h4></div>
      {unit.members.length ? (
        <ul className="police-checks">
          {unit.members.map((member) => (
            <li key={member.user_id} className="police-check-row">
              <div className="police-check-row-top">
                <p>{member.name} <small>{member.email}</small></p>
                <span className={`police-pill ${member.role === "supervisor" ? "is-warn" : "is-plain"}`}>{member.role === "supervisor" ? "Supervisor" : "Member"}</span>
                <button type="button" className="police-mini is-danger" onClick={() => void remove(member.user_id)}>Remove</button>
              </div>
            </li>
          ))}
        </ul>
      ) : <p className="police-row-detail">Nobody is in this unit.</p>}
      <form className="police-inline-form" onSubmit={add} aria-label={`Add to ${unit.name}`}>
        <div className="police-grid">
          <Field label="Police account email"><input required type="email" className="field" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Field label="Role">
            <select className="field" value={role} onChange={(e) => setRole(e.target.value as "member" | "supervisor")}>
              <option value="member">Member</option><option value="supervisor">Supervisor</option>
            </select>
          </Field>
        </div>
        <ErrorNote message={error} />
        <div><button className="police-mini" type="submit"><Plus size={13} aria-hidden="true" />Add or change</button></div>
      </form>
    </li>
  );
}

/**
 * Who supervises whom. A supervisor sees counts across the unit's officers, so this is
 * a grant of access, and every change is written to the audit log.
 */
export function UnitAdminPanel() {
  const [units, setUnits] = useState<PoliceUnit[] | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try { setUnits(await listUnits()); }
    catch (cause) { setError(errorText(cause)); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const made = await createUnit(name.trim());
      setUnits((current) => [...(current ?? []), made]);
      setName("");
    } catch (cause) { setError(errorText(cause)); }
  };

  return (
    <section className="police-units-panel police-stack" aria-label="Police units">
      <div className="police-card-head">
        <h4 className="flex items-center gap-2 text-sm font-semibold"><UsersRound size={16} aria-hidden="true" />Police units and supervisors</h4>
      </div>
      <p className="police-note">A supervisor sees deadline states and compliance counts for the unit&apos;s open cases, and no case material. Administrators do not gain that view by managing units. Each change is audited.</p>
      <form className="police-filters" onSubmit={create} aria-label="Create a unit">
        <label>New unit name<input required minLength={2} className="field" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <button className="police-mini" type="submit"><Plus size={13} aria-hidden="true" />Create unit</button>
      </form>
      <ErrorNote message={error} />
      {units && !units.length && <p className="police-empty">No unit has been created.</p>}
      {units && units.length > 0 && (
        <ul className="grid gap-3">
          {units.map((unit) => (
            <UnitCard key={unit.id} unit={unit} onChanged={(next) => setUnits((current) => (current ?? []).map((u) => (u.id === next.id ? next : u)))} />
          ))}
        </ul>
      )}
    </section>
  );
}
